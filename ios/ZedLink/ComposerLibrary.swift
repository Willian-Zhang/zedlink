import Foundation
import SwiftUI

struct ComposerScope: Codable, Hashable, Identifiable {
    let gatewayID: String
    let targetID: String

    init(gatewayID: String, targetID: String) {
        self.gatewayID = gatewayID.lowercased()
        self.targetID = targetID
    }

    var id: String { gatewayID + ":" + targetID }
}

struct PromptSnippet: Codable, Identifiable, Equatable {
    var id = UUID()
    var title: String
    var body: String
}

@MainActor final class ComposerLibrary: ObservableObject {
    static let shared = ComposerLibrary()

    private struct Record: Codable {
        let scope: ComposerScope
        var pinned: [String] = []
        var recent: [String] = []
        var snippets: [PromptSnippet] = []
    }

    @Published private var records: [Record] = []
    @Published private(set) var saveIssue: String?
    private let fileURL: URL?

    private init() {
        fileURL = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)
            .first?.appendingPathComponent("ComposerLibrary", isDirectory: true)
            .appendingPathComponent("shortcuts.json")
        if let fileURL,
           let data = try? Data(contentsOf: fileURL), data.count <= 1_048_576,
           let saved = try? JSONDecoder().decode([Record].self, from: data) {
            records = saved
        }
    }

    func pinned(in scope: ComposerScope) -> [String] {
        records.first(where: { $0.scope == scope })?.pinned ?? []
    }

    func recent(in scope: ComposerScope) -> [String] {
        records.first(where: { $0.scope == scope })?.recent ?? []
    }

    func snippets(in scope: ComposerScope) -> [PromptSnippet] {
        records.first(where: { $0.scope == scope })?.snippets ?? []
    }

    func clearIssue() { saveIssue = nil }

    func togglePin(_ name: String, in scope: ComposerScope) {
        let previous = records
        let index = recordIndex(for: scope)
        if records[index].pinned.contains(name) {
            records[index].pinned.removeAll { $0 == name }
        } else {
            records[index].pinned.insert(name, at: 0)
            records[index].pinned = Array(records[index].pinned.prefix(24))
        }
        if !save() { records = previous }
    }

    func recordChoice(_ name: String, in scope: ComposerScope) {
        let previous = records
        let index = recordIndex(for: scope)
        records[index].recent.removeAll { $0 == name }
        records[index].recent.insert(name, at: 0)
        records[index].recent = Array(records[index].recent.prefix(12))
        if !save() { records = previous }
    }

    @discardableResult func saveSnippet(_ snippet: PromptSnippet, in scope: ComposerScope) -> Bool {
        let title = snippet.title.trimmingCharacters(in: .whitespacesAndNewlines)
        let body = snippet.body.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty, title.count <= 80, !body.isEmpty, body.count <= 3_000 else {
            saveIssue = "Use a title up to 80 characters and prompt text up to 3,000 characters."
            return false
        }
        let previous = records
        let index = recordIndex(for: scope)
        var updated = snippet
        updated.title = title
        updated.body = body
        if let existing = records[index].snippets.firstIndex(where: { $0.id == snippet.id }) {
            records[index].snippets[existing] = updated
        } else {
            guard records[index].snippets.count < 20 else {
                saveIssue = "This workspace already has 20 saved prompts. Remove one before adding another."
                records = previous
                return false
            }
            records[index].snippets.append(updated)
        }
        if save() { return true }
        records = previous
        return false
    }

    func deleteSnippet(_ id: UUID, in scope: ComposerScope) {
        guard let index = records.firstIndex(where: { $0.scope == scope }) else { return }
        let previous = records
        records[index].snippets.removeAll { $0.id == id }
        if !save() { records = previous }
    }

    func forgetGateway(_ gatewayID: String) {
        let previous = records
        records.removeAll { $0.scope.gatewayID == gatewayID.lowercased() }
        if !save() { records = previous }
    }

    private func recordIndex(for scope: ComposerScope) -> Int {
        if let index = records.firstIndex(where: { $0.scope == scope }) { return index }
        records.append(Record(scope: scope))
        return records.count - 1
    }

    @discardableResult private func save() -> Bool {
        guard let fileURL else { saveIssue = "Local prompt storage is unavailable."; return false }
        do {
            let data = try JSONEncoder().encode(records)
            guard data.count <= 1_048_576 else {
                saveIssue = "Local prompt storage is full. Remove saved prompts and try again."
                return false
            }
            try FileManager.default.createDirectory(at: fileURL.deletingLastPathComponent(),
                                                    withIntermediateDirectories: true)
            try data.write(to: fileURL, options: .atomic)
            try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete],
                                                  ofItemAtPath: fileURL.path)
            var excluded = fileURL
            var values = URLResourceValues()
            values.isExcludedFromBackup = true
            try excluded.setResourceValues(values)
            saveIssue = nil
            return true
        } catch {
            saveIssue = "Could not save prompts on this iPhone. Check available storage and try again."
            return false
        }
    }
}

@MainActor struct PromptSnippetsView: View {
    @Environment(\.dismiss) private var dismiss
    @ObservedObject var library: ComposerLibrary
    let scope: ComposerScope
    let currentDraft: String
    let insert: (String) -> Bool
    @State private var editing: PromptSnippet?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Saved on this iPhone for this Zed workspace. Inserting a prompt edits your draft; it does not send it.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Section("Saved prompts") {
                    if library.snippets(in: scope).isEmpty {
                        Text("No saved prompts yet. Add a reusable instruction or task outline.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(library.snippets(in: scope)) { snippet in
                        HStack(spacing: 12) {
                            Button {
                                if insert(snippet.body) { dismiss() }
                            } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(snippet.title).font(.body.weight(.medium))
                                    Text(snippet.body).font(.footnote).foregroundStyle(.secondary)
                                        .lineLimit(2)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .frame(minHeight: 44)
                            }
                            .buttonStyle(.plain)
                            Button { library.clearIssue(); editing = snippet } label: {
                                Image(systemName: "pencil").frame(width: 44, height: 44)
                            }
                            .accessibilityLabel("Edit \(snippet.title)")
                        }
                    }
                    .onDelete { offsets in
                        let snippets = library.snippets(in: scope)
                        for offset in offsets { library.deleteSnippet(snippets[offset].id, in: scope) }
                    }
                }
                if let issue = library.saveIssue {
                    Section { Text(issue).foregroundStyle(.orange) }
                }
            }
            .navigationTitle("Saved prompts")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Done") { dismiss() } }
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button("New blank prompt") {
                            library.clearIssue(); editing = PromptSnippet(title: "", body: "")
                        }
                        Button("Save current draft") {
                            library.clearIssue()
                            editing = PromptSnippet(title: "", body: currentDraft)
                        }
                        .disabled(currentDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    } label: {
                        Image(systemName: "plus")
                    }
                    .accessibilityLabel("Add saved prompt")
                }
            }
            .sheet(item: $editing) { snippet in
                PromptSnippetEditor(snippet: snippet, error: library.saveIssue) { updated in
                    if library.saveSnippet(updated, in: scope) { editing = nil }
                }
            }
        }
    }
}

private struct PromptSnippetEditor: View {
    @Environment(\.dismiss) private var dismiss
    let snippet: PromptSnippet
    let error: String?
    let save: (PromptSnippet) -> Void
    @State private var title: String
    @State private var bodyText: String

    init(snippet: PromptSnippet, error: String?, save: @escaping (PromptSnippet) -> Void) {
        self.snippet = snippet
        self.error = error
        self.save = save
        _title = State(initialValue: snippet.title)
        _bodyText = State(initialValue: snippet.body)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Name") {
                    TextField("Example: Review this change", text: $title)
                    Text("\(title.count) / 80 characters").font(.caption).foregroundStyle(.secondary)
                }
                Section("Prompt text") {
                    TextEditor(text: $bodyText).frame(minHeight: 180)
                    Text("\(bodyText.count) / 3,000 characters").font(.caption).foregroundStyle(.secondary)
                    Text("Insert this into the chat draft whenever you need it. It will not send automatically.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                if let error { Section { Text(error).foregroundStyle(.orange) } }
            }
            .navigationTitle(snippet.title.isEmpty ? "New prompt" : "Edit prompt")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") {
                        var updated = snippet
                        updated.title = title
                        updated.body = bodyText
                        save(updated)
                    }
                    .disabled(title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                              bodyText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ||
                              title.count > 80 || bodyText.count > 3_000)
                }
            }
        }
    }
}
