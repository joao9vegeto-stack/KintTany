import SwiftUI
import SwiftAgent
import FoundationModels

@main
struct SwiftAgentDemoApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}

struct ChatMessage: Identifiable, Sendable {
    enum Role { case user, assistant }
    let id = UUID()
    let role: Role
    let content: String
}

@MainActor
@Observable
final class ChatModel {
    var messages: [ChatMessage] = []
    var inputText = ""
    var isResponding = false
    var errorMessage: String?

    private let conversation: Conversation

    init() {
        let session = LanguageModelSession(
            model: SystemLanguageModel.default,
            tools: []
        ) {
            Instructions("You are a helpful assistant. Reply in the same language as the user.")
        }
        self.conversation = Conversation(languageModelSession: session) {
            GenerateText { (input: String) in Prompt(input) }
        }
    }

    func send() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isResponding else { return }
        inputText = ""
        errorMessage = nil
        messages.append(ChatMessage(role: .user, content: text))
        isResponding = true

        Task {
            do {
                let response = try await conversation.send(text)
                messages.append(ChatMessage(role: .assistant, content: response.content))
            } catch {
                errorMessage = error.localizedDescription
            }
            isResponding = false
        }
    }
}

struct ContentView: View {
    @State private var model = ChatModel()

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                if model.messages.isEmpty {
                    ContentUnavailableView(
                        "SwiftAgent",
                        systemImage: "brain.head.profile",
                        description: Text("Converse com o modelo local do Foundation Models.")
                    )
                    .frame(maxHeight: .infinity)
                } else {
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(spacing: 12) {
                                ForEach(model.messages) { message in
                                    HStack {
                                        if message.role == .assistant { Spacer(minLength: 0) }
                                        Text(message.content)
                                            .textSelection(.enabled)
                                            .padding(12)
                                            .background(message.role == .user ? Color.accentColor : Color.secondary.opacity(0.16))
                                            .foregroundStyle(message.role == .user ? Color.white : Color.primary)
                                            .clipShape(RoundedRectangle(cornerRadius: 16))
                                        if message.role == .user { Spacer(minLength: 0) }
                                    }
                                    .id(message.id)
                                }
                                if model.isResponding {
                                    HStack {
                                        ProgressView()
                                        Text("Pensando…").foregroundStyle(.secondary)
                                        Spacer()
                                    }
                                }
                            }
                            .padding()
                        }
                        .onChange(of: model.messages.count) {
                            if let id = model.messages.last?.id {
                                withAnimation { proxy.scrollTo(id, anchor: .bottom) }
                            }
                        }
                    }
                }

                if let error = model.errorMessage {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .padding(.horizontal)
                        .padding(.top, 6)
                }

                HStack(alignment: .bottom, spacing: 10) {
                    TextField("Mensagem", text: $model.inputText, axis: .vertical)
                        .lineLimit(1...5)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { model.send() }

                    Button(action: model.send) {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 30))
                    }
                    .disabled(model.inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.isResponding)
                }
                .padding()
                .background(.bar)
            }
            .navigationTitle("SwiftAgent 2.0.1")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}
