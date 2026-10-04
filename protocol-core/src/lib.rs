//! Transport-independent, provisional ZedLink protocol rules.
//!
//! This crate does not connect to Zed or grant authority. The native adapter must
//! own submission acceptance, exposure checks, and event serialization.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashMap, VecDeque};

pub const VERSION: u8 = 1;
pub const MAX_REQUEST_BYTES: usize = 64 * 1024;

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub version: u8,
    pub request_id: String,
    pub method: String,
    pub params: Value,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Response {
    pub version: u8,
    pub request_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<ProtocolError>,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ProtocolError {
    pub code: ErrorCode,
    pub message: String,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum ErrorCode {
    Unauthenticated,
    Forbidden,
    InstanceUnavailable,
    ThreadNotFound,
    ThreadNotExposed,
    UnsupportedCapability,
    VersionMismatch,
    InvalidRequest,
    RequestIdConflict,
    DeliveryUnknown,
    ResyncRequired,
    StaleTurn,
    ApprovalExpired,
    ApprovalAlreadyResolved,
    PayloadTooLarge,
    RateLimited,
    InternalError,
}

impl Response {
    pub fn success(request_id: String, result: Value) -> Self {
        Self {
            version: VERSION,
            request_id,
            result: Some(result),
            error: None,
        }
    }

    pub fn failure(request_id: String, code: ErrorCode, message: String) -> Self {
        Self {
            version: VERSION,
            request_id,
            result: None,
            error: Some(ProtocolError { code, message }),
        }
    }

    pub fn is_valid(&self) -> bool {
        self.version == VERSION && self.result.is_some() != self.error.is_some()
    }
}

pub fn parse_request(bytes: &[u8]) -> Result<Request, ErrorCode> {
    if bytes.len() > MAX_REQUEST_BYTES {
        return Err(ErrorCode::PayloadTooLarge);
    }
    let request: Request = serde_json::from_slice(bytes).map_err(|_| ErrorCode::InvalidRequest)?;
    if request.version != VERSION {
        return Err(ErrorCode::VersionMismatch);
    }
    if request.request_id.is_empty()
        || request.request_id.len() > 128
        || request.method.is_empty()
        || request.method.len() > 64
        || !request.params.is_object()
    {
        return Err(ErrorCode::InvalidRequest);
    }
    Ok(request)
}

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct RequestKey {
    pub device_id: String,
    pub instance_id: String,
    pub request_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Acceptance {
    pub message_id: String,
    pub turn_id: String,
    pub queued: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AcceptanceStatus {
    Accepted(Acceptance),
    Conflict,
    Unknown,
}

struct LedgerEntry {
    digest: [u8; 32],
    acceptance: Acceptance,
}

/// A bounded in-memory building block. The native adapter must serialize check,
/// native acceptance, and record; a restart or eviction yields Unknown.
pub struct AcceptanceLedger {
    entries: HashMap<RequestKey, LedgerEntry>,
    order: VecDeque<RequestKey>,
    capacity: usize,
}

impl AcceptanceLedger {
    pub fn new(capacity: usize) -> Self {
        Self {
            entries: HashMap::new(),
            order: VecDeque::new(),
            capacity,
        }
    }

    pub fn status(&self, key: &RequestKey) -> AcceptanceStatus {
        self.entries
            .get(key)
            .map_or(AcceptanceStatus::Unknown, |entry| {
                AcceptanceStatus::Accepted(entry.acceptance.clone())
            })
    }

    pub fn check(&self, key: &RequestKey, thread_id: &str, text: &str) -> AcceptanceStatus {
        self.entries
            .get(key)
            .map_or(AcceptanceStatus::Unknown, |entry| {
                if entry.digest == digest(thread_id, text) {
                    AcceptanceStatus::Accepted(entry.acceptance.clone())
                } else {
                    AcceptanceStatus::Conflict
                }
            })
    }

    /// Call only after the native submission path confirms acceptance.
    pub fn record_accepted(
        &mut self,
        key: RequestKey,
        thread_id: &str,
        text: &str,
        acceptance: Acceptance,
    ) -> AcceptanceStatus {
        if self.capacity == 0 {
            return AcceptanceStatus::Unknown;
        }
        match self.check(&key, thread_id, text) {
            AcceptanceStatus::Unknown => {}
            other => return other,
        }
        if self.entries.len() == self.capacity {
            if let Some(oldest) = self.order.pop_front() {
                self.entries.remove(&oldest);
            }
        }
        self.order.push_back(key.clone());
        self.entries.insert(
            key,
            LedgerEntry {
                digest: digest(thread_id, text),
                acceptance: acceptance.clone(),
            },
        );
        AcceptanceStatus::Accepted(acceptance)
    }
}

fn digest(thread_id: &str, text: &str) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update((thread_id.len() as u64).to_be_bytes());
    hasher.update(thread_id.as_bytes());
    hasher.update(text.as_bytes());
    hasher.finalize().into()
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Message {
    pub id: String,
    pub text: String,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Snapshot {
    pub instance_id: String,
    pub epoch: String,
    pub thread_id: String,
    pub seq: u64,
    pub messages: BTreeMap<String, Message>,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Event {
    pub instance_id: String,
    pub epoch: String,
    pub thread_id: String,
    pub seq: u64,
    pub change: Change,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "type", content = "payload", rename_all = "snake_case")]
pub enum Change {
    MessageUpsert(Message),
    MessageRemoved { id: String },
    ResyncRequired,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ApplyResult {
    Applied,
    Duplicate,
    ResyncRequired,
}

/// Pure client projection. A native adapter must provide a consistent snapshot
/// and sequence events at the same application-state serialization boundary.
impl Snapshot {
    pub fn apply(&mut self, event: Event) -> ApplyResult {
        if self.instance_id != event.instance_id
            || self.epoch != event.epoch
            || self.thread_id != event.thread_id
        {
            return ApplyResult::ResyncRequired;
        }
        if event.seq <= self.seq {
            return ApplyResult::Duplicate;
        }
        if self.seq.checked_add(1) != Some(event.seq) {
            return ApplyResult::ResyncRequired;
        }
        match event.change {
            Change::MessageUpsert(message) => {
                self.messages.insert(message.id.clone(), message);
            }
            Change::MessageRemoved { id } => {
                self.messages.remove(&id);
            }
            Change::ResyncRequired => return ApplyResult::ResyncRequired,
        }
        self.seq = event.seq;
        ApplyResult::Applied
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn key(id: &str) -> RequestKey {
        RequestKey {
            device_id: "device".into(),
            instance_id: "instance".into(),
            request_id: id.into(),
        }
    }

    #[test]
    fn request_bounds_and_version() {
        let valid = br#"{"version":1,"request_id":"r","method":"thread.send","params":{}}"#;
        assert!(parse_request(valid).is_ok());
        assert_eq!(
            parse_request(&vec![b' '; MAX_REQUEST_BYTES + 1]),
            Err(ErrorCode::PayloadTooLarge)
        );
        let old = br#"{"version":2,"request_id":"r","method":"thread.send","params":{}}"#;
        assert_eq!(parse_request(old), Err(ErrorCode::VersionMismatch));
    }

    #[test]
    fn response_has_exactly_one_outcome() {
        let result = Response::success("r".into(), Value::Null);
        assert!(result.is_valid());
        assert!(Response::failure("r".into(), ErrorCode::Forbidden, "denied".into()).is_valid());
        assert!(!Response {
            error: result.error.clone(),
            result: None,
            ..result
        }
        .is_valid());
    }

    #[test]
    fn acceptance_is_scoped_and_never_guessed_after_eviction() {
        let mut ledger = AcceptanceLedger::new(1);
        let accepted = Acceptance {
            message_id: "m1".into(),
            turn_id: "t1".into(),
            queued: false,
        };
        assert_eq!(
            ledger.check(&key("r1"), "thread", "hello"),
            AcceptanceStatus::Unknown
        );
        assert_eq!(
            ledger.record_accepted(key("r1"), "thread", "hello", accepted.clone()),
            AcceptanceStatus::Accepted(accepted.clone())
        );
        assert_eq!(
            ledger.check(&key("r1"), "thread", "hello"),
            AcceptanceStatus::Accepted(accepted.clone())
        );
        assert_eq!(
            ledger.check(&key("r1"), "thread", "changed"),
            AcceptanceStatus::Conflict
        );
        assert_eq!(
            ledger.check(&key("r1"), "other-thread", "hello"),
            AcceptanceStatus::Conflict
        );
        let different_device = RequestKey {
            device_id: "other".into(),
            ..key("r1")
        };
        assert_eq!(
            ledger.check(&different_device, "thread", "hello"),
            AcceptanceStatus::Unknown
        );
        ledger.record_accepted(key("r2"), "thread", "next", accepted);
        assert_eq!(ledger.status(&key("r1")), AcceptanceStatus::Unknown);
    }

    #[test]
    fn replay_deduplicates_and_detects_epoch_or_sequence_gaps() {
        let mut snapshot = Snapshot {
            instance_id: "i".into(),
            epoch: "e1".into(),
            thread_id: "t".into(),
            seq: 4,
            messages: BTreeMap::new(),
        };
        let event = Event {
            instance_id: "i".into(),
            epoch: "e1".into(),
            thread_id: "t".into(),
            seq: 5,
            change: Change::MessageUpsert(Message {
                id: "m".into(),
                text: "hello".into(),
            }),
        };
        assert_eq!(snapshot.apply(event.clone()), ApplyResult::Applied);
        assert_eq!(snapshot.apply(event.clone()), ApplyResult::Duplicate);
        assert_eq!(snapshot.messages.len(), 1);
        assert_eq!(
            snapshot.apply(Event {
                seq: 7,
                ..event.clone()
            }),
            ApplyResult::ResyncRequired
        );
        assert_eq!(
            snapshot.apply(Event {
                epoch: "e2".into(),
                seq: 6,
                ..event
            }),
            ApplyResult::ResyncRequired
        );
        assert_eq!(snapshot.seq, 5);
    }
}
