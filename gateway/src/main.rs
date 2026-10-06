use anyhow::{Context, Result, bail};
use axum::{
    Json, Router,
    body::{Body, Bytes},
    extract::{
        DefaultBodyLimit, Query, State, WebSocketUpgrade,
        ws::{Message, WebSocket},
    },
    http::{HeaderMap, HeaderName, HeaderValue, StatusCode, header},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use axum_server::tls_rustls::RustlsConfig;
use base64::{Engine as _, engine::general_purpose::URL_SAFE_NO_PAD};
use futures_util::SinkExt;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::{HashMap, HashSet},
    fs::{self, DirBuilder, OpenOptions, Permissions},
    io::Write,
    net::{IpAddr, SocketAddr},
    os::unix::fs::{DirBuilderExt, FileTypeExt, PermissionsExt},
    path::{Path, PathBuf},
    sync::Arc,
    time::{Duration, Instant},
};
use subtle::ConstantTimeEq;
use tokio::{
    io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader},
    net::{UnixListener, UnixStream},
    sync::{Mutex, Semaphore},
};
use uuid::Uuid;
use web_push::{
    ContentEncoding, IsahcWebPushClient, SubscriptionInfo, Urgency, VapidSignatureBuilder,
    WebPushClient, WebPushError, WebPushMessageBuilder,
};

const MAX_RPC: usize = 2 * 1024 * 1024;
const MAX_PROBE_RESPONSE: u64 = 1024 * 1024;
const PAIR_TTL: Duration = Duration::from_secs(300);
const MAX_DEVICES: usize = 32;
const NOTIFICATION_POLL: Duration = Duration::from_secs(2);
const PUSH_TIMEOUT: Duration = Duration::from_secs(12);

#[derive(Clone)]
struct Gateway(Arc<Inner>);
struct Inner {
    directory: PathBuf,
    probe: PathBuf,
    persisted: Mutex<Persisted>,
    pairing: Mutex<Option<Pairing>>,
    probe_limit: Arc<Semaphore>,
    push_client: IsahcWebPushClient,
}
#[derive(Clone, Serialize, Deserialize)]
struct Persisted {
    gateway_id: Uuid,
    devices: Vec<Device>,
    #[serde(default)]
    vapid_private_key: String,
    #[serde(default)]
    push_subscriptions: Vec<PushSubscription>,
}
#[derive(Clone, Serialize, Deserialize)]
struct Device {
    id: Uuid,
    name: String,
    digest: String,
}
#[derive(Clone, Serialize, Deserialize, PartialEq, Eq)]
struct PushSubscription {
    device_id: Uuid,
    subscription: SubscriptionInfo,
}
struct Pairing {
    digest: [u8; 32],
    kind: PairingKind,
    expires: Instant,
    attempts: u8,
}
#[derive(Clone, Copy)]
enum PairingKind {
    Hex,
    Decimal,
}
#[derive(Deserialize)]
struct PairRequest {
    code: String,
    device_name: String,
}
#[derive(Deserialize)]
struct EventQuery {
    thread_id: String,
    after_sequence: Option<u64>,
}
#[derive(Deserialize)]
struct UnsubscribeRequest {
    endpoint: String,
}
#[derive(Deserialize)]
struct NotificationTestRequest {
    endpoint: String,
}

#[derive(Clone, Default)]
struct ThreadObservation {
    status: String,
    approvals: usize,
    had_error: bool,
}

fn thread_notification(
    previous: &ThreadObservation,
    current: &ThreadObservation,
) -> Option<&'static str> {
    if previous.approvals == 0 && current.approvals > 0 {
        Some("A Zed Agent session needs your approval.")
    } else if !previous.had_error && current.had_error {
        Some("A Zed Agent session failed.")
    } else if previous.status == "Generating" && current.status == "Idle" {
        Some("A Zed Agent session finished.")
    } else {
        None
    }
}

enum PushOutcome {
    Sent,
    Stale,
    Failed,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    match args.first().map(String::as_str) {
        Some("serve") if args.len() == 6 => {
            let address: SocketAddr = args[1].parse().context("invalid listen address")?;
            if !private_ip(address.ip()) {
                bail!("bind a loopback or private address");
            }
            let probe = PathBuf::from(&args[4]);
            let directory = PathBuf::from(&args[5]);
            if !probe.is_absolute() || !directory.is_absolute() {
                bail!("socket and state paths must be absolute");
            }
            if fs::metadata(&args[3])?.permissions().mode() & 0o077 != 0 {
                bail!("TLS private key must be mode 0600 or stricter");
            }
            let tls = RustlsConfig::from_pem_file(&args[2], &args[3]).await?;
            let state = Gateway::load(directory, probe)?;
            let admin = state.clone();
            tokio::spawn(async move {
                if let Err(error) = admin.admin_server().await {
                    eprintln!("admin socket stopped: {error:#}");
                }
            });
            let notifications = state.clone();
            tokio::spawn(async move { notifications.notification_monitor().await });
            let app = Router::new()
                .route("/", get(browser_page))
                .route("/app.js", get(browser_script))
                .route("/style.css", get(browser_style))
                .route("/manifest.webmanifest", get(browser_manifest))
                .route("/service-worker.js", get(browser_service_worker))
                .route("/icons/icon-192.png", get(browser_icon_192))
                .route("/icons/icon-512.png", get(browser_icon_512))
                .route("/v1/gateway", get(info))
                .route("/v1/pair", post(pair))
                .route("/v1/rpc", post(rpc))
                .route("/v1/events", get(events))
                .route("/v1/notifications/config", get(notification_config))
                .route("/v1/notifications/subscribe", post(notification_subscribe))
                .route("/v1/notifications/status", post(notification_status))
                .route(
                    "/v1/notifications/unsubscribe",
                    post(notification_unsubscribe),
                )
                .route("/v1/notifications/test", post(notification_test))
                .layer(DefaultBodyLimit::max(MAX_RPC))
                .with_state(state);
            axum_server::bind_rustls(address, tls)
                .serve(app.into_make_service())
                .await?;
            Ok(())
        }
        Some("admin") if args.len() >= 3 => {
            let command = match args[2].as_str() {
                "pair-code" if args.len() == 3 => json!({"method":"pair-code"}),
                "pair-short-code" if args.len() == 3 => json!({"method":"pair-short-code"}),
                "devices" if args.len() == 3 => json!({"method":"devices"}),
                "revoke" if args.len() == 4 => json!({"method":"revoke","device_id":args[3]}),
                _ => bail!("admin STATE_DIR pair-code|pair-short-code|devices|revoke DEVICE_ID"),
            };
            let mut stream = UnixStream::connect(Path::new(&args[1]).join("admin.sock")).await?;
            stream
                .write_all(serde_json::to_string(&command)?.as_bytes())
                .await?;
            stream.write_all(b"\n").await?;
            let mut response = String::new();
            BufReader::new(stream).read_line(&mut response).await?;
            print!("{response}");
            Ok(())
        }
        _ => bail!(
            "serve PRIVATE_IP:PORT CERT_PEM KEY_PEM PROBE_SOCKET STATE_DIR | admin STATE_DIR pair-code|pair-short-code|devices|revoke DEVICE_ID"
        ),
    }
}
fn static_response(content_type: &'static str, body: &'static str) -> Response {
    let mut response = Response::new(Body::from(body));
    let headers = response.headers_mut();
    headers.insert(header::CONTENT_TYPE, HeaderValue::from_static(content_type));
    headers.insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
    headers.insert(
        HeaderName::from_static("x-content-type-options"),
        HeaderValue::from_static("nosniff"),
    );
    headers.insert(
        HeaderName::from_static("x-frame-options"),
        HeaderValue::from_static("DENY"),
    );
    headers.insert(
        HeaderName::from_static("referrer-policy"),
        HeaderValue::from_static("no-referrer"),
    );
    headers.insert(
        HeaderName::from_static("content-security-policy"),
        HeaderValue::from_static(
            "default-src 'none'; script-src 'self'; worker-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; font-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        ),
    );
    response
}
async fn browser_page() -> Response {
    static_response(
        "text/html; charset=utf-8",
        include_str!("../web/index.html"),
    )
}
async fn browser_script() -> Response {
    static_response(
        "text/javascript; charset=utf-8",
        include_str!("../web/app.js"),
    )
}
async fn browser_style() -> Response {
    static_response("text/css; charset=utf-8", include_str!("../web/style.css"))
}
async fn browser_manifest() -> Response {
    static_response(
        "application/manifest+json; charset=utf-8",
        include_str!("../web/manifest.webmanifest"),
    )
}
async fn browser_service_worker() -> Response {
    static_response(
        "text/javascript; charset=utf-8",
        include_str!("../web/service-worker.js"),
    )
}
fn static_bytes(content_type: &'static str, body: &'static [u8]) -> Response {
    let mut response = Response::new(Body::from(body));
    let headers = response.headers_mut();
    headers.insert(header::CONTENT_TYPE, HeaderValue::from_static(content_type));
    headers.insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
    headers.insert(
        HeaderName::from_static("x-content-type-options"),
        HeaderValue::from_static("nosniff"),
    );
    response
}
async fn browser_icon_192() -> Response {
    static_bytes("image/png", include_bytes!("../web/icons/icon-192.png"))
}
async fn browser_icon_512() -> Response {
    static_bytes("image/png", include_bytes!("../web/icons/icon-512.png"))
}
fn private_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(ip) => {
            ip.is_loopback()
                || ip.is_private()
                || (ip.octets()[0] == 100 && (64..=127).contains(&ip.octets()[1]))
        }
        IpAddr::V6(ip) => ip.is_loopback() || (ip.segments()[0] & 0xfe00 == 0xfc00),
    }
}
fn digest(bytes: &[u8]) -> [u8; 32] {
    let mut hash = Sha256::new();
    hash.update(b"ZedLink gateway credential v1\0");
    hash.update(bytes);
    hash.finalize().into()
}
fn new_vapid_private_key() -> String {
    loop {
        let bytes: [u8; 32] = rand::random();
        let encoded = URL_SAFE_NO_PAD.encode(bytes);
        if VapidSignatureBuilder::from_base64_no_sub(&encoded).is_ok() {
            return encoded;
        }
    }
}

fn valid_subscription(subscription: &SubscriptionInfo) -> bool {
    let public_key = URL_SAFE_NO_PAD.decode(subscription.keys.p256dh.as_bytes());
    let auth = URL_SAFE_NO_PAD.decode(subscription.keys.auth.as_bytes());
    let trusted_endpoint = url::Url::parse(&subscription.endpoint)
        .ok()
        .filter(|endpoint| {
            endpoint.scheme() == "https"
                && endpoint.username().is_empty()
                && endpoint.password().is_none()
                && endpoint.port_or_known_default() == Some(443)
        })
        .and_then(|endpoint| endpoint.host_str().map(str::to_owned))
        .is_some_and(|host| {
            host == "fcm.googleapis.com"
                || host == "push.apple.com"
                || host.ends_with(".push.apple.com")
                || host == "push.services.mozilla.com"
                || host.ends_with(".push.services.mozilla.com")
        });
    trusted_endpoint
        && subscription.endpoint.len() <= 2048
        && !subscription.keys.p256dh.is_empty()
        && subscription.keys.p256dh.len() <= 256
        && !subscription.keys.auth.is_empty()
        && subscription.keys.auth.len() <= 256
        && matches!(public_key.as_deref(), Ok([4, ..]) if public_key.as_ref().is_ok_and(|key| key.len() == 65))
        && auth.as_ref().is_ok_and(|secret| secret.len() == 16)
}
fn save(directory: &Path, state: &Persisted) -> Result<()> {
    let temporary = directory.join(format!("state-{}.tmp", Uuid::new_v4()));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary)?;
    fs::set_permissions(&temporary, Permissions::from_mode(0o600))?;
    file.write_all(&serde_json::to_vec(state)?)?;
    file.sync_all()?;
    fs::rename(&temporary, directory.join("state.json"))?;
    fs::File::open(directory)?.sync_all()?;
    Ok(())
}
impl Gateway {
    fn load(directory: PathBuf, probe: PathBuf) -> Result<Self> {
        let probe_metadata = fs::metadata(&probe).context("native probe socket unavailable")?;
        let probe_parent = fs::metadata(probe.parent().context("probe parent missing")?)?;
        if !probe_metadata.file_type().is_socket()
            || probe_metadata.permissions().mode() & 0o077 != 0
            || !probe_parent.is_dir()
            || probe_parent.permissions().mode() & 0o077 != 0
        {
            bail!("native probe must be in a private directory with private socket permissions");
        }
        if !directory.exists() {
            let mut builder = DirBuilder::new();
            builder.mode(0o700);
            builder.create(&directory)?;
        }
        let metadata = fs::metadata(&directory)?;
        if !metadata.is_dir() || metadata.permissions().mode() & 0o077 != 0 {
            bail!("state directory must be private");
        }
        let file = directory.join("state.json");
        let mut persisted: Persisted = if file.exists() {
            let metadata = fs::metadata(&file)?;
            if !metadata.is_file() || metadata.permissions().mode() & 0o077 != 0 {
                bail!("state file must be private");
            }
            serde_json::from_slice(&fs::read(file)?)?
        } else {
            let initial = Persisted {
                gateway_id: Uuid::new_v4(),
                devices: vec![],
                vapid_private_key: new_vapid_private_key(),
                push_subscriptions: vec![],
            };
            save(&directory, &initial)?;
            initial
        };
        if persisted.vapid_private_key.is_empty() {
            persisted.vapid_private_key = new_vapid_private_key();
            save(&directory, &persisted)?;
        }
        VapidSignatureBuilder::from_base64_no_sub(&persisted.vapid_private_key)
            .context("invalid saved Web Push key")?;
        Ok(Self(Arc::new(Inner {
            directory,
            probe,
            persisted: Mutex::new(persisted),
            pairing: Mutex::new(None),
            probe_limit: Arc::new(Semaphore::new(16)),
            push_client: IsahcWebPushClient::new().context("Web Push client unavailable")?,
        })))
    }
    async fn authorize(&self, headers: &HeaderMap) -> Option<Uuid> {
        let token = headers
            .get("authorization")?
            .to_str()
            .ok()?
            .strip_prefix("Bearer ")?;
        self.authorize_token(token).await
    }
    async fn authorize_token(&self, token: &str) -> Option<Uuid> {
        let bytes = hex::decode(token).ok()?;
        if bytes.len() != 32 {
            return None;
        }
        let hash = digest(&bytes);
        self.0
            .persisted
            .lock()
            .await
            .devices
            .iter()
            .find_map(|device| {
                let stored = hex::decode(&device.digest).ok()?;
                (stored.len() == 32 && bool::from(stored.ct_eq(&hash))).then_some(device.id)
            })
    }
    async fn probe(&self, request: &Value) -> Result<Value> {
        let _permit = self
            .0
            .probe_limit
            .clone()
            .try_acquire_owned()
            .context("probe request limit reached")?;
        let encoded = serde_json::to_vec(request)?;
        if encoded.len() > MAX_RPC {
            bail!("oversized probe request");
        }
        let mut stream =
            tokio::time::timeout(Duration::from_secs(3), UnixStream::connect(&self.0.probe))
                .await??;
        stream.write_all(&encoded).await?;
        stream.write_all(b"\n").await?;
        let mut response = Vec::new();
        tokio::time::timeout(Duration::from_secs(6), async {
            BufReader::new(stream)
                .take(MAX_PROBE_RESPONSE + 1)
                .read_until(b'\n', &mut response)
                .await
        })
        .await??;
        if response.len() as u64 > MAX_PROBE_RESPONSE || !response.ends_with(b"\n") {
            bail!("invalid probe response");
        }
        let response: Value = serde_json::from_slice(&response)?;
        if response["version"] != 1
            || response["request_id"] != request["request_id"]
            || response.get("result").is_some() == response.get("error").is_some()
        {
            bail!("invalid probe response envelope");
        }
        Ok(response)
    }
    async fn admin_server(&self) -> Result<()> {
        let path = self.0.directory.join("admin.sock");
        if path.exists() {
            fs::remove_file(&path)?;
        }
        let listener = UnixListener::bind(&path)?;
        fs::set_permissions(&path, Permissions::from_mode(0o600))?;
        loop {
            let (stream, _) = listener.accept().await?;
            let state = self.clone();
            tokio::spawn(async move {
                if let Err(error) = state.admin_command(stream).await {
                    eprintln!("admin command failed: {error:#}");
                }
            });
        }
    }
    async fn admin_command(&self, stream: UnixStream) -> Result<()> {
        let mut reader = BufReader::new(stream);
        let mut request = Vec::new();
        (&mut reader)
            .take(1025)
            .read_until(b'\n', &mut request)
            .await?;
        if request.len() > 1024 || !request.ends_with(b"\n") {
            bail!("invalid admin request");
        }
        let request: Value = serde_json::from_slice(&request)?;
        let response = match request["method"].as_str() {
            Some("pair-code") => {
                let code: [u8; 32] = rand::random();
                *self.0.pairing.lock().await = Some(Pairing {
                    digest: digest(&code),
                    kind: PairingKind::Hex,
                    expires: Instant::now() + PAIR_TTL,
                    attempts: 0,
                });
                json!({"code":hex::encode(code),"expires_seconds":PAIR_TTL.as_secs()})
            }
            Some("pair-short-code") => {
                let code = format!("{:010}", rand::random_range(0..10_000_000_000_u64));
                *self.0.pairing.lock().await = Some(Pairing {
                    digest: digest(code.as_bytes()),
                    kind: PairingKind::Decimal,
                    expires: Instant::now() + PAIR_TTL,
                    attempts: 0,
                });
                json!({"code":code,"expires_seconds":PAIR_TTL.as_secs()})
            }
            Some("devices") => {
                let persisted = self.0.persisted.lock().await;
                json!({"gateway_id":persisted.gateway_id,
                    "devices":persisted.devices.iter().map(|device| json!({
                        "id":device.id,
                        "name":device.name,
                        "notifications":persisted.push_subscriptions.iter().any(|subscription| subscription.device_id == device.id)
                    })).collect::<Vec<_>>()})
            }
            Some("revoke") => {
                let id =
                    Uuid::parse_str(request["device_id"].as_str().context("device ID missing")?)?;
                let mut persisted = self.0.persisted.lock().await;
                let mut next = persisted.clone();
                let before = next.devices.len();
                next.devices.retain(|device| device.id != id);
                next.push_subscriptions
                    .retain(|subscription| subscription.device_id != id);
                if next.devices.len() != before {
                    save(&self.0.directory, &next)?;
                    *persisted = next;
                }
                json!({"revoked":persisted.devices.len()!=before})
            }
            _ => json!({"error":"INVALID_REQUEST"}),
        };
        let mut stream = reader.into_inner();
        stream
            .write_all(serde_json::to_string(&response)?.as_bytes())
            .await?;
        stream.write_all(b"\n").await?;
        Ok(())
    }

    fn vapid_public_key(&self, persisted: &Persisted) -> Result<String> {
        let builder = VapidSignatureBuilder::from_base64_no_sub(&persisted.vapid_private_key)?;
        Ok(URL_SAFE_NO_PAD.encode(builder.get_public_key()))
    }

    async fn send_push(
        &self,
        record: &PushSubscription,
        body: &str,
        thread_id: Option<&str>,
    ) -> PushOutcome {
        let private_key = self.0.persisted.lock().await.vapid_private_key.clone();
        let signature = match VapidSignatureBuilder::from_base64(&private_key, &record.subscription)
            .and_then(|builder| builder.build())
        {
            Ok(signature) => signature,
            Err(_) => return PushOutcome::Failed,
        };
        let payload = json!({
            "title": "ZedLink",
            "body": body,
            "tag": thread_id.map_or_else(|| "zedlink-test".to_owned(), |id| format!("zedlink-thread-{id}")),
            "thread_id": thread_id,
        });
        let encoded = match serde_json::to_vec(&payload) {
            Ok(encoded) => encoded,
            Err(_) => return PushOutcome::Failed,
        };
        let mut builder = WebPushMessageBuilder::new(&record.subscription);
        builder.set_payload(ContentEncoding::Aes128Gcm, &encoded);
        builder.set_ttl(300);
        builder.set_urgency(Urgency::Normal);
        builder.set_vapid_signature(signature);
        let message = match builder.build() {
            Ok(message) => message,
            Err(_) => return PushOutcome::Failed,
        };
        match tokio::time::timeout(PUSH_TIMEOUT, self.0.push_client.send(message)).await {
            Ok(Ok(())) => PushOutcome::Sent,
            Ok(Err(WebPushError::EndpointNotFound(_) | WebPushError::EndpointNotValid(_))) => {
                PushOutcome::Stale
            }
            _ => PushOutcome::Failed,
        }
    }

    async fn notify_all(&self, body: &'static str, thread_id: &str) {
        let subscriptions = self.0.persisted.lock().await.push_subscriptions.clone();
        let mut stale = HashSet::new();
        for record in subscriptions {
            if matches!(
                self.send_push(&record, body, Some(thread_id)).await,
                PushOutcome::Stale
            ) {
                stale.insert(record.subscription.endpoint);
            }
        }
        if !stale.is_empty() {
            let mut persisted = self.0.persisted.lock().await;
            let mut next = persisted.clone();
            next.push_subscriptions
                .retain(|record| !stale.contains(&record.subscription.endpoint));
            if save(&self.0.directory, &next).is_ok() {
                *persisted = next;
            }
        }
    }

    async fn notification_monitor(&self) {
        let mut prior = HashMap::<String, ThreadObservation>::new();
        let mut interval = tokio::time::interval(NOTIFICATION_POLL);
        loop {
            interval.tick().await;
            if self.0.persisted.lock().await.push_subscriptions.is_empty() {
                prior.clear();
                continue;
            }
            let request = json!({
                "version": 1,
                "request_id": Uuid::new_v4().to_string(),
                "method": "thread.list",
                "params": {},
            });
            let Ok(response) = self.probe(&request).await else {
                continue;
            };
            let Some(threads) = response["result"]["threads"].as_array() else {
                continue;
            };
            let mut current = HashMap::new();
            for thread in threads {
                let (Some(thread_id), Some(status)) =
                    (thread["thread_id"].as_str(), thread["status"].as_str())
                else {
                    continue;
                };
                let snapshot_request = json!({
                    "version": 1,
                    "request_id": Uuid::new_v4().to_string(),
                    "method": "thread.snapshot",
                    "params": {"thread_id": thread_id},
                });
                let approvals = self
                    .probe(&snapshot_request)
                    .await
                    .ok()
                    .and_then(|snapshot| {
                        snapshot["result"]["pending_approvals"]
                            .as_array()
                            .map(Vec::len)
                    })
                    .unwrap_or(0);
                let observation = ThreadObservation {
                    status: status.to_owned(),
                    approvals,
                    had_error: thread["had_error"].as_bool().unwrap_or(false),
                };
                if let Some(previous) = prior.get(thread_id)
                    && let Some(body) = thread_notification(previous, &observation)
                {
                    self.notify_all(body, thread_id).await;
                }
                current.insert(thread_id.to_owned(), observation);
            }
            prior = current;
        }
    }
}
async fn info(State(state): State<Gateway>) -> Json<Value> {
    Json(json!({"version":1,"gateway_id":state.0.persisted.lock().await.gateway_id}))
}
async fn pair(State(state): State<Gateway>, Json(request): Json<PairRequest>) -> impl IntoResponse {
    if request.device_name.trim().is_empty() || request.device_name.len() > 64 {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error":"INVALID_REQUEST"})),
        );
    }
    let mut pairing = state.0.pairing.lock().await;
    let Some(active) = pairing.as_mut() else {
        return (
            StatusCode::FORBIDDEN,
            Json(json!({"error":"PAIRING_UNAVAILABLE"})),
        );
    };
    if Instant::now() >= active.expires || active.attempts >= 5 {
        *pairing = None;
        return (
            StatusCode::FORBIDDEN,
            Json(json!({"error":"PAIRING_EXPIRED"})),
        );
    }
    active.attempts += 1;
    let valid = match active.kind {
        PairingKind::Hex => {
            let decoded = hex::decode(&request.code).unwrap_or_default();
            decoded.len() == 32 && bool::from(active.digest.ct_eq(&digest(&decoded)))
        }
        PairingKind::Decimal => {
            request.code.len() == 10
                && request.code.bytes().all(|byte| byte.is_ascii_digit())
                && bool::from(active.digest.ct_eq(&digest(request.code.as_bytes())))
        }
    };
    if !valid {
        return (
            StatusCode::FORBIDDEN,
            Json(json!({"error":"PAIRING_INVALID"})),
        );
    }
    let mut persisted = state.0.persisted.lock().await;
    if persisted.devices.len() >= MAX_DEVICES {
        return (
            StatusCode::TOO_MANY_REQUESTS,
            Json(json!({"error":"RATE_LIMITED"})),
        );
    }
    let token: [u8; 32] = rand::random();
    let id = Uuid::new_v4();
    let mut next = persisted.clone();
    next.devices.push(Device {
        id,
        name: request.device_name,
        digest: hex::encode(digest(&token)),
    });
    if save(&state.0.directory, &next).is_err() {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error":"INTERNAL_ERROR"})),
        );
    }
    *persisted = next;
    *pairing = None;
    (
        StatusCode::OK,
        Json(json!({"device_id":id,"token":hex::encode(token),"gateway_id":persisted.gateway_id})),
    )
}

async fn notification_config(
    State(state): State<Gateway>,
    headers: HeaderMap,
) -> impl IntoResponse {
    let Some(device_id) = state.authorize(&headers).await else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({"error":"UNAUTHENTICATED"})),
        );
    };
    let persisted = state.0.persisted.lock().await;
    let public_key = match state.vapid_public_key(&persisted) {
        Ok(public_key) => public_key,
        Err(_) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"error":"INTERNAL_ERROR"})),
            );
        }
    };
    let enabled = persisted
        .push_subscriptions
        .iter()
        .any(|subscription| subscription.device_id == device_id);
    (
        StatusCode::OK,
        Json(json!({
            "version": 1,
            "supported": true,
            "enabled": enabled,
            "application_server_key": public_key,
        })),
    )
}

async fn notification_subscribe(
    State(state): State<Gateway>,
    headers: HeaderMap,
    Json(subscription): Json<SubscriptionInfo>,
) -> impl IntoResponse {
    let Some(device_id) = state.authorize(&headers).await else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({"error":"UNAUTHENTICATED"})),
        );
    };
    if !valid_subscription(&subscription) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error":"INVALID_SUBSCRIPTION"})),
        );
    }
    let mut persisted = state.0.persisted.lock().await;
    let mut next = persisted.clone();
    next.push_subscriptions
        .retain(|record| record.subscription.endpoint != subscription.endpoint);
    next.push_subscriptions.push(PushSubscription {
        device_id,
        subscription,
    });
    if save(&state.0.directory, &next).is_err() {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error":"INTERNAL_ERROR"})),
        );
    }
    *persisted = next;
    (StatusCode::OK, Json(json!({"enabled":true})))
}

async fn notification_unsubscribe(
    State(state): State<Gateway>,
    headers: HeaderMap,
    Json(request): Json<UnsubscribeRequest>,
) -> impl IntoResponse {
    let Some(device_id) = state.authorize(&headers).await else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({"error":"UNAUTHENTICATED"})),
        );
    };
    if request.endpoint.is_empty() || request.endpoint.len() > 2048 {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error":"INVALID_REQUEST"})),
        );
    }
    let mut persisted = state.0.persisted.lock().await;
    let mut next = persisted.clone();
    next.push_subscriptions.retain(|record| {
        record.device_id != device_id || record.subscription.endpoint != request.endpoint
    });
    if save(&state.0.directory, &next).is_err() {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error":"INTERNAL_ERROR"})),
        );
    }
    *persisted = next;
    (StatusCode::OK, Json(json!({"enabled":false})))
}

async fn notification_status(
    State(state): State<Gateway>,
    headers: HeaderMap,
    Json(request): Json<UnsubscribeRequest>,
) -> impl IntoResponse {
    let Some(device_id) = state.authorize(&headers).await else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({"error":"UNAUTHENTICATED"})),
        );
    };
    if request.endpoint.is_empty() || request.endpoint.len() > 2048 {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error":"INVALID_REQUEST"})),
        );
    }
    let enabled = state
        .0
        .persisted
        .lock()
        .await
        .push_subscriptions
        .iter()
        .any(|record| {
            record.device_id == device_id && record.subscription.endpoint == request.endpoint
        });
    (StatusCode::OK, Json(json!({"enabled":enabled})))
}

async fn notification_test(
    State(state): State<Gateway>,
    headers: HeaderMap,
    Json(request): Json<NotificationTestRequest>,
) -> impl IntoResponse {
    let Some(device_id) = state.authorize(&headers).await else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({"error":"UNAUTHENTICATED"})),
        );
    };
    let subscription = state
        .0
        .persisted
        .lock()
        .await
        .push_subscriptions
        .iter()
        .find(|record| {
            record.device_id == device_id && record.subscription.endpoint == request.endpoint
        })
        .cloned();
    let Some(subscription) = subscription else {
        return (
            StatusCode::CONFLICT,
            Json(json!({"error":"NOTIFICATIONS_DISABLED"})),
        );
    };
    match state
        .send_push(
            &subscription,
            "Notifications are ready for this device.",
            None,
        )
        .await
    {
        PushOutcome::Sent => (StatusCode::OK, Json(json!({"delivered":true}))),
        PushOutcome::Stale => (
            StatusCode::GONE,
            Json(json!({"error":"SUBSCRIPTION_EXPIRED"})),
        ),
        PushOutcome::Failed => (
            StatusCode::BAD_GATEWAY,
            Json(json!({"error":"PUSH_DELIVERY_FAILED"})),
        ),
    }
}

async fn rpc(State(state): State<Gateway>, headers: HeaderMap, body: Bytes) -> impl IntoResponse {
    let Some(device_id) = state.authorize(&headers).await else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({"error":"UNAUTHENTICATED"})),
        );
    };
    if body.len() > MAX_RPC {
        return (
            StatusCode::PAYLOAD_TOO_LARGE,
            Json(json!({"error":"PAYLOAD_TOO_LARGE"})),
        );
    }
    let mut request: Value = match serde_json::from_slice(&body) {
        Ok(request) => request,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error":"INVALID_REQUEST"})),
            );
        }
    };
    let Some(method) = request["method"].as_str().map(str::to_owned) else {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error":"INVALID_REQUEST"})),
        );
    };
    if !matches!(
        method.as_str(),
        "instance.info"
            | "thread.list"
            | "thread.create"
            | "thread.snapshot"
            | "thread.events"
            | "thread.commands"
            | "thread.settings"
            | "thread.settings.update"
            | "thread.approvals"
            | "approval.respond"
            | "project.files"
            | "project.file"
            | "project.search"
            | "changes.snapshot"
            | "changes.diff"
            | "changes.stage"
            | "changes.unstage"
            | "thread.send"
            | "thread.cancel"
            | "request.status"
    ) {
        return (
            StatusCode::FORBIDDEN,
            Json(json!({"error":"UNSUPPORTED_CAPABILITY"})),
        );
    }
    let Some(original_request_id) = request["request_id"]
        .as_str()
        .filter(|id| !id.is_empty() && id.len() <= 80)
        .map(str::to_owned)
    else {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error":"INVALID_REQUEST"})),
        );
    };
    if matches!(
        method.as_str(),
        "thread.send" | "thread.create" | "changes.stage" | "changes.unstage"
    ) {
        request["request_id"] = json!(format!("{device_id}:{original_request_id}"));
    } else if method == "request.status" {
        let Some(original_send_id) = request["params"]["original_request_id"]
            .as_str()
            .filter(|id| !id.is_empty() && id.len() <= 80)
            .map(str::to_owned)
        else {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error":"INVALID_REQUEST"})),
            );
        };
        request["params"]["original_request_id"] = json!(format!("{device_id}:{original_send_id}"));
    }
    match state.probe(&request).await {
        Ok(mut response) => {
            response["request_id"] = json!(original_request_id);
            (StatusCode::OK, Json(response))
        }
        Err(_) => (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"error":"INSTANCE_UNAVAILABLE"})),
        ),
    }
}
async fn events(
    State(state): State<Gateway>,
    headers: HeaderMap,
    Query(query): Query<EventQuery>,
    upgrade: WebSocketUpgrade,
) -> impl IntoResponse {
    let websocket_token = headers
        .get(header::SEC_WEBSOCKET_PROTOCOL)
        .and_then(|value| value.to_str().ok())
        .and_then(|value| {
            value
                .split(',')
                .map(str::trim)
                .find_map(|protocol| protocol.strip_prefix("zedlink-token-").map(str::to_owned))
        });
    let device_id = if let Some(device_id) = state.authorize(&headers).await {
        Some(device_id)
    } else if let Some(token) = websocket_token.as_deref() {
        state.authorize_token(token).await
    } else {
        None
    };
    let Some(device_id) = device_id else {
        return StatusCode::UNAUTHORIZED.into_response();
    };
    if query.thread_id.is_empty() || query.thread_id.len() > 128 {
        return StatusCode::BAD_REQUEST.into_response();
    }
    upgrade
        .protocols(["zedlink-v1"])
        .on_upgrade(move |socket| event_stream(socket, state, device_id, query))
        .into_response()
}
async fn event_stream(mut socket: WebSocket, state: Gateway, device_id: Uuid, query: EventQuery) {
    let mut sequence = query.after_sequence.unwrap_or(0);
    let mut interval = tokio::time::interval(Duration::from_millis(250));
    loop {
        interval.tick().await;
        if !state
            .0
            .persisted
            .lock()
            .await
            .devices
            .iter()
            .any(|device| device.id == device_id)
        {
            break;
        }
        let request = json!({"version":1,"request_id":Uuid::new_v4().to_string(),
            "method":"thread.events","params":{"thread_id":query.thread_id,"after_sequence":sequence}});
        let response = match state.probe(&request).await {
            Ok(response) => response,
            Err(_) => json!({"version":1,"error":{"code":"INSTANCE_UNAVAILABLE"}}),
        };
        if let Some(next) = response["result"]["last_sequence"].as_u64() {
            sequence = next;
        }
        let stop = response.get("error").is_some();
        if tokio::time::timeout(
            Duration::from_secs(5),
            socket.send(Message::Text(response.to_string().into())),
        )
        .await
        .map_or(true, |result| result.is_err())
            || stop
        {
            break;
        }
    }
    if let Err(error) = socket.close().await {
        eprintln!("event stream close failed: {error}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn creates_stable_vapid_key_pair() {
        let private_key = new_vapid_private_key();
        let first = VapidSignatureBuilder::from_base64_no_sub(&private_key).unwrap();
        let second = VapidSignatureBuilder::from_base64_no_sub(&private_key).unwrap();
        assert_eq!(first.get_public_key(), second.get_public_key());
        assert_eq!(first.get_public_key().len(), 65);
    }

    #[test]
    fn validates_web_push_subscription_shape() {
        let subscription = SubscriptionInfo::new(
            "https://fcm.googleapis.com/device".to_owned(),
            URL_SAFE_NO_PAD.encode([4_u8].into_iter().chain([7_u8; 64]).collect::<Vec<_>>()),
            URL_SAFE_NO_PAD.encode([9_u8; 16]),
        );
        assert!(valid_subscription(&subscription));

        let mut insecure = subscription.clone();
        insecure.endpoint = "http://push.example.test/device".into();
        assert!(!valid_subscription(&insecure));

        let mut private_endpoint = subscription.clone();
        private_endpoint.endpoint = "https://127.0.0.1/device".into();
        assert!(!valid_subscription(&private_endpoint));

        let mut malformed = subscription;
        malformed.keys.p256dh = URL_SAFE_NO_PAD.encode([4_u8; 32]);
        assert!(!valid_subscription(&malformed));
    }

    #[test]
    fn loads_state_from_before_notifications() {
        let gateway_id = Uuid::new_v4();
        let state: Persisted = serde_json::from_value(json!({
            "gateway_id": gateway_id,
            "devices": [],
        }))
        .unwrap();
        assert_eq!(state.gateway_id, gateway_id);
        assert!(state.vapid_private_key.is_empty());
        assert!(state.push_subscriptions.is_empty());
    }

    #[test]
    fn chooses_failure_notification_before_generic_completion() {
        let generating = ThreadObservation {
            status: "Generating".into(),
            approvals: 0,
            had_error: false,
        };
        let failed = ThreadObservation {
            status: "Idle".into(),
            approvals: 0,
            had_error: true,
        };
        assert_eq!(
            thread_notification(&generating, &failed),
            Some("A Zed Agent session failed.")
        );
        assert_eq!(thread_notification(&failed, &failed), None);
    }
}
