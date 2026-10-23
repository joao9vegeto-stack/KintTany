# Handoff técnico — XOWUE

**Jogo:** X-Men Origins: Wolverine — Xbox 360
**Title ID:** 41560816
**Repositório:** [joao9vegeto-stack/KintTany](https://github.com/joao9vegeto-stack/KintTany)
**Branch autorizada:** XOWUE
**Build mais recente auditado:** 4 (Action #14, sucesso)
**Workflow:** [XOWUE iOS IPA](https://github.com/joao9vegeto-stack/KintTany/actions/workflows/xowue-ios.yml)

## Situação desta entrega

A última versão testada no aparelho foi o Build 6 (Action #19, commit `3562073`). O XEX2 foi aberto corretamente e os 261 imports foram localizados. O XOWUE executou `XGetVideoMode`, inicializou os engines e configurou o ring buffer Xenos.

O Build 6 então parou na importação `KiApcNormalRoutineNop` (LR `0x82B3E360`). O relatório confirma que o ring buffer ainda não tinha comandos: `rptr=0`, `packets=0`, `draws=0`, `guest_swaps=0` e `decoded_frames=0`. KosmicKrisp passou no dispositivo Apple A19 Pro: Vulkan, CAMetalLayer, Metal e swapchain ativos; o host apresentou frames, mas não recebeu frames convidados.

A referência de Xenia exporta `KiApcNormalRoutineNop` como rotina stub que retorna zero. O adapter XOWUE agora atende as duas grafias exportadas, retorna zero no PPC e registra o evento, em vez de abortar o boot. O HUD tátil também deixa de cobrir a mensagem quando o boot falha. A validação desta mudança no XEX requer o próximo teste no aparelho.

A tradução Xenos ainda é parcial: o runtime consome ring/indirect buffers, reconhece pacotes de swap e decodifica dois formatos de framebuffer; os opcodes de draw são contabilizados, mas não executados com estado e shaders Xenos. Portanto, o Build 6 não produziu imagem do jogo. A próxima medição deve confirmar se o título ultrapassa a chamada APC e passa a submeter comandos; o trabalho gráfico fica guiado pelos pacotes reais registrados.

O número do app vem de `CFBundleVersion`; somente Actions concluídas com sucesso avançam o build. O `default.xex` e os assets do jogo não estão incluídos no IPA ou na branch.

A Action #20 (commit `98e54e2`) produziu o IPA Build 7, sem assinatura, com 24.529.954 bytes e SHA-256 `8141b57adf3b993c4ef23db9c6d7a3216c020dda3f9f229b23484da499551c61`. A Action validou o AOT, o runtime ARM64, o app e o pacote. O último resultado no aparelho continua sendo o Build 6; o Build 7 aguarda a nova execução do XEX.

## O que entrou no Build 3

### Threads PPC e TLS

Runtime/XOWUEEngine.cpp agora fornece uma base para o ciclo de vida das threads do título:

- ExCreateThread lê o ABI PPC usado pelo startup XAPI, cria contexto e pilha próprios e inicia o trampoline/entry point;
- objetos guest de thread, KPCR, ponteiro r13, estado de saída e handles ficam associados ao contexto da thread;
- os caminhos implementados de espera, NtSuspendThread/NtResumeThread, eventos, prioridade/afinidade e término acordam ou finalizam as threads;
- o header TLS do XEX é lido e validado; dados estáticos são copiados para TLS separado por thread;
- KeTlsAlloc/Free/GetValue/SetValue mantém valores por thread e geração, para não reutilizar valores antigos após liberar um slot;
- a parada do runtime acorda e junta threads guest; se uma thread não encerrar no limite, a memória da sessão é preservada em vez de ser liberada enquanto ela ainda executa.

Esse código compilou no host, mas ainda precisa ser exercitado com o default.xex desta instalação. O log do Build 2 parou na primeira chamada de ExCreateThread, LR 0x82C4C110; portanto não havia resultado anterior que confirmasse o caminho novo.

### App, biblioteca local e relatórios

- Em Arquivos, a pasta local do app é No Meu iPhone/XOWUE/Jogos. O app procura default.xex automaticamente, incluindo uma pasta de jogo dentro de Jogos.
- O seletor do iOS aceita pasta ou default.xex, copia o conteúdo para a biblioteca local do XOWUE e registra a instalação escolhida. Havendo mais de uma instalação, mostra opções.
- Build aparece no cabeçalho. Os relatórios ficam na raiz de Documentos, visível em Arquivos:
  - diagnostico-build-N.txt
  - crash-build-N.txt
- Os relatórios registram versão/dispositivo, varredura, picker, importação, caminho do XEX, início/fim do boot, eventos do runtime e exceções Objective-C. O arquivo de crash também identifica um início anterior que não teve término registrado; um encerramento forçado do iOS pode não permitir gravar detalhes adicionais.
- O ícone foi redesenhado para o XOWUE: escudo escuro azul-marinho, lâminas curvas com acabamento metálico e acentos dourados.

### KosmicKrisp, Vulkan e Xenos

Os patches 0001 e 0002 e o smoke source usados aqui correspondem aos mesmos blobs preservados na branch PsTJohn, commit mais recente consultado db014165eb39429ae37d1946db6fc83c600c63b3. O workflow fixa Mesa em bfe063f723d436e5cdef8a98f058d4e44a64810c, aplica os patches iOS/Metal WSI e compila libkk.a e libvulkan_wsi.a para arm64.

iOS/App/XOWUEVulkanBackend.m cria o ICD KosmicKrisp, a surface CAMetalLayer, device e swapchain. O backend continua sendo KosmicKrisp, conforme as validações no PsTJon/PoPTST. O clear de diagnóstico saiu da tela inicial; a viewport em tela cheia fica preta até o runtime executar um draw real do jogo. O Build 4 confirmou 180 presents do host, mas nenhum swap guest.

O runtime tem handlers iniciais Vd*, estado de modo de vídeo e um parser PM4 que apenas valida/conta pacotes; ele não executa estado ou draws Xenos. O callback guest_swap só recebe endereço/dimensão e atualiza telemetria, sem enviar pixels à swapchain. O tamanho do ring buffer em VdInitializeRingBuffer segue a fórmula do Xenia (1 << (size_log2 + 3)) e VdInitializeEngines retorna 1, então esses dois comportamentos já estão alinhados com os stubs upstream. Ainda falta consumir o ring buffer real, traduzir registradores/estado de draw, shaders e formatos/tiling de textura Xenos para Vulkan. A evidência de progresso visual será draw guest e primeiro flip com imagem do XEX.

### Imports e conteúdo do jogo

O gerador cobre as 261 imports do executável. Com XGetVideoMode, 75 adapters têm comportamento inicial; os outros 186 falham de forma explícita, com nome da API e LR PPC. Os adapters disponíveis não equivalem à implementação completa do kernel/XAM. O próximo diagnóstico do aparelho deve guiar a próxima correção.

O AOT existente continua compactado em dist/XOWUE-AOT-source.partNN; a Action valida dist/SHA256SUMS e compila as unidades sem colocar o default.xex no Git. Não regenere ou reenvie os blobs AOT sem necessidade e autorização do projeto. Não adicione o XEX original, pasta WGame, DLC, title update, saves ou assets extraídos ao branch.

## Como executar no iPhone

1. Baixe o artifact XOWUE-Build-5 da execução bem-sucedida da Action. O IPA é arm64 e unsigned.
2. Assine com um certificado e perfil de desenvolvimento Apple compatíveis com com.joaopedro.xowue antes de instalar.
3. Coloque a pasta completa do jogo em Arquivos → No Meu iPhone → XOWUE → Jogos. Estruturas detectadas:

       Jogos/default.xex
       Jogos/Nome do jogo/default.xex

4. Volte ao app, toque em atualizar se necessário e use ABRIR JOGO. Também é possível importar uma pasta ou default.xex pelo seletor.
5. Depois de testar o Build 5, envie diagnostico-build-5.txt e crash-build-5.txt para identificar a próxima parada e capturar qualquer avanço até VdInitializeEngines/VdSwap. Esses logs ficam na raiz Documentos/XOWUE, acessível pelo app Arquivos.

## Build host

Linux com Clang 18, Python 3, CMake e submódulos XenonRecomp. A branch já contém a análise e o archive AOT:

    git clone https://github.com/joao9vegeto-stack/KintTany.git
    cd KintTany
    git switch --track origin/XOWUE

    git clone --recursive https://github.com/hedge-dev/XenonRecomp.git XOWUE/vendor/XenonRecomp
    git -C XOWUE/vendor/XenonRecomp checkout ddd128bcca99fe8bfbb99bea583c972351fa6ace
    git -C XOWUE/vendor/XenonRecomp submodule update --init --recursive
    git -C XOWUE/vendor/XenonRecomp apply "$PWD/XOWUE/patches/XenonRecomp-XOWUE.patch"

    tar -xzf XOWUE/dist/XOWUE-AOT-source.tar.gz -C XOWUE/generated
    cmake -S XOWUE/Runtime -B build-runtime \
      -DCMAKE_C_COMPILER=clang-18 \
      -DCMAKE_CXX_COMPILER=clang++-18 \
      -DCMAKE_BUILD_TYPE=Release \
      -DXENONRECOMP_ROOT="$PWD/XOWUE/vendor/XenonRecomp" \
      -DXOWUE_BUILD_HOST_SMOKE=ON
    cmake --build build-runtime --target XOWUEHostSmoke --parallel 4
    ./build-runtime/XOWUEHostSmoke /caminho/local/default.xex

O workflow da Action executa a compilação iOS arm64, gera o projeto com XcodeGen, valida Info.plist e arquitetura, empacota o IPA e testa a integridade do ZIP. O IPA não tem assinatura Apple nem inclui o jogo.

## Continuidade do trabalho

1. Validar no iPhone o adapter XGetVideoMode do próximo build e seguir até o primeiro erro reproduzível ou VdInitializeEngines.
2. Quando o título inicializar os engines, capturar ring buffer, read/write pointers, PM4 e registradores; a validação atual do parser não executa os pacotes.
3. Validar no runtime o fetch/frontbuffer do VdSwap (o mapa atual usa identidade) e alimentar a cadeia gráfica com a textura real; conferir formato, dimensões e tiling no aparelho.
4. Traduzir shaders Xenos para SPIR-V/Vulkan e enviar os draws pela swapchain KosmicKrisp/Metal; preservar contexto entre chamadas.
5. Não marcar como renderizado/jogável até capturar e validar um frame real do XEX no iPhone.

## Regras para o próximo agente com acesso ao GitHub

- Trabalhar exclusivamente em joao9vegeto-stack/KintTany, branch XOWUE; não alterar main.
- Ler este handoff, README.md, THIRD_PARTY_NOTICES.md e os logs da build instalada antes de alterar o runtime.
- Atualizar a mesma branch por commit fast-forward; não fazer force push.
- Preservar o contador sequencial de IPA e o nome de cada diagnóstico/crash por build.
- Nunca versionar default.xex, WGame, DLC, title updates, saves ou outros assets do usuário.
- Deixar falhas de APIs desconhecidas explícitas nos logs; não informar que houve boot ou frame sem evidência capturada.
