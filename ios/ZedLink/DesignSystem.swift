import SwiftUI
import UIKit

enum ZLTheme {
    static let background = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(red: 0, green: 0, blue: 0, alpha: 1) : .systemBackground
    })
    static let surface = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(red: 13 / 255, green: 14 / 255, blue: 16 / 255, alpha: 1) : .secondarySystemBackground
    })
    static let raised = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(red: 21 / 255, green: 23 / 255, blue: 25 / 255, alpha: 1) : .tertiarySystemBackground
    })
    static let line = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(red: 43 / 255, green: 45 / 255, blue: 48 / 255, alpha: 1) : .separator
    })
    static let ink = Color(red: 243 / 255, green: 243 / 255, blue: 241 / 255)
    static let muted = Color(red: 162 / 255, green: 165 / 255, blue: 170 / 255)
    static let subtle = Color(red: 121 / 255, green: 124 / 255, blue: 130 / 255)
    static let healthy = Color(red: 121 / 255, green: 199 / 255, blue: 155 / 255)
    static let warning = Color(red: 226 / 255, green: 188 / 255, blue: 128 / 255)
    static let danger = Color(red: 0.92, green: 0.38, blue: 0.4)
    static let focus = Color(red: 213 / 255, green: 231 / 255, blue: 1)
}

@MainActor func dismissZedLinkKeyboard() {
    UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
}

struct Hairline: View {
    var body: some View { Rectangle().fill(ZLTheme.line).frame(height: 1 / UIScreen.main.scale) }
}

struct ConnectionStatusView: View {
    let state: LinkState

    private var color: Color {
        switch state {
        case .live: ZLTheme.healthy
        case .connecting, .reconnecting: ZLTheme.warning
        case .offline, .stale: ZLTheme.danger
        }
    }

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: state.symbol).font(.system(size: 8, weight: .bold))
            Text(state.label).font(.caption.monospaced().weight(.medium))
        }
        .foregroundStyle(color)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Connection \(state.label)")
    }
}

struct SectionLabel: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text.uppercased())
            .font(.caption2.monospaced().weight(.semibold))
            .tracking(1.1)
            .foregroundStyle(ZLTheme.muted)
    }
}
