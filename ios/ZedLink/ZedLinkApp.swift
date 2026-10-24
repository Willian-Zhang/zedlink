import SwiftUI

@main @MainActor struct ZedLinkApp: App {
    @UIApplicationDelegateAdaptor(ZedLinkAPNsDelegate.self) private var pushDelegate
    init() { ApprovalNotifications.shared.configure() }
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
            TabView(selection: $selectedTab) {
                SessionsView(navigationPath: $sessionsPath)
                    .tabItem { Label("Sessions", systemImage: "bubble.left.and.bubble.right") }.tag(0)
                ConnectionsView(draft: $connectionDraft)
                    .tabItem { Label("Connections", systemImage: "link") }.tag(1)
                SettingsView()
                    .tabItem { Label("Settings", systemImage: "gearshape") }.tag(2)
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
                await ApprovalNotifications.shared.refreshStatus()
                ApprovalNotifications.shared.onRemoteToken = { _ = Task { await session.syncAPNs() } }
                session.enterForeground()
                if session.profile == nil, let profile = profiles.preferredProfile {
                    await session.connect(profile)
                    if session.state == .live { profiles.markUsed(profile) }
                }
                // Install only after initial profile restoration; earlier responses are queued.
                ApprovalNotifications.shared.handler = { data, action in
                    selectedTab = 0
                    await session.handleApprovalNotification(data, action: action)
                }
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active, session.profile != nil, !session.demoPreview {
                    session.enterForeground()
                    Task {
                        await ApprovalNotifications.shared.refreshStatus()
                        await session.refresh()
                    }
                } else if phase != .active {
                    Task { await session.persistConversation() }
                    if phase == .background { session.enterBackground() }
                }
            }
        }
    }

}
