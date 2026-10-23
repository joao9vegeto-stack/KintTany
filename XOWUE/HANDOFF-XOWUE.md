# Handoff técnico — XOWUE

**Jogo:** X-Men Origins: Wolverine — Xbox 360
**Title ID:** 41560816
**Repositório:** [joao9vegeto-stack/KintTany](https://github.com/joao9vegeto-stack/KintTany)
**Branch autorizada:** XOWUE
**Commit de código do Build 3:** d2cfc714903a1381629c6dce3397f56e63ea8436
**Workflow:** [XOWUE iOS IPA](https://github.com/joao9vegeto-stack/KintTany/actions/workflows/xowue-ios.yml)

## Situação desta entrega

O runner e o app foram atualizados para Build 3. A compilação host completa do engine passou com Clang 18: as 344 unidades PPC, o mapa de funções, os adapters e XOWUEHostSmoke compilaram e ligaram. O ambiente local não tem Xcode nem SDK iOS; a validação de arm64, compilação Metal/Vulkan e IPA é feita pela Action acima.

O número que aparece no app vem de CFBundleVersion. A Action conta somente execuções bem-sucedidas do workflow após Build 1; falhas e tentativas não consomem build. Build 1 foi a execução #8 e Build 2 a #11. A execução #12, no commit acima, deve produzir Build 3 se terminar com sucesso. Atualize esta seção com o resultado final e o hash do IPA depois da Action.

Build 3 é um runner de desenvolvimento. O default.xex e os assets do jogo não estão incluídos no repositório ou IPA. Ainda não há prova de menu, primeiro frame real ou partida jogável.

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

iOS/App/XOWUEVulkanBackend.m cria o ICD KosmicKrisp, uma surface CAMetalLayer, device, swapchain e apresenta clears Vulkan. O backend pausa/recria a swapchain em transições de background/foreground e escreve eventos com o número do build. Esse quadro de clear prova apenas a cadeia Vulkan → Metal; ele não é um frame do jogo.

O runtime tem handlers iniciais Vd*, estado de modo de vídeo, validação limitada de comandos PM4 e um marcador VdSwap que chega ao backend. Ainda falta consumir o ring buffer real do jogo, traduzir registradores/estado de draw, shaders e formatos/tiling de textura Xenos para Vulkan. O painel do app deve continuar descrevendo isso como trabalho incompleto até existir imagem real do XEX.

### Imports e conteúdo do jogo

O gerador cobre as 261 imports do executável. 71 adapters possuem comportamento inicial; os outros 190 falham de forma explícita, com nome da API e LR PPC. Os adapters disponíveis não equivalem à implementação completa do kernel/XAM. Ainda devem ser investigados os imports que aparecerem no próximo diagnóstico.

O AOT existente continua compactado em dist/XOWUE-AOT-source.partNN; a Action valida dist/SHA256SUMS e compila as unidades sem colocar o default.xex no Git. Não regenere ou reenvie os blobs AOT sem necessidade e autorização do projeto. Não adicione o XEX original, pasta WGame, DLC, title update, saves ou assets extraídos ao branch.

## Como executar no iPhone

1. Baixe o artifact XOWUE-Build-3 da execução bem-sucedida da Action. O IPA é arm64 e unsigned.
2. Assine com um certificado e perfil de desenvolvimento Apple compatíveis com com.joaopedro.xowue antes de instalar.
3. Coloque a pasta completa do jogo em Arquivos → No Meu iPhone → XOWUE → Jogos. Estruturas detectadas:

       Jogos/default.xex
       Jogos/Nome do jogo/default.xex

4. Volte ao app, toque em atualizar se necessário e use ABRIR JOGO. Também é possível importar uma pasta ou default.xex pelo seletor.
5. Depois do teste, envie diagnostico-build-3.txt e crash-build-3.txt para identificar a próxima parada. Esses logs ficam na raiz Documentos/XOWUE, acessível pelo app Arquivos.

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

1. Baixar os dois logs da Build 3 e seguir o primeiro import/endereço em que o XEX parar; implementar e testar essa API antes de ampliar os stubs.
2. Fazer o runtime consumir a sequência real PM4 do título e preservar contexto de GPU entre chamadas. Adicionar captura de registradores, draw/event packets, formatos e endereços de textura aos logs.
3. Implementar a tradução de shaders Xenos e formatos/tiling de textura e enviar draws Vulkan para a swapchain. Verificar primeiro um draw de teste derivado do estado observado e depois o frame do jogo.
4. Continuar kernel/XAM, heap, MMIO, XMA/áudio, entrada e acesso aos arquivos WGame a partir dos erros reproduzíveis.
5. Não marcar o projeto como jogável até capturar um frame real do jogo e validá-lo no aparelho.

## Regras para o próximo agente com acesso ao GitHub

- Trabalhar exclusivamente em joao9vegeto-stack/KintTany, branch XOWUE; não alterar main.
- Ler este handoff, README.md, THIRD_PARTY_NOTICES.md e os logs da build instalada antes de alterar o runtime.
- Atualizar a mesma branch por commit fast-forward; não fazer force push.
- Preservar o contador sequencial de IPA e o nome de cada diagnóstico/crash por build.
- Nunca versionar default.xex, WGame, DLC, title updates, saves ou outros assets do usuário.
- Deixar falhas de APIs desconhecidas explícitas nos logs; não informar que houve boot ou frame sem evidência capturada.
