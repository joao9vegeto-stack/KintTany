import SwiftUI
import Combine
import Foundation

@main
struct SwiftPilotApp: App {
    @StateObject private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(model)
        }
    }
}

struct ChatEntry: Identifiable {
    enum Role { case user, assistant }
    let id = UUID()
    let role: Role
    let text: String
}

struct WorkflowRun: Identifiable {
    let id: Int64
    let name: String
    let status: String
    let conclusion: String?
    let branch: String
    let htmlURL: String
}

enum AppError: LocalizedError {
    case message(String)

    var errorDescription: String? {
        switch self {
        case .message(let text): return text
        }
    }
}

@MainActor
final class AppModel: ObservableObject {
    @Published var messages: [ChatEntry] = []
    @Published var prompt = ""
    @Published var isWorking = false
    @Published var status = "Pronto"
    @Published var errorText: String?
    @Published var workflowRuns: [WorkflowRun] = []

    @Published var githubToken = KeychainStore.load(service: "SwiftPilot.github")
    @Published var groqKey = KeychainStore.load(service: "SwiftPilot.groq")
    @Published var repository = UserDefaults.standard.string(forKey: "SwiftPilot.repository") ?? "joao9vegeto-stack/KintTany"
    @Published var baseBranch = UserDefaults.standard.string(forKey: "SwiftPilot.baseBranch") ?? "AItest"
    @Published var modelName = UserDefaults.standard.string(forKey: "SwiftPilot.model") ?? "qwen/qwen3.8-27b"

    private var apiHistory: [[String: Any]] = []

    init() {
        messages.append(ChatEntry(
            role: .assistant,
            text: "Sou o SwiftPilot. Posso analisar código Swift no GitHub, criar uma branch isolada, editar arquivos e acompanhar builds no GitHub Actions. Configure GitHub e Groq em Ajustes antes de começar."
        ))
    }

    func saveSettings() {
        KeychainStore.save(githubToken.trimmingCharacters(in: .whitespacesAndNewlines), service: "SwiftPilot.github")
        KeychainStore.save(groqKey.trimmingCharacters(in: .whitespacesAndNewlines), service: "SwiftPilot.groq")
        UserDefaults.standard.set(repository.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "SwiftPilot.repository")
        UserDefaults.standard.set(baseBranch.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "SwiftPilot.baseBranch")
        UserDefaults.standard.set(modelName.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "SwiftPilot.model")
        status = "Credenciais salvas no Keychain"
    }

    func resetConversation() {
        apiHistory.removeAll()
        messages = [ChatEntry(role: .assistant, text: "Nova conversa iniciada.")]
        errorText = nil
        status = "Pronto"
    }

    func send() {
        let text = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !isWorking else { return }

        prompt = ""
        messages.append(ChatEntry(role: .user, text: text))
        isWorking = true
        errorText = nil
        status = "Analisando…"

        Task {
            do {
                try validateConfiguration()
                let answer = try await runAgent(userText: text)
                messages.append(ChatEntry(role: .assistant, text: answer))
                status = "Concluído"
                await refreshRuns()
            } catch {
                errorText = error.localizedDescription
                status = "Erro"
            }
            isWorking = false
        }
    }

    private func validateConfiguration() throws {
        guard !githubToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw AppError.message("Adicione um token do GitHub em Ajustes.")
        }
        guard !groqKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw AppError.message("Adicione sua API key da Groq em Ajustes.")
        }
        guard repository.split(separator: "/").count == 2 else {
            throw AppError.message("Repositório inválido. Use owner/repo.")
        }
    }

    private func systemPrompt() -> String {
        """
        Você é SwiftPilot, um agente de engenharia de software especializado em Swift, SwiftUI, UIKit, Swift Concurrency, XCTest e projetos Xcode.
        Repositório atual: \(repository)
        Branch base protegida: \(baseBranch)

        Regras:
        - Leia o código relevante antes de propor ou escrever alterações.
        - Nunca escreva diretamente em main, master ou na branch base protegida.
        - Antes da primeira escrita, crie uma branch começando com agent/ a partir da branch base.
        - Faça alterações mínimas e preserve comportamento não relacionado.
        - Não aumente timeouts para esconder erros.
        - Prefira APIs atuais de Swift e Apple.
        - Depois das alterações, informe os arquivos modificados e a branch usada.
        - Pushes em agent/** podem disparar o GitHub Actions do projeto.
        - Consulte workflow_runs para verificar builds quando for útil.
        - Se o usuário pedir apenas análise, não modifique nada.
        - Responda em português do Brasil.
        """
    }

    private func runAgent(userText: String) async throws -> String {
        let github = GitHubClient(token: githubToken, repository: repository, protectedBranch: baseBranch)

        if apiHistory.isEmpty {
            apiHistory.append(["role": "system", "content": systemPrompt()])
        }
        apiHistory.append(["role": "user", "content": userText])

        for turn in 1...12 {
            status = "IA trabalhando • etapa \(turn)"
            let response = try await GroqClient(apiKey: groqKey, model: modelName)
                .complete(messages: apiHistory, tools: AgentTools.definitions)

            guard let choices = response["choices"] as? [[String: Any]],
                  let first = choices.first,
                  let message = first["message"] as? [String: Any] else {
                throw AppError.message("Resposta inválida recebida da Groq.")
            }

            apiHistory.append(message)

            if let toolCalls = message["tool_calls"] as? [[String: Any]], !toolCalls.isEmpty {
                for call in toolCalls {
                    guard let callID = call["id"] as? String,
                          let function = call["function"] as? [String: Any],
                          let name = function["name"] as? String,
                          let argumentsString = function["arguments"] as? String else {
                        continue
                    }

                    status = "GitHub • \(name)"
                    let argsData = Data(argumentsString.utf8)
                    let args = (try? JSONSerialization.jsonObject(with: argsData)) as? [String: Any] ?? [:]
                    let result: String

                    do {
                        result = try await github.executeTool(name: name, args: args)
                    } catch {
                        result = "ERRO: \(error.localizedDescription)"
                    }

                    apiHistory.append([
                        "role": "tool",
                        "tool_call_id": callID,
                        "content": result
                    ])
                }
                continue
            }

            if let content = message["content"] as? String, !content.isEmpty {
                return content
            }
        }

        throw AppError.message("O agente atingiu o limite de 12 etapas. Continue a tarefa em uma nova mensagem.")
    }

    func refreshRuns() async {
        guard !githubToken.isEmpty, repository.split(separator: "/").count == 2 else { return }
        do {
            let client = GitHubClient(token: githubToken, repository: repository, protectedBranch: baseBranch)
            workflowRuns = try await client.fetchWorkflowRuns()
        } catch {
            errorText = error.localizedDescription
        }
    }

    func testGitHub() {
        isWorking = true
        errorText = nil
        Task {
            do {
                let client = GitHubClient(token: githubToken, repository: repository, protectedBranch: baseBranch)
                _ = try await client.getRepository()
                status = "GitHub conectado"
            } catch {
                errorText = error.localizedDescription
                status = "Falha no GitHub"
            }
            isWorking = false
        }
    }
}

struct RootView: View {
    var body: some View {
        TabView {
            ChatView()
                .tabItem { Label("Agente", systemImage: "terminal") }
            RunsView()
                .tabItem { Label("Builds", systemImage: "hammer") }
            SettingsView()
                .tabItem { Label("Ajustes", systemImage: "gearshape") }
        }
    }
}

struct ChatView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(model.messages) { entry in
                                HStack(alignment: .bottom) {
                                    if entry.role == .user { Spacer(minLength: 44) }
                                    Text(entry.text)
                                        .textSelection(.enabled)
                                        .padding(12)
                                        .foregroundStyle(entry.role == .user ? Color.white : Color.primary)
                                        .background(entry.role == .user ? Color.accentColor : Color.secondary.opacity(0.14))
                                        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                                    if entry.role == .assistant { Spacer(minLength: 44) }
                                }
                                .id(entry.id)
                            }

                            if model.isWorking {
                                HStack {
                                    ProgressView()
                                    Text(model.status)
                                        .font(.footnote)
                                        .foregroundStyle(.secondary)
                                    Spacer()
                                }
                                .padding(.vertical, 6)
                            }
                        }
                        .padding()
                    }
                    .onChange(of: model.messages.count) { _, _ in
                        if let last = model.messages.last {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }

                if let error = model.errorText {
                    Text(error)
                        .font(.footnote)
                        .foregroundStyle(.red)
                        .lineLimit(4)
                        .padding(.horizontal)
                        .padding(.top, 6)
                }

                HStack(alignment: .bottom, spacing: 10) {
                    TextField("Peça uma alteração no projeto…", text: $model.prompt, axis: .vertical)
                        .lineLimit(1...6)
                        .textFieldStyle(.roundedBorder)

                    Button(action: model.send) {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 32))
                    }
                    .disabled(model.prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.isWorking)
                }
                .padding()
                .background(.bar)
            }
            .navigationTitle("SwiftPilot")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button(action: model.resetConversation) {
                        Image(systemName: "plus.bubble")
                    }
                }
            }
        }
    }
}

struct RunsView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        NavigationStack {
            List {
                if model.workflowRuns.isEmpty {
                    ContentUnavailableView(
                        "Nenhum build carregado",
                        systemImage: "hammer",
                        description: Text("Toque em atualizar para consultar o GitHub Actions.")
                    )
                } else {
                    ForEach(model.workflowRuns) { run in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text(run.name).font(.headline)
                                Spacer()
                                Text(run.conclusion ?? run.status)
                                    .font(.caption.bold())
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(.secondary.opacity(0.15))
                                    .clipShape(Capsule())
                            }
                            Text(run.branch)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)

                            if let url = URL(string: run.htmlURL), !run.htmlURL.isEmpty {
                                Link("Abrir no GitHub", destination: url)
                                    .font(.footnote)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
            .navigationTitle("Builds")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        Task { await model.refreshRuns() }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
            .task { await model.refreshRuns() }
        }
    }
}

struct SettingsView: View {
    @EnvironmentObject private var model: AppModel

    var body: some View {
        NavigationStack {
            Form {
                Section("GitHub") {
                    TextField("owner/repo", text: $model.repository)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    TextField("Branch base", text: $model.baseBranch)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    SecureField("Fine-grained personal access token", text: $model.githubToken)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Text("Permissões recomendadas: Contents Read/Write, Actions Read e Metadata Read.")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Button("Testar GitHub", action: model.testGitHub)
                }

                Section("IA") {
                    SecureField("Groq API key", text: $model.groqKey)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    TextField("Modelo", text: $model.modelName)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Text("Padrão: qwen/qwen3.8-27b. As chaves ficam somente no Keychain.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                Section {
                    Button("Salvar credenciais") {
                        model.saveSettings()
                    }
                    .buttonStyle(.borderedProminent)
                }

                Section("Proteções") {
                    Label("Nunca escreve em main/master", systemImage: "lock.shield")
                    Label("Branch base é somente leitura", systemImage: "lock")
                    Label("Alterações somente em agent/**", systemImage: "arrow.triangle.branch")
                }
            }
            .navigationTitle("Ajustes")
        }
    }
}
