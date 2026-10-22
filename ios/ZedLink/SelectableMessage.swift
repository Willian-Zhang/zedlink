import SwiftUI
import UIKit

struct SelectableMessageSheet: View {
    @Environment(\.dismiss) private var dismiss
    let text: String
    @State private var selectionRequest = 0

    var body: some View {
        NavigationStack {
            SelectableTextView(text: text, selectionRequest: selectionRequest)
                .accessibilityIdentifier("selectable-message-text")
                .navigationTitle("Message text")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarLeading) { Button("Done") { dismiss() } }
                    ToolbarItemGroup(placement: .topBarTrailing) {
                        Button("Select All") { selectionRequest += 1 }
                            .accessibilityIdentifier("select-all-message-text")
                        Button("Copy All") { UIPasteboard.general.string = text }
                            .accessibilityIdentifier("copy-all-message-text")
                    }
                }
        }
        .presentationDetents([.medium, .large])
    }
}

private struct SelectableTextView: UIViewRepresentable {
    let text: String
    let selectionRequest: Int

    final class Coordinator {
        var lastSelectionRequest = 0
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> UITextView {
        let view = UITextView()
        view.isEditable = false
        view.isSelectable = true
        view.isScrollEnabled = true
        view.adjustsFontForContentSizeCategory = true
        view.font = .preferredFont(forTextStyle: .body)
        view.backgroundColor = .clear
        view.textContainerInset = UIEdgeInsets(top: 16, left: 12, bottom: 16, right: 12)
        return view
    }

    func updateUIView(_ view: UITextView, context: Context) {
        if view.text != text { view.text = text }
        guard selectionRequest != context.coordinator.lastSelectionRequest else { return }
        context.coordinator.lastSelectionRequest = selectionRequest
        DispatchQueue.main.async {
            view.becomeFirstResponder()
            view.selectAll(nil)
        }
    }
}
