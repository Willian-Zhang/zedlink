import SwiftUI

@main struct ZedLinkApp: App {
    @StateObject private var profiles = ProfileStore()
    @StateObject private var session = SessionManager()
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("zedlink.appearance") private var appearance = "dark"
    @State private var selectedTab = 0

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
                SessionsView()
                    .tabItem { Label("Sessions", systemImage: "bolt.horizontal.circle") }
                    .tag(0)
                ConnectionsView()
                    .tabItem { Label("Connections", systemImage: "network") }
                    .tag(1)
                SettingsView()
                    .tabItem { Label("Settings", systemImage: "gearshape") }
                    .tag(2)
            }
            .environmentObject(profiles)
            .environmentObject(session)
            .preferredColorScheme(preferredColorScheme)
            .tint(ZLTheme.focus)
            .toolbarBackground(ZLTheme.background, for: .navigationBar, .tabBar)
            .toolbarBackground(.visible, for: .navigationBar, .tabBar)
            .onChange(of: selectedTab) { _, _ in dismissZedLinkKeyboard() }
            .task {
                if session.profile == nil, let profile = profiles.preferredProfile {
                    await session.connect(profile)
                    if session.state == .live { profiles.markUsed(profile) }
                }
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active, session.profile != nil {
                    Task { await session.refresh() }
                }
            }
        }
    }
}
