import SwiftUI

struct MessageBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack(alignment: .top) {
            if message.role == "user" {
                Spacer(minLength: 44)
            }

            VStack(alignment: .leading, spacing: 7) {
                Text(message.role == "user" ? "Você" : "Qwen3-Coder")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)

                Text(message.content.isEmpty ? "…" : message.content)
                    .font(message.role == "assistant"
                          ? .system(.body, design: .monospaced)
                          : .body)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(12)
            .background(message.role == "user"
                        ? Color.accentColor.opacity(0.16)
                        : Color.secondary.opacity(0.10))
            .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))

            if message.role != "user" {
                Spacer(minLength: 28)
            }
        }
    }
}
