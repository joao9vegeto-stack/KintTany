import Foundation

struct PresenceBootstrap {
    var region: String
    var position: Position
    var lifeEpoch: Int = 1
    var action: [String: Any] = [:]
}

struct RealtimeConnection {
    let stream: AsyncStream<Data>
    let shard: String
    let serverName: String
    let queueLength: Int
    let populationLabel: String
}

actor RealtimeSocket {
    private struct ServerCandidate {
        let id: Int
        let name: String
        let full: Bool
        let queueLength: Int
        let populationLabel: String

        var shard: String { "s\(id)" }
    }

    private var task: URLSessionWebSocketTask?
    private var queueTask: URLSessionWebSocketTask?
    private var closed = false
    private var continuation: AsyncStream<Data>.Continuation?
    private var traceBuffer: [String] = []
    private var connectionID = UUID()

    /// v1.1.4 — seleciona automaticamente o melhor servidor NA antes de abrir
    /// queue/presence. A fonte é o mesmo endpoint já usado pelo Kintarabot Node
    /// v5.2: /api/servers, ordenando por `full` e `queueLength`. Antes de entrar,
    /// gate-check confirma se a conta pode acessar o shard. Se o melhor falhar,
    /// tenta automaticamente os demais servidores NA (2...7), sem exigir novo toque.
    func connectBestNA(
        session: SessionManager,
        bootstrap: PresenceBootstrap
    ) async throws -> RealtimeConnection {
        closeCurrentConnection()
        traceBuffer.removeAll(keepingCapacity: true)

        guard let cookie = session.cookie, !cookie.isEmpty else {
            trace("[ERROR] Sessão ausente no Keychain")
            throw SocketError.missingSession
        }

        trace("[SERVER] Consultando servidores NA • candidatos=s2,s3,s4,s5,s6,s7")

        let ranked: [ServerCandidate]
        do {
            ranked = try await rankedNAServers(cookie: cookie)
        } catch {
            trace("[WARN] Não foi possível consultar /api/servers: \(error.localizedDescription)")
            trace("[SERVER] Usando failover seguro entre s4,s7,s6,s5,s3,s2")
            ranked = fallbackServers()
        }

        guard !ranked.isEmpty else {
            throw SocketError.noAvailableServer
        }

        let summary = ranked.map { candidate in
            let availability = candidate.full ? "FULL" : candidate.populationLabel
            return "\(candidate.shard)=q\(candidate.queueLength)/\(availability)"
        }.joined(separator: " • ")
        trace("[SERVER] Ranking NA: \(summary)")

        var lastError: Error?
        var attempted = 0

        // Se existe pelo menos um servidor não cheio, não vale a pena entrar em
        // FULL antes de esgotar os abertos. Caso todos estejam FULL, ainda tentamos
        // em ordem de menor fila em vez de falhar sem tentar.
        let hasOpenServer = ranked.contains { !$0.full }
        let ordered = hasOpenServer ? ranked.filter { !$0.full } + ranked.filter { $0.full } : ranked

        for candidate in ordered {
            try Task.checkCancellation()

            let gate = await gateCheck(cookie: cookie, serverID: candidate.id)
            if gate == false {
                trace("[SERVER] \(candidate.shard) indisponível para esta conta • gate-check recusou")
                continue
            }
            if gate == nil {
                trace("[WARN] gate-check de \(candidate.shard) inconclusivo; conexão será tentada")
            }

            attempted += 1
            trace("[SERVER] Tentando \(candidate.name) (\(candidate.shard)) • carga=\(candidate.populationLabel) • fila=\(candidate.queueLength) • full=\(candidate.full ? "sim" : "não")")

            do {
                let stream = try await connectOnShard(
                    cookie: cookie,
                    shard: candidate.shard,
                    bootstrap: bootstrap
                )
                trace("[SERVER] Selecionado \(candidate.name) (\(candidate.shard)) • fila=\(candidate.queueLength)")
                return RealtimeConnection(
                    stream: stream,
                    shard: candidate.shard,
                    serverName: candidate.name,
                    queueLength: candidate.queueLength,
                    populationLabel: candidate.populationLabel
                )
            } catch is CancellationError {
                throw CancellationError()
            } catch {
                lastError = error
                trace("[WARN] \(candidate.shard) falhou: \(error.localizedDescription) • tentando próximo servidor NA")
                closeCurrentConnection()
            }
        }

        if attempted == 0 {
            trace("[ERROR] Nenhum servidor NA passou pelo gate-check")
            throw SocketError.noAvailableServer
        }

        let detail = lastError?.localizedDescription ?? "nenhum servidor respondeu"
        trace("[ERROR] Todos os servidores NA falharam • último erro: \(detail)")
        throw SocketError.allServersFailed(detail)
    }

    /// Mantido para compatibilidade com chamadas/testes que queiram um shard fixo.
    func connect(
        session: SessionManager,
        shard: String,
        bootstrap: PresenceBootstrap
    ) async throws -> AsyncStream<Data> {
        closeCurrentConnection()
        traceBuffer.removeAll(keepingCapacity: true)

        guard let cookie = session.cookie, !cookie.isEmpty else {
            trace("[ERROR] Sessão ausente no Keychain")
            throw SocketError.missingSession
        }

        return try await connectOnShard(cookie: cookie, shard: shard, bootstrap: bootstrap)
    }

    private func connectOnShard(
        cookie: String,
        shard: String,
        bootstrap: PresenceBootstrap
    ) async throws -> AsyncStream<Data> {
        closeCurrentConnection()
        connectionID = UUID()
        let currentConnectionID = connectionID
        closed = false

        var streamContinuation: AsyncStream<Data>.Continuation?
        let inbound = AsyncStream<Data> { continuation in
            streamContinuation = continuation
        }
        continuation = streamContinuation

        trace("[NET] Iniciando conexão realtime • shard=\(shard) • region=\(bootstrap.region) • cookie=presente (valor ocultado)")

        do {
            let token = try await connectToken(cookie: cookie, shard: shard, purpose: "queue")
            let queue = try await open(path: "/ws/queue/\(shard)?kt=\(token)", label: "queue")
            queueTask = queue

            // O cliente Node v5.2 envia q_ping como frame TEXTO. Além disso,
            // URLSessionWebSocketTask pode receber resume() antes de o upgrade ter
            // terminado. O primeiro q_ping agora tolera essa pequena janela e é
            // reenviado por alguns instantes em vez de abortar a atividade.
            let ping = try RealtimeProtocol.queuePing()
            tracePayload(direction: "OUT queue", data: ping)
            try await sendQueueText(ping, on: queue, retryWhileConnecting: true)

            let queueHeartbeat = Task { [weak self] in
                await self?.keepQueueAlive(queue)
            }
            defer { queueHeartbeat.cancel() }

            trace("[NET] Aguardando queue_ready • keepalive q_ping=5s")
            var ready = false
            var lastQueuePosition: Int?
            while !ready {
                try Task.checkCancellation()
                let message = try await queue.receive()
                guard let data = messageData(message) else {
                    trace("[WARN] Queue recebeu mensagem sem payload utilizável")
                    continue
                }

                tracePayload(direction: "IN queue", data: data)
                continuation?.yield(data)

                switch RealtimeProtocol.decode(data) {
                case .queueReady?:
                    ready = true
                    trace("[NET] queue_ready confirmado")

                case .queuePosition(let position)?:
                    if position != lastQueuePosition {
                        lastQueuePosition = position
                        trace("[QUEUE] posição \(position)")
                    }

                case .queueEvicted(let reason)?:
                    trace("[ERROR] Queue removida pelo servidor • reason=\(reason)")
                    throw SocketError.queueEvicted(reason)

                default:
                    break
                }
            }

            queue.cancel(with: .normalClosure, reason: nil)
            queueTask = nil
            trace("[NET] Queue encerrada após queue_ready")

            let presenceToken = try await connectToken(cookie: cookie, shard: shard, purpose: "presence")
            let presence = try await open(path: "/ws/presence/\(shard)?kt=\(presenceToken)", label: "presence")
            task = presence

            Task { [weak self] in
                await self?.receiveLoop(presence, connectionID: currentConnectionID)
            }

            let initialPosition = try RealtimeProtocol.position(
                region: bootstrap.region,
                position: bootstrap.position,
                lifeEpoch: bootstrap.lifeEpoch,
                moving: false,
                full: true,
                action: bootstrap.action
            )
            try await sendPresenceInitial(initialPosition, on: presence)
            trace("[NET] Presence preparada em \(bootstrap.region); receive loop ativo")
            return inbound
        } catch {
            trace("[ERROR] connect() abortado em \(shard): \(error.localizedDescription)")
            continuation?.finish()
            continuation = nil
            queueTask?.cancel(with: .goingAway, reason: nil)
            queueTask = nil
            task?.cancel(with: .goingAway, reason: nil)
            task = nil
            closed = true
            throw error
        }
    }

    func send(_ data: Data) async throws {
        guard !closed, let task else {
            trace("[ERROR] Tentativa de envio sem WebSocket conectado")
            throw SocketError.notConnected
        }

        tracePayload(direction: "OUT presence", data: data)
        do {
            try await task.send(.data(data))
        } catch {
            trace("[ERROR] Presence send falhou: \(error.localizedDescription)")
            throw error
        }
    }

    func close() {
        trace("[NET] Fechando conexão realtime")
        closeCurrentConnection()
    }

    func drainTrace() -> [String] {
        let copy = traceBuffer
        traceBuffer.removeAll(keepingCapacity: true)
        return copy
    }

    private func closeCurrentConnection() {
        connectionID = UUID()
        closed = true
        queueTask?.cancel(with: .normalClosure, reason: nil)
        queueTask = nil
        task?.cancel(with: .normalClosure, reason: nil)
        task = nil
        continuation?.finish()
        continuation = nil
    }

    // MARK: - Seleção de servidor NA

    private func rankedNAServers(cookie: String) async throws -> [ServerCandidate] {
        guard let url = URL(string: "https://kintara.com/api/servers") else {
            throw SocketError.invalidURL
        }

        trace("[HTTP] GET /api/servers")
        var request = URLRequest(url: url)
        request.setValue(cookie, forHTTPHeaderField: "Cookie")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 10

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw SocketError.serverListFailed
        }
        trace("[HTTP] /api/servers → HTTP \(http.statusCode) • \(data.count) bytes")

        guard (200...299).contains(http.statusCode) else {
            throw SocketError.serverListFailed
        }

        guard
            let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
            let rawServers = root["servers"] as? [[String: Any]]
        else {
            throw SocketError.serverListFailed
        }

        // O usuário trabalha na zona NA. Nesta versão a faixa considerada é
        // explicitamente Server 2...7, conforme a tela atual do lobby.
        let servers = rawServers.compactMap { object -> ServerCandidate? in
            guard let id = integer(object["id"]), (2...7).contains(id) else { return nil }
            let name = (object["name"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines)
            let normalizedName = (name?.isEmpty == false) ? name! : "Server \(id)"
            let full = boolean(object["full"]) ?? false
            let queueLength = max(0, integer(object["queueLength"]) ?? 0)
            let populationLabel = ((object["populationLabel"] as? String) ?? "UNKNOWN")
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .uppercased()
            return ServerCandidate(
                id: id,
                name: normalizedName,
                full: full,
                queueLength: queueLength,
                populationLabel: populationLabel.isEmpty ? "UNKNOWN" : populationLabel
            )
        }

        guard !servers.isEmpty else {
            throw SocketError.noAvailableServer
        }

        return servers.sorted { lhs, rhs in
            if lhs.full != rhs.full { return !lhs.full && rhs.full }
            if lhs.queueLength != rhs.queueLength { return lhs.queueLength < rhs.queueLength }
            let leftPopulation = populationRank(lhs.populationLabel)
            let rightPopulation = populationRank(rhs.populationLabel)
            if leftPopulation != rightPopulation { return leftPopulation < rightPopulation }
            return lhs.id < rhs.id
        }
    }

    private func populationRank(_ label: String) -> Int {
        switch label.uppercased() {
        case "LOW": return 0
        case "MEDIUM": return 1
        case "HIGH": return 2
        case "FULL": return 3
        default: return 4
        }
    }

    private func fallbackServers() -> [ServerCandidate] {
        // s4 era o shard fixo da v1.1.3. Mantemos como primeiro fallback caso
        // /api/servers esteja momentaneamente indisponível e, se falhar, fazemos
        // failover pelos demais servidores NA sem intervenção do usuário.
        [4, 7, 6, 5, 3, 2].map {
            ServerCandidate(id: $0, name: "Server \($0)", full: false, queueLength: 0, populationLabel: "UNKNOWN")
        }
    }

    private func gateCheck(cookie: String, serverID: Int) async -> Bool? {
        var components = URLComponents(string: "https://kintara.com/api/auth/gate-check")!
        components.queryItems = [URLQueryItem(name: "shard", value: String(serverID))]
        guard let url = components.url else { return nil }

        var request = URLRequest(url: url)
        request.setValue(cookie, forHTTPHeaderField: "Cookie")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 7

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else { return nil }
            if http.statusCode == 403 { return false }
            guard (200...299).contains(http.statusCode) else { return nil }
            guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
            if let gate = object["gate"] as? String {
                return gate.lowercased() == "ok"
            }
            return nil
        } catch {
            return nil
        }
    }

    private func integer(_ value: Any?) -> Int? {
        if let int = value as? Int { return int }
        if let number = value as? NSNumber { return number.intValue }
        if let string = value as? String { return Int(string) }
        return nil
    }

    private func boolean(_ value: Any?) -> Bool? {
        if let bool = value as? Bool { return bool }
        if let number = value as? NSNumber { return number.boolValue }
        if let string = value as? String {
            switch string.lowercased() {
            case "true", "1", "yes": return true
            case "false", "0", "no": return false
            default: return nil
            }
        }
        return nil
    }

    // MARK: - Queue / Presence

    private func connectToken(cookie: String, shard: String, purpose: String) async throws -> String {
        var components = URLComponents(string: "https://kintara.com/api/lobby/connect-token")!
        components.queryItems = [
            URLQueryItem(name: "shard", value: shard.replacingOccurrences(of: "s", with: "")),
            URLQueryItem(name: "purpose", value: purpose)
        ]

        guard let url = components.url else {
            trace("[ERROR] Não foi possível montar URL de connect-token")
            throw SocketError.tokenFailed
        }

        trace("[HTTP] GET /api/lobby/connect-token • shard=\(shard) • purpose=\(purpose)")
        var request = URLRequest(url: url)
        request.setValue(cookie, forHTTPHeaderField: "Cookie")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 15

        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                trace("[ERROR] connect-token sem HTTPURLResponse")
                throw SocketError.tokenFailed
            }

            trace("[HTTP] connect-token(\(purpose)) → HTTP \(http.statusCode) • \(data.count) bytes")

            guard
                (200...299).contains(http.statusCode),
                let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                let token = object["token"] as? String,
                !token.isEmpty
            else {
                if let body = String(data: data, encoding: .utf8), !body.isEmpty {
                    trace("[HTTP] connect-token(\(purpose)) body: \(redactSecrets(body))")
                }
                throw SocketError.tokenFailed
            }

            trace("[HTTP] connect-token(\(purpose)) recebido • token=<oculto>")
            return token.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? token
        } catch {
            trace("[ERROR] connect-token(\(purpose)) falhou: \(error.localizedDescription)")
            throw error
        }
    }

    private func open(path: String, label: String) async throws -> URLSessionWebSocketTask {
        guard let url = URL(string: "wss://us.kintara.com\(path)") else {
            trace("[ERROR] URL WebSocket inválida para \(label)")
            throw SocketError.invalidURL
        }

        let safePath = path.replacingOccurrences(
            of: #"kt=[^&]+"#,
            with: "kt=<oculto>",
            options: .regularExpression
        )
        trace("[WS] Abrindo \(label): wss://us.kintara.com\(safePath)")

        var request = URLRequest(url: url)
        request.setValue("https://kintara.com", forHTTPHeaderField: "Origin")
        request.timeoutInterval = 15

        let socket = URLSession.shared.webSocketTask(with: request)
        socket.resume()
        trace("[WS] \(label) resume() solicitado")
        return socket
    }

    private func keepQueueAlive(_ queue: URLSessionWebSocketTask) async {
        while !Task.isCancelled {
            do {
                try await Task.sleep(nanoseconds: 5_000_000_000)
                try Task.checkCancellation()
                let ping = try RealtimeProtocol.queuePing()
                tracePayload(direction: "OUT queue", data: ping)
                try await sendQueueText(ping, on: queue, retryWhileConnecting: false)
            } catch is CancellationError {
                return
            } catch {
                if !Task.isCancelled {
                    trace("[WARN] q_ping periódico falhou: \(error.localizedDescription)")
                }
                return
            }
        }
    }

    private func sendQueueText(
        _ data: Data,
        on queue: URLSessionWebSocketTask,
        retryWhileConnecting: Bool
    ) async throws {
        guard let text = String(data: data, encoding: .utf8) else {
            throw SocketError.invalidQueuePayload
        }

        let maxAttempts = retryWhileConnecting ? 10 : 1
        var lastError: Error?

        for attempt in 1...maxAttempts {
            try Task.checkCancellation()
            do {
                try await queue.send(.string(text))
                if attempt > 1 {
                    trace("[WS] q_ping enviado após WebSocket ficar pronto • tentativa \(attempt)")
                }
                return
            } catch {
                lastError = error
                guard attempt < maxAttempts else { break }
                if attempt == 1 {
                    trace("[WS] Queue ainda conectando; aguardando upgrade antes do q_ping")
                }
                try await Task.sleep(nanoseconds: 180_000_000)
            }
        }

        throw lastError ?? SocketError.notConnected
    }

    private func sendPresenceInitial(_ data: Data, on presence: URLSessionWebSocketTask) async throws {
        var lastError: Error?
        for attempt in 1...10 {
            try Task.checkCancellation()
            do {
                tracePayload(direction: "OUT presence", data: data)
                try await presence.send(.data(data))
                if attempt > 1 {
                    trace("[WS] Presence inicial enviada após upgrade • tentativa \(attempt)")
                }
                return
            } catch {
                lastError = error
                guard attempt < 10 else { break }
                if attempt == 1 {
                    trace("[WS] Presence ainda conectando; aguardando upgrade antes da posição inicial")
                }
                try await Task.sleep(nanoseconds: 180_000_000)
            }
        }
        throw lastError ?? SocketError.notConnected
    }

    private func receiveLoop(_ socket: URLSessionWebSocketTask, connectionID loopConnectionID: UUID) async {
        trace("[NET] Presence receive loop iniciado")
        while !closed {
            do {
                let message = try await socket.receive()
                guard let data = messageData(message) else {
                    trace("[WARN] Presence recebeu mensagem sem payload utilizável")
                    continue
                }
                tracePayload(direction: "IN presence", data: data)
                continuation?.yield(data)
            } catch {
                if !closed {
                    trace("[ERROR] Presence receive loop encerrou: \(error.localizedDescription)")
                }
                break
            }
        }

        guard loopConnectionID == connectionID else {
            trace("[NET] Receive loop antigo finalizado; conexão atual preservada")
            return
        }

        continuation?.finish()
        continuation = nil
        task = nil
        closed = true
        trace("[NET] Presence receive loop finalizado")
    }

    private func messageData(_ message: URLSessionWebSocketTask.Message) -> Data? {
        switch message {
        case .data(let data):
            return data
        case .string(let string):
            return Data(string.utf8)
        @unknown default:
            return nil
        }
    }

    private func tracePayload(direction: String, data: Data) {
        if let text = String(data: data, encoding: .utf8) {
            let safe = redactSecrets(text)
            let clipped = safe.count > 6_000 ? String(safe.prefix(6_000)) + "… <truncado>" : safe
            trace("[\(direction)] \(clipped)")
        } else {
            trace("[\(direction)] <binário \(data.count) bytes>")
        }
    }

    private func trace(_ line: String) {
        traceBuffer.append(line)
        if traceBuffer.count > 1_000 {
            traceBuffer.removeFirst(traceBuffer.count - 1_000)
        }
    }

    private func redactSecrets(_ text: String) -> String {
        var result = text
        let patterns = [
            (#"(?i)(\"?(?:token|cookie|session|private[_-]?key)\"?\s*[:=]\s*\")[^\"]*(\")"#, "$1<oculto>$2"),
            (#"(?i)(kintara_session=)[^;\s\"]+"#, "$1<oculto>"),
            (#"(?i)(kt=)[^&\s\"]+"#, "$1<oculto>")
        ]
        for (pattern, replacement) in patterns {
            result = result.replacingOccurrences(of: pattern, with: replacement, options: .regularExpression)
        }
        return result
    }
}

enum SocketError: LocalizedError {
    case missingSession
    case tokenFailed
    case notConnected
    case invalidURL
    case invalidQueuePayload
    case queueEvicted(String)
    case serverListFailed
    case noAvailableServer
    case allServersFailed(String)

    var errorDescription: String? {
        switch self {
        case .missingSession:
            return "Sessão não encontrada no Keychain"
        case .tokenFailed:
            return "Não foi possível obter o connect-token da sessão"
        case .notConnected:
            return "O WebSocket ainda não está conectado"
        case .invalidURL:
            return "URL WebSocket inválida"
        case .invalidQueuePayload:
            return "Não foi possível montar o q_ping da fila"
        case .queueEvicted(let reason):
            if reason == "idle" {
                return "A fila do Kintara encerrou a conexão por inatividade"
            }
            return "A fila do Kintara encerrou a conexão (\(reason))"
        case .serverListFailed:
            return "Não foi possível consultar a lista de servidores do Kintara"
        case .noAvailableServer:
            return "Nenhum servidor NA disponível entre Server 2 e Server 7"
        case .allServersFailed(let detail):
            return "Não foi possível conectar em nenhum servidor NA: \(detail)"
        }
    }
}
