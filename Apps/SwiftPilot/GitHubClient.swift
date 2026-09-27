import Foundation

@MainActor
final class GitHubClient {
    private let token: String
    private let repository: String
    private let protectedBranch: String

    init(token: String, repository: String, protectedBranch: String) {
        self.token = token
        self.repository = repository
        self.protectedBranch = protectedBranch
    }

    func getRepository() async throws -> [String: Any] {
        try await requestJSON("/repos/\(repository)")
    }

    func executeTool(name: String, args: [String: Any]) async throws -> String {
        switch name {
        case "read_file":
            let path = try stringArg("path", args)
            let ref = (args["ref"] as? String) ?? protectedBranch
            return try await readFile(path: path, ref: ref)

        case "list_files":
            let path = (args["path"] as? String) ?? ""
            let ref = (args["ref"] as? String) ?? protectedBranch
            return try await listFiles(path: path, ref: ref)

        case "create_branch":
            let branch = try stringArg("name", args)
            let from = (args["from"] as? String) ?? protectedBranch
            return try await createBranch(name: branch, from: from)

        case "write_file":
            let path = try stringArg("path", args)
            let content = try stringArg("content", args)
            let branch = try stringArg("branch", args)
            let message = (args["message"] as? String) ?? "SwiftPilot update"
            return try await writeFile(path: path, content: content, branch: branch, message: message)

        case "workflow_runs":
            let branch = args["branch"] as? String
            let runs = try await fetchWorkflowRuns(branch: branch)
            return runs.map {
                "#\($0.id) \($0.status)/\($0.conclusion ?? "-") branch=\($0.branch) \($0.htmlURL)"
            }
            .joined(separator: "\n")

        default:
            throw AppError.message("Ferramenta desconhecida: \(name)")
        }
    }

    private func stringArg(_ key: String, _ args: [String: Any]) throws -> String {
        guard let value = args[key] as? String, !value.isEmpty else {
            throw AppError.message("Argumento obrigatório ausente: \(key)")
        }
        return value
    }

    private func encodedPath(_ path: String) -> String {
        path.split(separator: "/").map {
            String($0).addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? String($0)
        }
        .joined(separator: "/")
    }

    private func makeURL(
        _ endpoint: String,
        query: [URLQueryItem] = []
    ) throws -> URL {
        var components = URLComponents(string: "https://api.github.com\(endpoint)")
        components?.queryItems = query.isEmpty ? nil : query

        guard let url = components?.url else {
            throw AppError.message("URL do GitHub inválida.")
        }

        return url
    }

    private func rawRequest(
        _ endpoint: String,
        method: String = "GET",
        query: [URLQueryItem] = [],
        body: [String: Any]? = nil,
        allow404: Bool = false
    ) async throws -> (Data, HTTPURLResponse) {
        let url = try makeURL(endpoint, query: query)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        request.setValue("2022-11-28", forHTTPHeaderField: "X-GitHub-Api-Version")
        request.timeoutInterval = 60

        if let body {
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let http = response as? HTTPURLResponse else {
            throw AppError.message("Resposta HTTP inválida do GitHub.")
        }

        if allow404 && http.statusCode == 404 {
            return (data, http)
        }

        guard (200..<300).contains(http.statusCode) else {
            let detail = String(data: data, encoding: .utf8) ?? "sem detalhes"
            throw AppError.message("GitHub HTTP \(http.statusCode): \(detail)")
        }

        return (data, http)
    }

    private func requestJSON(
        _ endpoint: String,
        method: String = "GET",
        query: [URLQueryItem] = [],
        body: [String: Any]? = nil
    ) async throws -> [String: Any] {
        let (data, _) = try await rawRequest(
            endpoint,
            method: method,
            query: query,
            body: body
        )

        if data.isEmpty {
            return [:]
        }

        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw AppError.message("JSON inesperado do GitHub.")
        }

        return object
    }

    private func readFile(path: String, ref: String) async throws -> String {
        let object = try await requestJSON(
            "/repos/\(repository)/contents/\(encodedPath(path))",
            query: [URLQueryItem(name: "ref", value: ref)]
        )

        guard object["type"] as? String == "file",
              let content = object["content"] as? String,
              let data = Data(
                base64Encoded: content.replacingOccurrences(of: "\n", with: ""),
                options: .ignoreUnknownCharacters
              ),
              let text = String(data: data, encoding: .utf8) else {
            throw AppError.message("Não foi possível ler \(path) como texto UTF-8.")
        }

        return text
    }

    private func listFiles(path: String, ref: String) async throws -> String {
        let suffix = path.isEmpty ? "" : "/\(encodedPath(path))"

        let (data, _) = try await rawRequest(
            "/repos/\(repository)/contents\(suffix)",
            query: [URLQueryItem(name: "ref", value: ref)]
        )

        let object = try JSONSerialization.jsonObject(with: data)

        guard let items = object as? [[String: Any]] else {
            if let item = object as? [String: Any] {
                return "\(item["type"] ?? "?") \(item["path"] ?? path)"
            }
            throw AppError.message("Resposta inesperada ao listar arquivos.")
        }

        return items.prefix(200).map {
            "\($0["type"] as? String ?? "?") \($0["path"] as? String ?? "?")"
        }
        .joined(separator: "\n")
    }

    private func createBranch(name: String, from: String) async throws -> String {
        guard name.hasPrefix("agent/") else {
            throw AppError.message("Por segurança, branches criadas pelo agente devem começar com agent/.")
        }

        let encodedFrom = from.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? from

        let reference = try await requestJSON(
            "/repos/\(repository)/git/ref/heads/\(encodedFrom)"
        )

        guard let object = reference["object"] as? [String: Any],
              let sha = object["sha"] as? String else {
            throw AppError.message("Não encontrei o SHA da branch \(from).")
        }

        _ = try await requestJSON(
            "/repos/\(repository)/git/refs",
            method: "POST",
            body: [
                "ref": "refs/heads/\(name)",
                "sha": sha
            ]
        )

        return "Branch criada: \(name) a partir de \(from)"
    }

    private func writeFile(
        path: String,
        content: String,
        branch: String,
        message: String
    ) async throws -> String {
        let lowered = branch.lowercased()

        guard branch.hasPrefix("agent/"),
              lowered != "main",
              lowered != "master",
              branch != protectedBranch else {
            throw AppError.message("Escrita bloqueada: use uma branch agent/** isolada.")
        }

        let endpoint = "/repos/\(repository)/contents/\(encodedPath(path))"

        let (existingData, existingHTTP) = try await rawRequest(
            endpoint,
            query: [URLQueryItem(name: "ref", value: branch)],
            allow404: true
        )

        var body: [String: Any] = [
            "message": message,
            "content": Data(content.utf8).base64EncodedString(),
            "branch": branch
        ]

        if existingHTTP.statusCode != 404,
           let existing = try? JSONSerialization.jsonObject(with: existingData) as? [String: Any],
           let sha = existing["sha"] as? String {
            body["sha"] = sha
        }

        let result = try await requestJSON(
            endpoint,
            method: "PUT",
            body: body
        )

        let commit = result["commit"] as? [String: Any]
        return "Arquivo salvo: \(path) • commit \(commit?["sha"] as? String ?? "criado")"
    }

    func fetchWorkflowRuns(branch: String? = nil) async throws -> [WorkflowRun] {
        var query = [URLQueryItem(name: "per_page", value: "20")]

        if let branch, !branch.isEmpty {
            query.append(URLQueryItem(name: "branch", value: branch))
        }

        let object = try await requestJSON(
            "/repos/\(repository)/actions/runs",
            query: query
        )

        let runs = object["workflow_runs"] as? [[String: Any]] ?? []

        return runs.compactMap { item in
            guard let id = item["id"] as? NSNumber else {
                return nil
            }

            return WorkflowRun(
                id: id.int64Value,
                name: item["name"] as? String ?? "Workflow",
                status: item["status"] as? String ?? "unknown",
                conclusion: item["conclusion"] as? String,
                branch: item["head_branch"] as? String ?? "-",
                htmlURL: item["html_url"] as? String ?? ""
            )
        }
    }
}
