import SwiftUI

struct ContentView: View {
    @EnvironmentObject private var settings: AppSettings
    @StateObject private var viewModel = ChatViewModel()
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                statusHeader
                Divider()

                if viewModel.messages.isEmpty {
                    emptyState
                } else {
                    conversation
                }

                if let error = viewModel.errorMessage {
                    HStack(alignment: .top, spacing: 10) {
                        Image(systemName: "exclamationmark.triangle.fill")
                        Text(error)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        Button {
                            viewModel.clearError()
                        } label: {
                            Image(systemName: "xmark.circle.fill")
                        }
                    }
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .padding(.horizontal)
                    .padding(.top, 8)
                }

                composer
            }
            .navigationTitle("Qwen Coder")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button {
                        viewModel.clear()
                    } label: {
                        Image(systemName: "trash")
                    }
                    .disabled(viewModel.messages.isEmpty)

                    Button {
                        showSettings = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                }
            }
            .sheet(isPresented: $showSettings) {
                SettingsView()
                    .environmentObject(settings)
                    .interactiveDismissDisabled(!settings.isReadyForChat)
            }
            .onAppear {
                if !settings.isReadyForChat {
                    showSettings = true
                }
            }
        }
    }

    private var statusHeader: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(settings.isReadyForChat ? Color.green : Color.orange)
                .frame(width: 8, height: 8)

            VStack(alignment: .leading, spacing: 2) {
                Text(settings.model)
                    .font(.caption.weight(.semibold))
                    .lineLimit(1)

                Text(settings.isReadyForChat
                     ? settings.endpoint
                     : "Configuração necessária antes de conversar")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            Spacer()
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
        .contentShape(Rectangle())
        .onTapGesture { showSettings = true }
    }

    private var emptyState: some View {
        VStack(spacing: 14) {
            Spacer()

            Image(systemName: "chevron.left.forwardslash.chevron.right")
                .font(.system(size: 44, weight: .medium))
                .foregroundStyle(.tint)

            Text("Qwen3-Coder no iPhone")
                .font(.title3.bold())

            Text(settings.isReadyForChat
                 ? "Pergunte sobre Swift, SwiftUI, bugs, arquitetura, scripts ou qualquer outro código."
                 : "Configure a conexão primeiro. O app não enviará mensagens sem uma conexão válida.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 34)

            if !settings.isReadyForChat {
                Button("Configurar conexão") {
                    showSettings = true
                }
                .buttonStyle(.borderedProminent)
            }

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var conversation: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 12) {
                    ForEach(viewModel.messages) { message in
                        MessageBubble(message: message)
                            .id(message.id)
                    }
                }
                .padding()
            }
            .onChange(of: viewModel.messages) { _, newValue in
                guard let id = newValue.last?.id else { return }
                withAnimation {
                    proxy.scrollTo(id, anchor: .bottom)
                }
            }
        }
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("Mensagem para o Qwen3-Coder…", text: $viewModel.input, axis: .vertical)
                .lineLimit(1...6)
                .textFieldStyle(.plain)
                .padding(11)
                .background(Color.secondary.opacity(0.10))
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))

            if viewModel.isGenerating {
                Button {
                    viewModel.stop()
                } label: {
                    Image(systemName: "stop.fill")
                        .frame(width: 42, height: 42)
                }
                .buttonStyle(.borderedProminent)
            } else {
                Button {
                    if settings.isReadyForChat {
                        viewModel.send(using: settings)
                    } else {
                        showSettings = true
                    }
                } label: {
                    Image(systemName: settings.isReadyForChat ? "arrow.up" : "gearshape.fill")
                        .frame(width: 42, height: 42)
                }
                .buttonStyle(.borderedProminent)
                .disabled(viewModel.input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && settings.isReadyForChat)
            }
        }
        .padding()
        .background(.ultraThinMaterial)
    }
}
