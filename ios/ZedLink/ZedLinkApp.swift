import SwiftUI

@main struct ZedLinkApp: App {
    @StateObject private var library = SessionLibrary()
    @StateObject private var profiles = ProfileStore()
    @StateObject private var session = SessionManager()
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("zedlink.appearance") private var appearance = "dark"
    @State private var selectedTab = 0
    @State private var sessionsPath: [String] = []
    @State private var connectionDraft = ConnectionDraft()

    private var preferredColorScheme: ColorScheme? {
        switch appearance {
        case "light": .light
        case "system": nil
        default: .dark
        }
    }

    var body: some Scene {
        WindowGroup {
            Group {
                switch selectedTab {
                case 1: ConnectionsView(draft: $connectionDraft)
                case 2: SettingsView()
                default: SessionsView(navigationPath: $sessionsPath)
                }
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                if selectedTab != 0 || sessionsPath.isEmpty {
                    VStack(spacing: 0) {
                        Hairline()
                        HStack(spacing: 0) {
                            navigationButton("Sessions", symbol: "bolt.horizontal", tab: 0)
                            navigationButton("Connections", symbol: "network", tab: 1)
                            navigationButton("Settings", symbol: "gearshape", tab: 2)
                        }
                    }.background(ZLTheme.background)
                }
            }
            .environmentObject(profiles)
            .environmentObject(session)
            .environmentObject(library)
            .preferredColorScheme(preferredColorScheme)
            .tint(ZLTheme.focus)
            .toolbarBackground(ZLTheme.background, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .onChange(of: selectedTab) { _, _ in dismissZedLinkKeyboard() }
            .onChange(of: session.showConnections) { _, requested in
                if requested { sessionsPath = []; selectedTab = 1; session.showConnections = false }
            }
            .task {
                #if DEBUG
                if ProcessInfo.processInfo.arguments.contains("--zedlink-demo") { session.loadDemoPreview(); return }
                #endif
                ApprovalNotifications.shared.configure()
                ApprovalNotifications.shared.handler = { data, action in
                    selectedTab = 0
                    await session.handleApprovalNotification(data, action: action)
                }
                if session.profile == nil, let profile = profiles.preferredProfile {
                    await session.connect(profile)
                    if session.state == .live { profiles.markUsed(profile) }
                }
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active, session.profile != nil, !session.demoPreview {
                    Task { await session.refresh() }
                }
            }
        }
    }

    private func navigationButton(_ title: String, symbol: String, tab: Int) -> some View {
        Button { selectedTab = tab } label: {
            VStack(spacing: 4) {
                Image(systemName: symbol).font(.body)
                Text(title).font(.caption)
            }.frame(maxWidth: .infinity, minHeight: 52)
                .foregroundStyle(selectedTab == tab ? ZLTheme.ink : ZLTheme.muted)
                .overlay(alignment: .top) {
                    if selectedTab == tab { Rectangle().fill(ZLTheme.ink).frame(height: 2) }
                }
        }.buttonStyle(.plain)
            .accessibilityIdentifier(title.lowercased() + "-tab")
            .accessibilityAddTraits(selectedTab == tab ? .isSelected : [])
    }
}
