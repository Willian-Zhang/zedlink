import SwiftUI
import Speech
import AVFoundation
import UIKit

@MainActor
private final class DraftDictation: ObservableObject {
    @Published var listening = false
    @Published var starting = false
    @Published var finishing = false
    @Published var transcript = ""
    @Published var issue = ""
    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var tapped = false
    private var generation = UUID()
    private var finishTimeout: Task<Void, Never>?
    private var audioActive = false

    func start() async {
        guard !starting, !finishing else { return }
        guard !listening else { finish(); return }
        stop()
        let current = generation
        starting = true
        defer { if current == generation { starting = false } }
        let authorization = await withCheckedContinuation { continuation in
            SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0) }
        }
        let microphone = await withCheckedContinuation { continuation in
            AVAudioSession.sharedInstance().requestRecordPermission { continuation.resume(returning: $0) }
        }
        guard current == generation else { return }
        guard authorization == .authorized, microphone else { issue = "Allow microphone and speech access in Settings, or use keyboard dictation."; return }
        guard let recognizer = SFSpeechRecognizer(), recognizer.isAvailable, recognizer.supportsOnDeviceRecognition else {
            issue = "On-device dictation is unavailable for this language. Use your keyboard microphone."; return
        }
        transcript = ""; issue = ""
        do {
            let audio = AVAudioSession.sharedInstance()
            try audio.setCategory(.record, mode: .measurement)
            try audio.setActive(true)
            audioActive = true
            let request = SFSpeechAudioBufferRecognitionRequest()
            request.requiresOnDeviceRecognition = true
            request.shouldReportPartialResults = true
            self.request = request
            let node = engine.inputNode
            let format = node.outputFormat(forBus: 0)
            guard format.sampleRate > 0 else { throw NSError(domain: "Dictation", code: 1, userInfo: [NSLocalizedDescriptionKey: "Microphone is unavailable."]) }
            node.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in request.append(buffer) }
            tapped = true
            engine.prepare(); try engine.start(); listening = true
            task = recognizer.recognitionTask(with: request) { [weak self] result, error in
                Task { @MainActor in
                    guard let self, self.generation == current else { return }
                    if let result { self.transcript = result.bestTranscription.formattedString }
                    if let error { self.issue = error.localizedDescription }
                    if result?.isFinal == true || error != nil { self.stop() }
                }
            }
        } catch { issue = error.localizedDescription; stop() }
    }
    func finish() {
        guard listening, !finishing else { return }
        stopAudioCapture()
        listening = false; finishing = true
        request?.endAudio()
        let current = generation
        finishTimeout = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(3)) } catch { return }
            guard let self, self.generation == current else { return }
            self.stop()
        }
    }
    private func stopAudioCapture() {
        if engine.isRunning { engine.stop() }
        if tapped { engine.inputNode.removeTap(onBus: 0); tapped = false }
    }
    func stop() {
        generation = UUID()
        finishTimeout?.cancel(); finishTimeout = nil
        stopAudioCapture()
        request?.endAudio(); task?.cancel(); task = nil; request = nil
        listening = false; starting = false; finishing = false
        if audioActive {
            audioActive = false
            do { try AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation) }
            catch { if issue.isEmpty { issue = error.localizedDescription } }
        }
    }
}

struct VoiceDraftButton: View {
    @Binding var text: String
    let scope: String
    @StateObject private var dictation = DraftDictation()
    @State private var original = ""
    @State private var lastApplied = ""
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        Button {
            if dictation.listening { dictation.finish() }
            else { original = text; lastApplied = text; Task { await dictation.start() } }
        } label: {
            Group {
                if dictation.starting || dictation.finishing { ProgressView().controlSize(.small) }
                else { Image(systemName: dictation.listening ? "waveform" : "mic").symbolEffect(.variableColor, isActive: dictation.listening && !reduceMotion) }
            }.frame(width: 44, height: 44)
        }.disabled(dictation.starting || dictation.finishing)
        .accessibilityLabel(dictation.starting ? "Preparing dictation" : dictation.finishing ? "Finishing dictation" : dictation.listening ? "Stop dictation" : "Dictate draft text")
        .onChange(of: dictation.transcript) { _, value in
            guard text == lastApplied else { dictation.stop(); return }
            lastApplied = String((original + (original.isEmpty || value.isEmpty ? "" : " ") + value).prefix(3000))
            text = lastApplied
        }
        .onChange(of: scope) { _, _ in dictation.stop() }
        .onChange(of: scenePhase) { _, phase in if phase != .active { dictation.stop() } }
        .onDisappear { dictation.stop() }
        .alert("Dictation", isPresented: Binding(get: { !dictation.issue.isEmpty }, set: { if !$0 { dictation.issue = "" } })) {
            Button("OK") { dictation.issue = "" }
        } message: { Text(dictation.issue) }
    }
}

struct RemoteClipboardView: View {
    @EnvironmentObject private var session: SessionManager
    @Environment(\.dismiss) private var dismiss
    var destination = "terminal"
    let insert: (String) -> Void
    @State private var text = ""
    @State private var busy = false
    @State private var status = ""
    private var scope: String { "\(session.profile?.id.uuidString ?? "").\(session.targetID ?? "").\(session.instanceID ?? "").\(session.epoch ?? "").\(session.selectedThreadID ?? "")" }
    var body: some View {
        NavigationStack {
            Form {
                Section("Preview") { TextEditor(text: $text).frame(minHeight: 160).onChange(of: text) { old, value in if value.utf8.count > 65536 { text = old; status = "Clipboard exceeds 64 KiB." } }
                    Text(destination == "terminal"
                         ? "Explicit text transfers only. Terminal paste fills a draft; it does not execute."
                         : "Explicit text transfers only. Inserting text fills the message draft; it does not send.")
                        .font(.caption)
                }
                Section {
                    Button("Read desktop clipboard") { transfer(nil) }.disabled(!session.capabilities.contains("clipboard.read"))
                    Button("Paste from phone") { let value = UIPasteboard.general.string ?? ""; if value.utf8.count <= 65536 { text = value } else { status = "Clipboard exceeds 64 KiB." } }
                    Button("Copy to phone") { UIPasteboard.general.string = text }
                    Button("Send to desktop clipboard") { transfer(text) }.disabled(!session.capabilities.contains("clipboard.write"))
                    Button("Insert in \(destination) draft") {
                        guard text.utf8.count <= 16384, !text.unicodeScalars.contains(where: { $0.value < 32 && $0.value != 9 && $0.value != 10 && $0.value != 13 || $0.value == 127 }) else { status = "Use plain text up to 16 KiB without terminal controls."; return }
                        guard destination != "prompt" || text.count <= 3000 else { status = "Use up to 3000 characters for the prompt."; return }
                        insert(text); dismiss()
                    }.disabled(destination == "terminal" ? !session.capabilities.contains("terminal.input") : session.selectedThreadID == nil)
                }.disabled(busy)
                if !session.capabilities.contains("clipboard.read") { Text("Enable Remote Clipboard in desktop ZedLink settings for desktop transfers.") }
                if !status.isEmpty { Text(status) }
            }
            .task { await session.loadProjectContext() }
            .onChange(of: scope) { _, _ in text = ""; dismiss() }
            .onDisappear { text = "" }
            .navigationTitle("Remote clipboard").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
        }
    }
    private func transfer(_ value: String?) {
        busy = true
        Task { defer { busy = false }; if let result = await session.transferClipboard(value) { text = result; status = value == nil ? "Ready to review." : "Desktop clipboard updated." } else { status = session.issue } }
    }
}
