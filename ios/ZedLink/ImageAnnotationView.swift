import SwiftUI
import UIKit

struct ImageAnnotationView: View {
    let image: UIImage
    let cancel: () -> Void
    let attach: (Data) -> Void
    @State private var strokes: [[CGPoint]] = []
    @State private var active: [CGPoint] = []

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                Text("Draw to mark an area, or attach the image as it is.")
                    .font(.caption).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
                GeometryReader { geometry in
                    ZStack {
                        Image(uiImage: image).resizable().aspectRatio(contentMode: .fill)
                        Canvas { context, size in
                            for points in strokes + [active] where points.count > 1 {
                                var path = Path()
                                path.move(to: CGPoint(x: points[0].x * size.width, y: points[0].y * size.height))
                                for point in points.dropFirst() {
                                    path.addLine(to: CGPoint(x: point.x * size.width, y: point.y * size.height))
                                }
                                context.stroke(path, with: .color(ZLTheme.danger), style: StrokeStyle(lineWidth: 4, lineCap: .round, lineJoin: .round))
                            }
                        }
                        .contentShape(Rectangle())
                        .gesture(DragGesture(minimumDistance: 0)
                            .onChanged { value in
                                let point = CGPoint(x: min(max(value.location.x / max(geometry.size.width, 1), 0), 1),
                                                    y: min(max(value.location.y / max(geometry.size.height, 1), 0), 1))
                                active.append(point)
                            }
                            .onEnded { _ in if active.count > 1 { strokes.append(active) }; active = [] })
                    }
                    .clipped()
                }
                .aspectRatio(image.size.width / max(image.size.height, 1), contentMode: .fit)
                HStack {
                    Button("Undo") { if !strokes.isEmpty { strokes.removeLast() } }.disabled(strokes.isEmpty)
                    Button("Clear") { strokes = []; active = [] }.disabled(strokes.isEmpty && active.isEmpty)
                    Spacer()
                    Button("Attach") {
                        guard let data = annotatedJPEG() else { return }
                        attach(data)
                    }.buttonStyle(ZLPrimaryButtonStyle())
                }
            }
            .padding()
            .navigationTitle("Review image")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel", action: cancel) } }
        }
    }

    private func annotatedJPEG() -> Data? {
        let size = image.size
        guard size.width > 0, size.height > 0 else { return nil }
        let scale = min(1, 1600 / max(size.width, size.height))
        let outputSize = CGSize(width: size.width * scale, height: size.height * scale)
        let format = UIGraphicsImageRendererFormat(); format.scale = 1
        let renderer = UIGraphicsImageRenderer(size: outputSize, format: format)
        let annotated = renderer.image { context in
            image.draw(in: CGRect(origin: .zero, size: outputSize))
            let path = UIBezierPath(); path.lineWidth = max(4, outputSize.width / 120)
            path.lineCapStyle = .round; path.lineJoinStyle = .round
            UIColor(ZLTheme.danger).setStroke()
            for points in strokes where points.count > 1 {
                path.move(to: CGPoint(x: points[0].x * outputSize.width, y: points[0].y * outputSize.height))
                for point in points.dropFirst() { path.addLine(to: CGPoint(x: point.x * outputSize.width, y: point.y * outputSize.height)) }
            }
            path.stroke()
            context.cgContext.flush()
        }
        return promptJPEG(annotated)
    }
}
