import SwiftUI
import UIKit

enum ZLTheme {
    static let background = Color(uiColor: UIColor { traits in
        if traits.accessibilityContrast == .high { return .systemBackground }
        return traits.userInterfaceStyle == .dark ? UIColor(red: 0, green: 0, blue: 0, alpha: 1) : .systemBackground
    })
    static let surface = Color(uiColor: UIColor { traits in
        if traits.accessibilityContrast == .high { return .secondarySystemBackground }
        return traits.userInterfaceStyle == .dark ? UIColor(red: 13 / 255, green: 14 / 255, blue: 16 / 255, alpha: 1) : .secondarySystemBackground
    })
    static let raised = Color(uiColor: UIColor { traits in
        if traits.accessibilityContrast == .high { return .tertiarySystemBackground }
        return traits.userInterfaceStyle == .dark ? UIColor(red: 21 / 255, green: 23 / 255, blue: 25 / 255, alpha: 1) : .tertiarySystemBackground
    })
    static let line = Color(uiColor: UIColor { traits in
        if traits.accessibilityContrast == .high { return .separator }
        return traits.userInterfaceStyle == .dark ? UIColor(red: 43 / 255, green: 45 / 255, blue: 48 / 255, alpha: 1) : .separator
    })
    static let ink = Color(uiColor: .label)
    static let muted = Color(uiColor: UIColor { traits in
        if traits.accessibilityContrast == .high { return .secondaryLabel }
        return traits.userInterfaceStyle == .dark
            ? UIColor(red: 0.64, green: 0.65, blue: 0.67, alpha: 1)
            : UIColor(red: 0.36, green: 0.38, blue: 0.41, alpha: 1)
    })
    static let subtle = muted
    private static func adaptive(_ dark: UIColor, _ light: UIColor) -> Color {
        Color(uiColor: UIColor { $0.userInterfaceStyle == .dark ? dark : light })
    }
    static let healthy = adaptive(UIColor(red: 0.47, green: 0.78, blue: 0.61, alpha: 1), UIColor(red: 0.10, green: 0.42, blue: 0.25, alpha: 1))
    static let warning = adaptive(UIColor(red: 0.89, green: 0.74, blue: 0.50, alpha: 1), UIColor(red: 0.50, green: 0.32, blue: 0.07, alpha: 1))
    static let danger = adaptive(UIColor(red: 0.92, green: 0.38, blue: 0.40, alpha: 1), UIColor(red: 0.72, green: 0.15, blue: 0.19, alpha: 1))
    static let focus = adaptive(UIColor(red: 0.84, green: 0.91, blue: 1, alpha: 1), UIColor(red: 0.13, green: 0.30, blue: 0.61, alpha: 1))
}

@MainActor func dismissZedLinkKeyboard() {
    UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil)
}

struct Hairline: View {
    @Environment(\.displayScale) private var displayScale
    var body: some View { Rectangle().fill(ZLTheme.line).frame(height: 1 / displayScale) }
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
