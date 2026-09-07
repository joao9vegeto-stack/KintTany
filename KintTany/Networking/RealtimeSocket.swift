import Foundation

actor RealtimeSocket {
    private var task: URLSessionWebSocketTask?
    private var closed = false
    private var continuation: AsyncStream<Data>.Continuation?
    private let inbound: AsyncStream<Data>
    init() {
        var c: AsyncStream<Data>.Continuation?
        inbound = AsyncStream { c = $0 }
        continuation = c
    }
    func stream() -> AsyncStream<Data> { inbound }
    func connect(session: SessionManager, shard: String) async throws {
        closed = false
        guard let cookie = session.cookie, !cookie.isEmpty else { throw SocketError.missingSession }
        let token = try await connectToken(cookie: cookie, shard: shard, purpose: "queue")
        let queue = try await open(path: "/ws/queue/\(shard)?kt=\(token)", cookie: cookie)
        try await queue.send(.data(RealtimeProtocol.queuePing()))
        var ready = false
        while !ready {
            let message = try await queue.receive()
            if case .data(let data) = message {
                continuation?.yield(data)
                if case .queueReady? = RealtimeProtocol.decode(data) { ready = true }
            }
        }
        queue.cancel(with: .normalClosure, reason: nil)
        let presenceToken = try await connectToken(cookie: cookie, shard: shard, purpose: "presence")
        let presence = try await open(path: "/ws/presence/\(shard)?kt=\(presenceToken)", cookie: cookie)
        task = presence
        Task { [weak self] in await self?.receiveLoop(presence) }
        try await send(RealtimeProtocol.position(region: "world", position: Position(x: 22.5, z: -3.5), lifeEpoch: 1, moving: false))
    }
    func send(_ data: Data) async throws { guard !closed, let task else { return }; try await task.send(.data(data)) }
    func close() { closed = true; task?.cancel(with: .normalClosure, reason: nil); task = nil }

    private func connectToken(cookie: String, shard: String, purpose: String) async throws -> String {
        var components = URLComponents(string: "https://kintara.com/api/lobby/connect-token")!
        components.queryItems = [URLQueryItem(name: "shard", value: shard.replacingOccurrences(of: "s", with: "")), URLQueryItem(name: "purpose", value: purpose)]
        var request = URLRequest(url: components.url!); request.setValue(cookie, forHTTPHeaderField: "Cookie"); request.setValue("application/json", forHTTPHeaderField: "Accept")
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode < 300, let object = try? JSONSerialization.jsonObject(with: data) as? [String:Any], let token = object["token"] as? String else { throw SocketError.tokenFailed }
        return token.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? token
    }
    private func open(path: String, cookie: String) async throws -> URLSessionWebSocketTask {
        var request = URLRequest(url: URL(string: "wss://us.kintara.com\(path)")!); request.setValue("https://kintara.com", forHTTPHeaderField: "Origin"); request.setValue(cookie, forHTTPHeaderField: "Cookie")
        let socket = URLSession.shared.webSocketTask(with: request); socket.resume(); return socket
    }
    private func receiveLoop(_ socket: URLSessionWebSocketTask) async {
        while !closed {
            do { let message = try await socket.receive(); if case .data(let data) = message { continuation?.yield(data) } }
            catch { break }
        }
    }
}

enum SocketError: LocalizedError { case missingSession, tokenFailed; var errorDescription: String? { switch self { case .missingSession: "Sessão não encontrada no Keychain"; case .tokenFailed: "Não foi possível obter o connect-token da sessão" } } }
