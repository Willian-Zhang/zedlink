import SwiftUI
import UIKit

enum ZLTheme {
    static let background = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(red: 0.025, green: 0.027, blue: 0.03, alpha: 1) : .systemBackground
    })
    static let surface = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(red: 0.055, green: 0.059, blue: 0.065, alpha: 1) : .secondarySystemBackground
    })
    static let raised = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(red: 0.085, green: 0.09, blue: 0.098, alpha: 1) : .tertiarySystemBackground
    })
    static let line = Color(uiColor: UIColor { traits in
        traits.userInterfaceStyle == .dark ? UIColor(white: 0.18, alpha: 1) : .separator
    })
    static let muted = Color(uiColor: .secondaryLabel)
    static let healthy = Color(red: 0.43, green: 0.78, blue: 0.58)
    static let warning = Color(red: 0.9, green: 0.68, blue: 0.34)
    static let danger = Color(red: 0.92, green: 0.38, blue: 0.4)
    static let focus = Color(red: 0.39, green: 0.67, blue: 0.98)
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
