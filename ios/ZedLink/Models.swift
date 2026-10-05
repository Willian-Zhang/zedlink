import Foundation

enum RouteKind: String, CaseIterable, Codable, Identifiable {
    case tailscale = "Tailscale"
    case wireGuard = "WireGuard"
    case otherVPN = "Other VPN"
    case local = "Local HTTPS"
    case custom = "Custom HTTPS"

    var id: String { rawValue }

    var guidance: String {
        switch self {
        case .tailscale: "Connect your existing Tailscale app, then enter the workstation's verified HTTPS hostname."
        case .wireGuard: "Connect your existing WireGuard tunnel and enter a hostname routed to the workstation."
        case .otherVPN: "Connect a VPN that routes to the workstation, then enter its HTTPS address."
        case .local: "Join the same trusted local network and use a certificate valid for the entered hostname."
        case .custom: "Enter the HTTPS address of a trusted reverse proxy that forwards ZedLink API requests."
        }
    }
}

struct ConnectionProfile: Codable, Identifiable, Equatable {
    var id: UUID = UUID()
    var name: String
    var route: RouteKind
    var endpoint: String
    var gatewayID: String
}

struct NativeThread: Identifiable, Equatable {
    let id: String
    let title: String
    let status: String
    let currentTurnID: Int?
}

struct ThreadSnapshot {
    let threadID: String
    let title: String
    let status: String
    let currentTurnID: Int?
    let instanceID: String
    let epoch: String
    let lastSequence: Int
    let entries: [String]
    let truncated: Bool
    let pendingApprovalCount: Int
}

struct PendingSend: Codable {
    let id: String
    let instanceID: String
    let epoch: String
    let threadID: String
    // A draft remains in memory only. A relaunched app reconciles by ID without resending.
    var text: String?

    enum CodingKeys: String, CodingKey { case id, instanceID, epoch, threadID }
}

enum LinkState: Equatable {
    case offline
    case connecting
    case live
    case reconnecting
    case stale

    var label: String {
        switch self {
        case .offline: "Offline"
        case .connecting: "Connecting"
        case .live: "Live"
        case .reconnecting: "Reconnecting"
        case .stale: "Stale"
        }
    }
}
