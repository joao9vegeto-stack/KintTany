import SwiftUI

struct DashboardBackground: View {
    var body: some View {
        ZStack {
            LinearGradient(
                colors: [KintTanyTheme.backgroundTop, KintTanyTheme.backgroundBottom],
                startPoint: .top,
                endPoint: .bottom
            )

            Canvas { context, size in
                let spacing: CGFloat = 22
                var path = Path()
                stride(from: CGFloat.zero, through: size.width, by: spacing).forEach { x in
                    path.move(to: CGPoint(x: x, y: 0))
                    path.addLine(to: CGPoint(x: x, y: size.height))
                }
                stride(from: CGFloat.zero, through: size.height, by: spacing).forEach { y in
                    path.move(to: CGPoint(x: 0, y: y))
                    path.addLine(to: CGPoint(x: size.width, y: y))
                }
                context.stroke(path, with: .color(KintTanyTheme.cyan.opacity(0.025)), lineWidth: 0.5)
            }
        }
        .ignoresSafeArea()
    }
}

struct PixelPanel<Content: View>: View {
    let accent: Color
    let inset: CGFloat
    let content: Content

    init(
        accent: Color = KintTanyTheme.border,
        inset: CGFloat = 16,
        @ViewBuilder content: () -> Content
    ) {
        self.accent = accent
        self.inset = inset
        self.content = content()
    }

    var body: some View {
        content
            .padding(inset)
            .background(
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: [KintTanyTheme.panel.opacity(0.98), KintTanyTheme.panelDeep.opacity(0.99)],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .stroke(accent.opacity(0.34), lineWidth: 1)
                    .allowsHitTesting(false)
            )
    }
}

struct DashboardSectionTitle: View {
    let title: String
    let subtitle: String
    var accent: Color = KintTanyTheme.cyan

    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            Rectangle()
                .fill(accent)
                .frame(width: 3, height: 28)
                .shadow(color: accent.opacity(0.7), radius: 4)

            VStack(alignment: .leading, spacing: 2) {
                Text(title.uppercased())
                    .font(.system(size: 13, weight: .black, design: .monospaced))
                    .tracking(1.1)
                Text(subtitle)
                    .font(.caption2)
                    .foregroundStyle(KintTanyTheme.mutedText)
            }
        }
    }
}

struct PixelStatusChip: View {
    let text: String
    let color: Color
    var systemImage: String?

    var body: some View {
        HStack(spacing: 6) {
            if let systemImage {
                Image(systemName: systemImage)
                    .font(.system(size: 9, weight: .black))
            } else {
                Rectangle()
                    .fill(color)
                    .frame(width: 7, height: 7)
                    .shadow(color: color, radius: 3)
            }
            Text(text.uppercased())
                .font(.system(size: 10, weight: .black, design: .monospaced))
                .lineLimit(1)
        }
        .foregroundStyle(color)
        .padding(.horizontal, 9)
        .padding(.vertical, 7)
        .background(color.opacity(0.12), in: RoundedRectangle(cornerRadius: 6))
        .overlay(RoundedRectangle(cornerRadius: 6).stroke(color.opacity(0.48), lineWidth: 1))
    }
}

struct PixelProgressBar: View {
    let progress: Double
    let color: Color

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Rectangle().fill(.black.opacity(0.42))
                Rectangle()
                    .fill(LinearGradient(colors: [color.opacity(0.72), color], startPoint: .leading, endPoint: .trailing))
                    .frame(width: proxy.size.width * min(1, max(0, progress)))
            }
        }
        .frame(height: 10)
        .overlay(Rectangle().stroke(.white.opacity(0.12), lineWidth: 1))
        .clipShape(RoundedRectangle(cornerRadius: 3))
        .accessibilityValue("\(Int(min(1, max(0, progress)) * 100)) por cento")
    }
}

struct PixelStat: View {
    let value: String
    let label: String
    var color: Color = .white

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(value)
                .font(.system(size: 17, weight: .black, design: .monospaced))
                .foregroundStyle(color)
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.72)
            Text(label.uppercased())
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .tracking(0.7)
                .foregroundStyle(KintTanyTheme.mutedText)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct PixelIconButtonStyle: ButtonStyle {
    let color: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .black, design: .monospaced))
            .foregroundStyle(.white)
            .padding(.horizontal, 13)
            .padding(.vertical, 11)
            .background(color.opacity(configuration.isPressed ? 0.55 : 0.82), in: RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(color, lineWidth: 1))
            .shadow(color: .black.opacity(0.35), radius: 0, y: configuration.isPressed ? 1 : 3)
            .offset(y: configuration.isPressed ? 2 : 0)
    }
}
