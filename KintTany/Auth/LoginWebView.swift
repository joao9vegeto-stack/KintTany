import SwiftUI
import CryptoKit
import Foundation

// Legacy filename kept to avoid changing the Xcode project structure.
// This is now a native private-key login screen; it no longer embeds WKWebView.
struct LoginWebView: View {
    let onCookie: (String) -> Void
    let onDiagnostic: (String) -> Void

    @Environment(\.dismiss) private var dismiss

    @State private var privateKey: String
    @State private var rememberKey: Bool
    @State private var isConnecting = false
    @State private var errorMessage: String?

    private static let privateKeyKeychainKey = "kinttany.wallet.private-key-base58"

    init(
        onCookie: @escaping (String) -> Void,
        onDiagnostic: @escaping (String) -> Void = { _ in }
    ) {
        self.onCookie = onCookie
        self.onDiagnostic = onDiagnostic
        let saved = KeychainStore.get(Self.privateKeyKeychainKey) ?? ""
        _privateKey = State(initialValue: saved)
        _rememberKey = State(initialValue: !saved.isEmpty)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Carteira") {
                    SecureField("Private Key Base58", text: $privateKey)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()

                    Toggle("Salvar neste iPhone", isOn: $rememberKey)
                }

                Section {
                    Button {
                        Task { await connect() }
                    } label: {
                        HStack {
                            Spacer()
                            if isConnecting {
                                ProgressView()
                                    .padding(.trailing, 6)
                            }
                            Text(isConnecting ? "Conectando…" : "Conectar")
                                .fontWeight(.semibold)
                            Spacer()
                        }
                    }
                    .disabled(isConnecting || privateKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }

                Section {
                    Text("A autenticação é feita diretamente com o serviço usando Ed25519. A chave não é enviada ao GitHub, ao Codemagic nem ao GitHub Actions. Se você optar por salvá-la, ela fica no Keychain deste aparelho.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }

                if KeychainStore.get(Self.privateKeyKeychainKey) != nil {
                    Section {
                        Button("Esquecer chave salva", role: .destructive) {
                            KeychainStore.delete(Self.privateKeyKeychainKey)
                            privateKey = ""
                            rememberKey = false
                        }
                    }
                }
            }
            .navigationTitle("Sessão")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Fechar") { dismiss() }
                }
            }
            .alert("Falha ao autenticar", isPresented: Binding(
                get: { errorMessage != nil },
                set: { if !$0 { errorMessage = nil } }
            )) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(errorMessage ?? "Erro desconhecido")
            }
        }
    }

    @MainActor
    private func connect() async {
        guard !isConnecting else { return }
        isConnecting = true
        errorMessage = nil

        let secret = privateKey.trimmingCharacters(in: .whitespacesAndNewlines)

        do {
            onDiagnostic("[AUTH] Iniciando autenticação Ed25519 com Private Key Base58 (valor ocultado)")
            let result = try await WalletAuthService().login(privateKeyBase58: secret)
            onDiagnostic("[AUTH] Login aceito • publicKey=\(Self.maskedPublicKey(result.publicKey)) • kintara_session=<oculto>")

            if rememberKey {
                KeychainStore.set(Self.privateKeyKeychainKey, secret)
            } else {
                KeychainStore.delete(Self.privateKeyKeychainKey)
                privateKey = ""
            }

            // RootView persists the returned kintara_session cookie through AppStore.
            onCookie(result.cookie)
        } catch {
            let message = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            onDiagnostic("[AUTH][ERROR] \(message)")
            errorMessage = message
        }

        isConnecting = false
    }
    private static func maskedPublicKey(_ value: String) -> String {
        guard value.count > 12 else { return value }
        return "\(value.prefix(6))…\(value.suffix(6))"
    }

}

private struct WalletAuthResult {
    let cookie: String
    let publicKey: String
}

private enum WalletAuthError: LocalizedError {
    case emptyKey
    case invalidBase58
    case invalidKeyLength(Int)
    case publicKeyMismatch
    case invalidChallenge
    case challengeRejected(String, Int)
    case verifyRejected(String, Int)
    case missingSessionCookie
    case invalidHTTPResponse

    var errorDescription: String? {
        switch self {
        case .emptyKey:
            return "Informe a Private Key Base58."
        case .invalidBase58:
            return "A Private Key contém caracteres que não pertencem ao Base58."
        case .invalidKeyLength(let length):
            return "A chave decodificada possui \(length) bytes. O formato aceito possui 32 ou 64 bytes."
        case .publicKeyMismatch:
            return "A parte pública da chave de 64 bytes não confere com a seed."
        case .invalidChallenge:
            return "O servidor retornou um challenge de autenticação inválido."
        case .challengeRejected(let message, let status):
            return status > 0 ? "Challenge recusado (HTTP \(status)): \(message)" : message
        case .verifyRejected(let message, let status):
            return status > 0 ? "Verificação recusada (HTTP \(status)): \(message)" : message
        case .missingSessionCookie:
            return "A autenticação foi aceita, mas o servidor não retornou kintara_session."
        case .invalidHTTPResponse:
            return "Resposta HTTP inválida durante a autenticação."
        }
    }
}

private struct AuthResponse: Decodable {
    let ok: Bool?
    let challengeId: String?
    let message: String?
    let error: String?
}

private final class NoRedirectDelegate: NSObject, URLSessionTaskDelegate {
    func urlSession(
        _ session: URLSession,
        task: URLSessionTask,
        willPerformHTTPRedirection newRequest: URLRequest,
        newResponse response: HTTPURLResponse,
        completionHandler: @escaping (URLRequest?) -> Void
    ) {
        completionHandler(nil)
    }
}

private struct WalletAuthService {
    private static let origin = URL(string: "https://kintara.com")!

    func login(privateKeyBase58: String) async throws -> WalletAuthResult {
        let trimmed = privateKeyBase58.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw WalletAuthError.emptyKey }

        let raw = try Base58.decode(trimmed)
        guard raw.count == 32 || raw.count == 64 else {
            throw WalletAuthError.invalidKeyLength(raw.count)
        }

        let seed = Data(raw.prefix(32))
        let privateKey = try Curve25519.Signing.PrivateKey(rawRepresentation: seed)
        let publicKeyBytes = privateKey.publicKey.rawRepresentation

        if raw.count == 64 {
            let suppliedPublicKey = Data(raw.suffix(32))
            guard suppliedPublicKey == publicKeyBytes else {
                throw WalletAuthError.publicKeyMismatch
            }
        }

        let publicKeyBase58 = Base58.encode(publicKeyBytes)

        let configuration = URLSessionConfiguration.ephemeral
        configuration.httpShouldSetCookies = false
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = 15

        let redirectDelegate = NoRedirectDelegate()
        let session = URLSession(configuration: configuration, delegate: redirectDelegate, delegateQueue: nil)
        defer { session.invalidateAndCancel() }

        // 1) GET /api/auth/challenge
        var challengeRequest = URLRequest(url: Self.origin.appendingPathComponent("api/auth/challenge"))
        challengeRequest.httpMethod = "GET"
        challengeRequest.timeoutInterval = 15
        challengeRequest.setValue("application/json", forHTTPHeaderField: "Accept")

        let (challengeData, challengeResponse) = try await session.data(for: challengeRequest)
        guard let challengeHTTP = challengeResponse as? HTTPURLResponse else {
            throw WalletAuthError.invalidHTTPResponse
        }

        let challengePayload = try? JSONDecoder().decode(AuthResponse.self, from: challengeData)
        guard (200...299).contains(challengeHTTP.statusCode), challengePayload?.ok == true else {
            let message = challengePayload?.error ?? "challenge falhou"
            throw WalletAuthError.challengeRejected(message, challengeHTTP.statusCode)
        }

        guard
            let challengeId = challengePayload?.challengeId,
            let message = challengePayload?.message,
            !challengeId.isEmpty,
            !message.isEmpty,
            challengeId.utf8.count <= 512,
            message.utf8.count <= 4096
        else {
            throw WalletAuthError.invalidChallenge
        }

        let challengeCookie = sessionCookie(from: challengeHTTP)
        let signature = try privateKey.signature(for: Data(message.utf8))

        // 2) POST /api/auth/verify
        var verifyRequest = URLRequest(url: Self.origin.appendingPathComponent("api/auth/verify"))
        verifyRequest.httpMethod = "POST"
        verifyRequest.timeoutInterval = 15
        verifyRequest.setValue("application/json", forHTTPHeaderField: "Accept")
        verifyRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let challengeCookie {
            verifyRequest.setValue(challengeCookie, forHTTPHeaderField: "Cookie")
        }

        verifyRequest.httpBody = try JSONSerialization.data(withJSONObject: [
            "publicKey": publicKeyBase58,
            "signature": Array(signature),
            "message": message,
            "challengeId": challengeId
        ])

        let (verifyData, verifyResponse) = try await session.data(for: verifyRequest)
        guard let verifyHTTP = verifyResponse as? HTTPURLResponse else {
            throw WalletAuthError.invalidHTTPResponse
        }

        let verifyPayload = try? JSONDecoder().decode(AuthResponse.self, from: verifyData)
        guard (200...299).contains(verifyHTTP.statusCode), verifyPayload?.ok == true else {
            let message = verifyPayload?.error ?? "verify falhou"
            throw WalletAuthError.verifyRejected(message, verifyHTTP.statusCode)
        }

        guard let cookie = sessionCookie(from: verifyHTTP) ?? challengeCookie else {
            throw WalletAuthError.missingSessionCookie
        }

        return WalletAuthResult(cookie: cookie, publicKey: publicKeyBase58)
    }

    private func sessionCookie(from response: HTTPURLResponse) -> String? {
        guard let setCookie = response.value(forHTTPHeaderField: "Set-Cookie") else { return nil }
        guard let start = setCookie.range(of: "kintara_session=")?.lowerBound else { return nil }

        let tail = setCookie[start...]
        let end = tail.firstIndex(of: ";") ?? tail.endIndex
        let cookie = String(tail[..<end])
        return cookie.isEmpty ? nil : cookie
    }
}

private enum Base58 {
    private static let alphabet = Array("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz".utf8)

    static func decode(_ text: String) throws -> Data {
        let input = Array(text.utf8)
        guard !input.isEmpty else { throw WalletAuthError.emptyKey }

        var bytes: [UInt8] = [0] // little-endian base-256 representation

        for character in input {
            guard let digit = alphabet.firstIndex(of: character) else {
                throw WalletAuthError.invalidBase58
            }

            var carry = digit
            for index in bytes.indices {
                let value = Int(bytes[index]) * 58 + carry
                bytes[index] = UInt8(value & 0xff)
                carry = value >> 8
            }

            while carry > 0 {
                bytes.append(UInt8(carry & 0xff))
                carry >>= 8
            }
        }

        while bytes.count > 1 && bytes.last == 0 {
            bytes.removeLast()
        }

        let leadingZeros = input.prefix { $0 == alphabet[0] }.count
        var result = [UInt8](repeating: 0, count: leadingZeros)

        if !(bytes.count == 1 && bytes[0] == 0) {
            result.append(contentsOf: bytes.reversed())
        }

        return Data(result)
    }

    static func encode(_ data: Data) -> String {
        let input = Array(data)
        guard !input.isEmpty else { return "" }

        var digits: [UInt8] = [0] // little-endian base-58 representation

        for byte in input {
            var carry = Int(byte)
            for index in digits.indices {
                let value = Int(digits[index]) * 256 + carry
                digits[index] = UInt8(value % 58)
                carry = value / 58
            }

            while carry > 0 {
                digits.append(UInt8(carry % 58))
                carry /= 58
            }
        }

        while digits.count > 1 && digits.last == 0 {
            digits.removeLast()
        }

        let leadingZeros = input.prefix { $0 == 0 }.count
        var output = String(repeating: "1", count: leadingZeros)

        if !(digits.count == 1 && digits[0] == 0) {
            for digit in digits.reversed() {
                output.append(Character(UnicodeScalar(alphabet[Int(digit)])))
            }
        }

        return output
    }
}
