import SwiftUI

@main struct ZedLinkApp: App {
    @StateObject private var profiles = ProfileStore()
    @StateObject private var session = SessionManager()
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage("zedlink.appearance") private var appearance = "dark"

    private var preferredColorScheme: ColorScheme? {
        switch appearance {
        case "light": .light
        case "system": nil
        default: .dark
        }
    }

    var body: some Scene {
        WindowGroup {
            TabView {
                SessionsView()
                    .tabItem { Label("Sessions", systemImage: "bolt.horizontal.circle") }
                ConnectionsView()
                    .tabItem { Label("Connections", systemImage: "network") }
                SettingsView()
                    .tabItem { Label("Settings", systemImage: "gearshape") }
            }
            .environmentObject(profiles)
            .environmentObject(session)
            .preferredColorScheme(preferredColorScheme)
            .tint(ZLTheme.focus)
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
