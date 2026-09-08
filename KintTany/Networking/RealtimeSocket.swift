import Foundation

actor RealtimeSocket {
    private var task: URLSessionWebSocketTask?
    private var closed = false
    private var continuation: AsyncStream<Data>.Continuation?
    private var traceBuffer: [String] = []
    private var connectionID = UUID()

    func connect(session: SessionManager, shard: String) async throws -> AsyncStream<Data> {
        closeCurrentConnection()
        connectionID = UUID()
        let currentConnectionID = connectionID
        closed = false
        traceBuffer.removeAll(keepingCapacity: true)

        var streamContinuation: AsyncStream<Data>.Continuation?
        let inbound = AsyncStream<Data> { continuation in
            streamContinuation = continuation
        }
        continuation = streamContinuation

        guard let cookie = session.cookie, !cookie.isEmpty else {
            trace("[ERROR] Sessão ausente no Keychain")
            throw SocketError.missingSession
        }

        trace("[NET] Iniciando conexão realtime • shard=\(shard) • cookie=presente (valor ocultado)")

        do {
            let token = try await connectToken(cookie: cookie, shard: shard, purpose: "queue")
            let queue = try await open(path: "/ws/queue/\(shard)?kt=\(token)", cookie: cookie, label: "queue")

            let ping = try RealtimeProtocol.queuePing()
            tracePayload(direction: "OUT queue", data: ping)
            do {
                try await queue.send(.data(ping))
            } catch {
                trace("[ERROR] Falha ao enviar q_ping para queue: \(error.localizedDescription)")
                throw error
            }

            trace("[NET] Aguardando queue_ready")
            var ready = false
            while !ready {
                let message: URLSessionWebSocketTask.Message
                do {
                    message = try await queue.receive()
                } catch {
                    trace("[ERROR] Queue receive falhou: \(error.localizedDescription)")
                    throw error
                }

                guard let data = messageData(message) else {
                    trace("[WARN] Queue recebeu mensagem sem payload utilizável")
                    continue
                }

                tracePayload(direction: "IN queue", data: data)
                continuation?.yield(data)
                if case .queueReady? = RealtimeProtocol.decode(data) {
                    ready = true
                    trace("[NET] queue_ready confirmado")
                }
            }

            queue.cancel(with: .normalClosure, reason: nil)
            trace("[NET] Queue encerrada após queue_ready")

            let presenceToken = try await connectToken(cookie: cookie, shard: shard, purpose: "presence")
            let presence = try await open(path: "/ws/presence/\(shard)?kt=\(presenceToken)", cookie: cookie, label: "presence")
            task = presence

            Task { [weak self] in
                await self?.receiveLoop(presence, connectionID: currentConnectionID)
            }

            let initialPosition = try RealtimeProtocol.position(
                region: "world",
                position: Position(x: 22.5, z: -3.5),
                lifeEpoch: 1,
                moving: false
            )
            try await send(initialPosition)
            trace("[NET] Presence preparada; receive loop ativo")
            return inbound
        } catch {
            trace("[ERROR] connect() abortado: \(error.localizedDescription)")
            continuation?.finish()
            continuation = nil
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
        task?.cancel(with: .normalClosure, reason: nil)
        task = nil
        continuation?.finish()
        continuation = nil
    }

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

    private func open(path: String, cookie: String, label: String) async throws -> URLSessionWebSocketTask {
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
        request.setValue(cookie, forHTTPHeaderField: "Cookie")
        request.timeoutInterval = 15

        let socket = URLSession.shared.webSocketTask(with: request)
        socket.resume()
        trace("[WS] \(label) resume() solicitado")
        return socket
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
            trace("[\(direction)] \(redactSecrets(text))")
        } else {
            trace("[\(direction)] <binário \(data.count) bytes> base64=\(data.base64EncodedString())")
        }
    }

    private func trace(_ line: String) {
        traceBuffer.append(line)
        if traceBuffer.count > 500 {
            traceBuffer.removeFirst(traceBuffer.count - 500)
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
        }
    }
}
