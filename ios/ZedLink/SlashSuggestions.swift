import SwiftUI

struct NativeSlashSuggestions: View {
    let commands: [NativeCommand]
    let query: String
    let choose: (NativeCommand) -> Void
    private var matches: [NativeCommand] {
        commands.filter { query.isEmpty || $0.name.localizedCaseInsensitiveContains(query) || $0.description.localizedCaseInsensitiveContains(query) }
    }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if matches.isEmpty { Text("No matching advertised commands. Open Agent commands to refresh.").font(.caption).foregroundStyle(ZLTheme.muted).padding(10) }
                ForEach(matches.prefix(12)) { command in
                    Button { choose(command) } label: {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("/\(command.name) · \(command.category)").font(.caption.monospaced()).foregroundStyle(ZLTheme.ink)
                            Text(command.inputHint ?? command.description).font(.caption).foregroundStyle(ZLTheme.muted)
                        }.frame(maxWidth: .infinity, alignment: .leading).padding(10)
                    }.buttonStyle(.plain)
                    Hairline()
                }
            }
        }.frame(maxHeight: 170).background(ZLTheme.surface).accessibilityIdentifier("slash-suggestions")
    }
}
