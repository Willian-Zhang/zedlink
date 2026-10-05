import SwiftUI

@main struct ZedLinkApp: App {
    @StateObject private var profiles = ProfileStore()
    @StateObject private var session = SessionManager()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            TabView {
                SessionsView()
                    .tabItem { Label("Sessions", systemImage: "bubble.left.and.bubble.right") }
                ConnectionsView()
                    .tabItem { Label("Connections", systemImage: "network") }
                SettingsView()
                    .tabItem { Label("Settings", systemImage: "gearshape") }
            }
            .environmentObject(profiles)
            .environmentObject(session)
            .onChange(of: scenePhase) { _, phase in
                if phase == .active, session.profile != nil {
                    Task { await session.refresh() }
                }
            }
        }
    }
}
