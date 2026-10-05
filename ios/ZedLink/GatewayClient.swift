import Foundation

enum GatewayFailure: LocalizedError {
    case invalidEndpoint
    case invalidResponse
    case changedIdentity
    case redirected
    case status(Int)
    case native(String)

    var errorDescription: String? {
        switch self {
        case .invalidEndpoint: "Enter a valid HTTPS address without credentials, query, or fragment."
        case .invalidResponse: "The gateway sent an unexpected response."
        case .changedIdentity: "Gateway identity changed. No device credential was sent."
        case .redirected: "The endpoint redirected. Check the saved address before reconnecting."
        case .status(let status): "Gateway returned HTTP \(status)."
        case .native(let code):
            switch code {
            case "UNAUTHENTICATED": "Device pairing is missing or revoked."
            case "THREAD_NOT_EXPOSED": "This thread is no longer exposed in desktop Zed."
            case "INSTANCE_UNAVAILABLE": "Desktop Zed is unavailable."
            case "RESYNC_REQUIRED": "Event history changed; refreshing the native snapshot."
            default: code
            }
        }
    }
}

private final class NoRedirect: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest) async -> URLRequest? { nil }
}

struct GatewayClient {
    private static let redirectDelegate = NoRedirect()
    private static let session = URLSession(configuration: .ephemeral, delegate: redirectDelegate, delegateQueue: nil)
    let profile: ConnectionProfile
    let token: String?

    private var base: URL {
        get throws {
            guard let url = URL(string: profile.endpoint),
                  let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
                  components.scheme == "https", components.host != nil,
                  components.user == nil, components.password == nil,
                  components.query == nil, components.fragment == nil else {
                throw GatewayFailure.invalidEndpoint
            }
            return url
        }
    }

    private func address(_ path: String) throws -> URL {
        let root = try base.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let result = URL(string: root + path) else { throw GatewayFailure.invalidEndpoint }
        return result
    }

    private func call(_ path: String, payload: [String: Any]? = nil, authorized: Bool = false) async throws -> [String: Any] {
        var request = URLRequest(url: try address(path))
        request.timeoutInterval = 12
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.httpMethod = payload == nil ? "GET" : "POST"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let payload {
            request.httpBody = try JSONSerialization.data(withJSONObject: payload)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if authorized {
            guard let token else { throw GatewayFailure.native("UNAUTHENTICATED") }
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await Self.session.data(for: request)
        } catch let error as URLError {
            switch error.code {
            case .notConnectedToInternet:
                throw GatewayFailure.native("No network connection. Check the phone's network settings.")
            case .cannotFindHost, .dnsLookupFailed:
                throw GatewayFailure.native("Gateway name could not be resolved. Check the saved hostname and VPN DNS route.")
            case .timedOut, .cannotConnectToHost, .networkConnectionLost:
                throw GatewayFailure.native("Gateway unreachable. Check the VPN connection, address, and route.")
            case .serverCertificateUntrusted, .serverCertificateHasUnknownRoot,
                 .serverCertificateHasBadDate, .serverCertificateNotYetValid,
                 .secureConnectionFailed:
                throw GatewayFailure.native("HTTPS identity could not be verified. Check the hostname and certificate.")
            default:
                throw error
            }
        }
        guard let http = response as? HTTPURLResponse else { throw GatewayFailure.invalidResponse }
        if (300..<400).contains(http.statusCode) { throw GatewayFailure.redirected }
        guard data.count <= 1_048_576,
              let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw GatewayFailure.invalidResponse
        }
        guard http.statusCode == 200 else {
            throw GatewayFailure.native(object["error"] as? String ?? "HTTP \(http.statusCode)")
        }
        return object
    }

    func gatewayID() async throws -> String {
        let object = try await call("/v1/gateway")
        guard object["version"] as? Int == 1, let id = object["gateway_id"] as? String else {
            throw GatewayFailure.invalidResponse
        }
        return id
    }

    func verifyIdentity() async throws {
        guard try await gatewayID() == profile.gatewayID else { throw GatewayFailure.changedIdentity }
    }

    func pair(code: String, deviceName: String) async throws -> (deviceID: String, token: String) {
        try await verifyIdentity()
        let object = try await call("/v1/pair", payload: ["code": code, "device_name": deviceName])
        guard object["gateway_id"] as? String == profile.gatewayID,
              let deviceID = object["device_id"] as? String,
              let token = object["token"] as? String, token.count == 64 else {
            throw GatewayFailure.invalidResponse
        }
        return (deviceID, token)
    }

    func rpc(_ method: String, params: [String: Any] = [:], requestID: String = UUID().uuidString) async throws -> [String: Any] {
        // Recheck before every authenticated call. A changed endpoint never receives the token.
        try await verifyIdentity()
        let envelope: [String: Any] = ["version": 1, "request_id": requestID, "method": method, "params": params]
        let object = try await call("/v1/rpc", payload: envelope, authorized: true)
        guard object["version"] as? Int == 1, object["request_id"] as? String == requestID else {
            throw GatewayFailure.invalidResponse
        }
        if let error = object["error"] as? [String: Any], let code = error["code"] as? String {
            throw GatewayFailure.native(code)
        }
        guard let result = object["result"] as? [String: Any] else { throw GatewayFailure.invalidResponse }
        return result
    }
}
