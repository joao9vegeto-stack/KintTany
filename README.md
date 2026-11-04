# God of War III Remastered — iOS

<p align="center">
  <strong>Uma adaptação comunitária de God of War III Remastered para iPhone e iPadOS.</strong><br>
  <em>Fork independente da linhagem SpartanPort / gow3_android, com uma camada nativa específica para iOS.</em>
</p>

> [!IMPORTANT]
> **Este repositório é um fork comunitário e experimental.** Ele não é o projeto original SpartanPort, não é uma versão oficial da Sony e não é afiliado, patrocinado ou endossado pela Sony Interactive Entertainment ou pela Santa Monica Studio.
>
> Nenhum jogo, firmware, BIOS, dump, arquivo de sistema PS4 ou conteúdo protegido de God of War é distribuído aqui. É necessário possuir e preparar legalmente sua própria cópia do jogo.

## Índice

- [Sobre este fork](#sobre-este-fork)
- [Objetivo e estado atual](#objetivo-e-estado-atual)
- [Origem e linhagem do código](#origem-e-linhagem-do-código)
- [Como funciona](#como-funciona)
- [Histórico do desenvolvimento para iOS 26](#histórico-do-desenvolvimento-para-ios-26)
- [Compatibilidade e requisitos](#compatibilidade-e-requisitos)
- [Preparação do jogo](#preparação-do-jogo)
- [Instalação e JIT](#instalação-e-jit)
- [Compilação a partir do código-fonte](#compilação-a-partir-do-código-fonte)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Diagnóstico e desempenho](#diagnóstico-e-desempenho)
- [Créditos e agradecimentos](#créditos-e-agradecimentos)
- [Licença e avisos legais](#licença-e-avisos-legais)

## Sobre este fork

Este projeto adapta para iOS a versão comunitária de **God of War III Remastered (PlayStation 4)** cuja linhagem de código passa pelo projeto Android e pelo port de PC.

O motivo do fork é técnico: levar o runtime e o caminho gráfico do projeto original a um ambiente Apple Silicon móvel, sem depender de uma camada Android, de Turnip ou de um processo Linux separado. Isso exige substituir partes específicas de Linux/Android por implementações compatíveis com Darwin e iOS, integrar a execução JIT permitida pelo sistema, criar uma janela nativa baseada em `CAMetalLayer`, adaptar entrada e áudio e compilar o conjunto como um aplicativo iOS instalável.

O trabalho não consiste em converter previamente todo o executável do jogo para ARM64. O executável x86-64 do PS4 continua sendo executado por tradução dinâmica do FEXCore para ARM64; as bibliotecas e serviços do sistema PS4 são atendidos pelo runtime/HLE do port.

**Relação com o projeto original:** a base de runtime e GPU vem da linhagem [gow3_android](https://github.com/wyatt-poole/gow3_android), que por sua vez é um fork de [SpartanPort](https://github.com/FelipePrado0/SpartanPort). Este repositório mantém o reconhecimento dessa origem e dos autores anteriores. A página do GitHub deste repositório pode não exibir o selo automático de fork; isso não altera a atribuição da origem do código.

## Objetivo e estado atual

O objetivo de desempenho deste fork é executar o jogo a **30 quadros reais por segundo**, com a cena renderizada na resolução nativa de **1920 × 1080**, em hardware Apple Silicon recente — especialmente iPhone 17 Pro com A19 Pro.

O projeto separa três coisas que não devem ser confundidas:

- **Limite de FPS:** configuração que impede o jogo de ultrapassar uma taxa escolhida.
- **FPS efetivamente sustentado:** quantidade de quadros completos que o jogo e a GPU conseguem produzir na cena testada.
- **Taxa de apresentação da tela:** frequência com que o iOS apresenta imagens no display. Uma tela de 120 Hz não transforma, por si só, 25 FPS reais em 30 ou 60 FPS.

O estado do projeto é experimental. Há evidências documentadas de inicialização, menus, vídeo de introdução, áudio e gameplay em aparelho real, além de otimizações que elevaram cenas de aproximadamente 8–12 FPS para perto de 27 FPS. Isso **não significa** que todas as cenas sustentem 30 FPS, que a renderização esteja livre de defeitos ou que a meta de 1080p/30 esteja concluída. Compatibilidade, estabilidade, temperatura, memória e desempenho ainda dependem de validação no dispositivo.

## Origem e linhagem do código

A cadeia principal de proveniência é:

1. **[SpartanPort](https://github.com/FelipePrado0/SpartanPort)** — port comunitário de PC de God of War III Remastered; origem histórica da base de runtime e do trabalho de compatibilidade do jogo.
2. **[gow3_android](https://github.com/wyatt-poole/gow3_android)** — adaptação Android da base SpartanPort, com FEXCore para executar o código x86-64 em ARM64 e com a camada gráfica shadPS4/Vulkan. O repositório declara SpartanPort como seu repositório pai.
3. **Este fork iOS** — preserva e adapta essa base para Darwin/iOS, substituindo a integração Android, o caminho de janela e partes de memória, JIT, entrada, áudio e empacotamento.

A importação do runtime de gow3_android e as alterações posteriores estão registradas no histórico Git. O documento [docs/AUDIT.md](docs/AUDIT.md) registra a auditoria técnica da migração Linux/Android → iOS, incluindo as diferenças de memória virtual, sinais, ABI, JIT, loader e GPU.

## Como funciona

Visão simplificada do caminho de execução:

```text
Aplicativo iOS (Expo / React Native)
├── Launcher, configurações, importação do dump e estado do JIT
└── Módulo nativo gow3-core (Swift / Objective-C++)
    ├── UIViewController + CAMetalLayer
    ├── Controles táteis e integração com controles externos
    └── Bibliotecas nativas estáticas
        ├── Runtime GoW3 / HLE de serviços PS4
        ├── FEXCore: tradução dinâmica x86-64 → ARM64
        └── shadPS4 video core
            └── Vulkan → MoltenVK → Metal → GPU Apple
```

- **Aplicativo:** Expo e React Native cuidam do launcher, das configurações, da seleção dos arquivos do usuário e da interface.
- **Renderização do jogo:** o React Native não desenha o jogo. Durante a execução, uma view/controller nativa apresenta o conteúdo por uma `CAMetalLayer`.
- **CPU:** FEXCore traduz blocos de código x86-64 do jogo para ARM64 em tempo de execução. O projeto inclui adaptações para Darwin e para o mecanismo JIT do iOS.
- **Serviços do console:** o runtime do port implementa/substitui os serviços PS4 necessários ao jogo.
- **GPU:** o video core derivado do shadPS4 traduz o trabalho gráfico para Vulkan; MoltenVK converte Vulkan para Metal.
- **Áudio e controles:** as integrações são adaptadas para o ciclo de vida de um aplicativo iOS, sem iniciar uma segunda aplicação ou depender do SDL como proprietário de `UIApplication`.

## Histórico do desenvolvimento para iOS 26

O histórico abaixo organiza os marcos técnicos documentados no repositório. Ele é uma síntese de etapas, não uma alegação de que cada tentativa intermediária tenha sido bem-sucedida.

### Setembro de 2026 — criação da base de trabalho

- **8–12 de setembro:** início da montagem do repositório e importação dos arquivos-base, com os primeiros commits de preparação do projeto iOS.
- Organização inicial do código do aplicativo, runtime, GPU, ferramentas e dependências.
- Definição da estratégia de manter o código específico de iOS isolado sempre que possível, reduzindo o impacto sobre a base compartilhada com PC/Android.

### Outubro de 2026 — portabilidade do runtime e JIT

- **Auditoria de portabilidade:** levantamento das dependências Linux/Android em memória virtual, sinais, contexto de CPU, chamadas de sistema, loader, threads, janela, áudio e entrada. Os resultados estão em [docs/AUDIT.md](docs/AUDIT.md).
- **Memória Darwin:** substituição de mecanismos Linux como `memfd_create`, `MAP_NORESERVE` e operações de leitura de memória por caminhos compatíveis com Mach VM/Darwin, preservando o layout de memória exigido pelo runtime.
- **Páginas de 16 KiB:** validação das premissas de page size e adaptação dos caminhos de proteção/fault para o comportamento de SIGBUS/SIGSEGV no Darwin.
- **FEXCore no iOS:** compilação nativa das bibliotecas FEXCore para iOS/ARM64 e adaptação de alocação, recursos da CPU host e contexto de sinais.
- **20 de outubro — primeiro marco de execução JIT:** o self-test nativo e os testes de tradução FEXCore passaram em um iPhone 17 com JIT habilitado. Os resultados de memória, endereçamento e JIT foram documentados na auditoria.
- **21 de outubro — JIT integrado ao aplicativo:** inclusão do helper de JIT baseado em StikJIT, com alocação de pool executável e alias de escrita. O teste de execução traduzida retornou o resultado esperado no aparelho.
- **Pareamento:** integração do fluxo de pareamento no aplicativo, baseada no trabalho de Madeira. O pareamento dentro do app depende de iOS 27 ou posterior; o helper/JIT documentado tem suporte a partir do iOS 26, conforme as condições do sideload e do debugger.

### Outubro de 2026 — GPU, janela e primeiro boot do jogo

- Integração do MoltenVK e criação do caminho de superfície Metal nativa.
- Compilação da biblioteca gráfica baseada no video core shadPS4 para ARM64/iOS.
- Integração das bibliotecas nativas ao módulo Expo local e ao aplicativo.
- **22 de outubro — primeiro boot documentado:** o jogo chegou à tela de brilho, menus e vídeo de introdução no iPhone 17; entrada por DualSense também foi observada. A partida nova ainda apresentava crash nessa etapa.
- **0.1.23 — correção de crash em hooks:** stubs de código usados pelos hooks do runtime passaram a ser registrados corretamente como regiões executáveis para o FEXCore.
- **0.1.24 — primeira grande otimização gráfica documentada:** correção do caminho de MSAA para evitar o custo de multisampling forçado em targets de cor e redução do tamanho excessivo da superfície de apresentação. As medições registradas passaram de aproximadamente 8–12 FPS para perto de 27 FPS em gameplay.
- **0.1.25–0.1.27 — instrumentação e investigação de corrupção gráfica:** inclusão de mecanismos de diagnóstico, captura de frame e alternância de otimizações; investigação de descritores Vulkan no MoltenVK 1.4.1+ e adoção do caminho de descriptor sets como mitigação testável.
- **0.1.28–0.1.32 — investigação de texturas e custo por passe:** capturas e verificações de texturas, testes de caches, bindings, tracking e pipelines. Os registros indicam que a corrupção persistia em determinadas cenas e que várias hipóteses foram descartadas. Não se deve interpretar esses testes como prova de que o problema gráfico foi totalmente resolvido.

### Final de outubro e novembro de 2026 — desempenho, resolução e distribuição

- Inclusão de ferramentas de diagnóstico no próprio aparelho, como `env.txt`, `toggles.txt`, `capture.txt` e perfil de GPU por passe.
- Análise do custo de renderização em GPU Apple tile-based e otimização da continuidade de dynamic rendering quando os attachments permanecem compatíveis, evitando encerramentos/reinícios de passe apenas para alterar metadados de clear.
- Revisão da meta de desempenho: a resolução de cena nativa **1920 × 1080** foi restaurada como objetivo/configuração padrão; o escalonamento de cena não deve ser usado para mascarar a falta de desempenho.
- Consolidação do CI em um único workflow iOS: validação rápida no Linux, compilação nativa no macOS, build Expo/Xcode, helper JIT e empacotamento IPA.
- **4 de novembro:** registro formal da meta 1080p/30 e das medições disponíveis em [docs/PERFORMANCE-2026-11-04.md](docs/PERFORMANCE-2026-11-04.md). O documento também lista o que ainda precisa ser medido no aparelho.
- O número de versão do app e os commits mais recentes devem ser consultados no próprio repositório; a evolução não é representada por uma única build final.

## Compatibilidade e requisitos

### Dispositivo e sistema

- Projeto direcionado a dispositivos iOS com Apple Silicon; validação documentada em iPhone 17.
- O trabalho de JIT foi desenvolvido para o ambiente de sideload/debugger do iOS 26 em diante.
- Algumas funções de pareamento integrado exigem iOS 27 ou posterior. Consulte [docs/JIT.md](docs/JIT.md) antes de escolher o método de ativação.
- A configuração de build atual declara deployment target iOS 17.0; isso é o mínimo de compilação configurado, **não** uma garantia de que todos os recursos de JIT funcionem em iOS 17.
- Um sideloader compatível, Developer Mode e a configuração de JIT são necessários para executar o código x86-64 traduzido.

### Dump do jogo

O usuário deve fornecer uma cópia própria e preparada de God of War III Remastered para PS4. A linhagem upstream documenta os serials CUSA01623, CUSA01715 e CUSA01720 e a atualização 01.02. A compatibilidade de cada dump/região deve ser confirmada na prática.

**Não compartilhe nem solicite que terceiros enviem arquivos protegidos do jogo.** Este projeto não inclui e não hospeda `eboot.bin`, módulos PS4, atualizações ou assets.

## Preparação do jogo

O fluxo do jogo segue a preparação do projeto upstream: os arquivos do dump devem ser preparados fora do aplicativo conforme as ferramentas e instruções da base original e, em seguida, importados para o espaço de arquivos do app.

- Consulte a documentação e as ferramentas da base [gow3_android](https://github.com/wyatt-poole/gow3_android) e [SpartanPort](https://github.com/FelipePrado0/SpartanPort) para entender a estrutura do dump e os arquivos esperados.
- A estrutura preparada deve conter o executável e os diretórios de sistema do jogo esperados pelo loader.
- O usuário é responsável por possuir o jogo e por cumprir a legislação aplicável à criação e utilização de dumps pessoais.

O fluxo de preparação diretamente no iPhone e a compatibilidade de todos os formatos de pacote não devem ser considerados concluídos sem documentação e teste específicos.

## Instalação e JIT

O CI produz um IPA para instalação por sideload. O pacote não é uma distribuição App Store e não contém o jogo.

1. Obtenha o IPA em um artefato de uma execução concluída do workflow ou em uma release publicada.
2. Instale usando um sideloader compatível, observando as exigências de assinatura e entitlements.
3. Ative Developer Mode e configure o JIT seguindo [docs/JIT.md](docs/JIT.md).
4. Importe os arquivos do jogo preparados pelo próprio usuário.
5. Inicie o jogo pelo aplicativo e consulte os logs em caso de falha.

**JIT e assinatura:** iOS impõe restrições de execução de memória a aplicativos sideloaded. O projeto utiliza o fluxo de helper/debugger documentado em `docs/JIT.md`. O resultado depende do método de assinatura, dos entitlements efetivamente preservados pelo sideloader e da versão do iOS. Não presuma que SideStore, AltStore ou outro assinador preserve os mesmos entitlements em todas as configurações.

## Compilação a partir do código-fonte

A compilação oficial é feita pelo GitHub Actions em runners macOS, pois o build iOS exige Xcode e SDKs da Apple.

### Pré-requisitos

- macOS com Xcode estável compatível com o projeto.
- CMake, Ninja, Node.js 22, npm, Rust/Cargo, ferramentas de linha de comando e dependências listadas pelos scripts.
- Acesso aos submódulos e às dependências de terceiros.
- Para instalação no dispositivo: certificado/perfil ou sideloader compatível e configuração de JIT.

### Build automatizado

O workflow principal é:

- [`.github/workflows/ios.yml`](.github/workflows/ios.yml)

Ele executa, em sequência:

1. Checkout da branch.
2. Testes de runtime independentes de plataforma no Linux.
3. Restauração do cache de bibliotecas nativas quando a chave corresponde ao código e às ferramentas.
4. Quando necessário, compilação do FEXCore, runtime e GPU para iOS/ARM64 por `native/scripts/build-ios.sh`.
5. Compilação da biblioteca de pareamento Rust.
6. `npm ci` e `expo prebuild -p ios --clean`.
7. Build Xcode sem assinatura de distribuição.
8. Compilação/integração do helper JIT.
9. Empacotamento do aplicativo em IPA e upload dos logs e artefatos.

### Build local

Os scripts de build e suas opções são a referência; evite reproduzir manualmente etapas que o workflow já executa. Em um Mac, o fluxo principal do núcleo nativo é:

```bash
native/scripts/fetch-submodules.sh
native/scripts/build-ios.sh build/native-ios
```

Depois, o aplicativo pode ser preparado e compilado com os scripts/etapas equivalentes do workflow. A assinatura final e a ativação de JIT dependem do ambiente Apple e do sideloader.

## Estrutura do repositório

| Caminho | Responsabilidade |
|---|---|
| `app/` | Aplicativo Expo/React Native, launcher e módulo nativo local |
| `app/modules/gow3-core/` | Integração Swift/Objective-C++ com o runtime e a view Metal |
| `native/cpu/` | Integração de CPU e FEXCore para Darwin/ARM64 |
| `native/jit/` | Pool de memória executável e suporte ao JIT |
| `native/jit-helper/` | Extensão auxiliar para habilitar JIT |
| `native/rppairing/` | Biblioteca Rust usada no pareamento compatível |
| `native/runtime/` | Runtime GoW3, serviços, input, loader e camada GPU |
| `native/scripts/` | Scripts de dependências, compilação e integração |
| `docs/` | Auditorias, resultados de aparelho, handovers e diagnóstico |
| `.github/workflows/ios.yml` | Validação, compilação e empacotamento do IPA |

## Diagnóstico e desempenho

Documentos de referência:

- [Auditoria de portabilidade](docs/AUDIT.md) — diferenças entre Linux/Android e Darwin/iOS.
- [JIT integrado](docs/JIT.md) — helper, pareamento e limitações por versão do iOS.
- [Histórico de diagnóstico](docs/NEXT.md) — experimentos, resultados e hipóteses já descartadas.
- [Status de outubro](docs/STATUS-2026-10-23.md) — marcos de estabilidade, GPU e texturas.
- [Desempenho e meta 1080p/30](docs/PERFORMANCE-2026-11-04.md) — medições, otimizações e plano de validação.

Para medir desempenho real, use a mesma cena/save, aparelho em condição térmica comparável e logs sem profiler intrusivo. Registre frame time, FPS efetivo, tempo de GPU por passe, draw count e estado térmico. O contador limitado a 30 FPS não comprova 30 FPS sustentados. CI comprova compilação e testes automatizados; não comprova desempenho ou estabilidade em gameplay no iPhone.

## Créditos e agradecimentos

Este fork existe porque vários projetos e desenvolvedores construíram as camadas que tornaram a adaptação possível. Os créditos abaixo distinguem a linhagem original das contribuições e referências específicas de iOS. A inclusão nesta lista reconhece trabalho e proveniência; não implica endosso deste fork pelos autores.

### Linhagem original e contribuições legadas

- **[Felipe Prado e colaboradores — SpartanPort](https://github.com/FelipePrado0/SpartanPort):** port comunitário de PC de God of War III Remastered e base histórica do código que originou a linhagem utilizada aqui.
- **[Wyatt Poole — gow3_android](https://github.com/wyatt-poole/gow3_android):** adaptação Android e integração ARM64/FEXCore; o runtime e o video core utilizados por este fork descendem desse trabalho.
- **[shadPS4](https://github.com/shadps4-emu/shadPS4):** video core e infraestrutura de tradução gráfica Vulkan para a arquitetura PS4.
- **[FEX-Emu](https://github.com/FEX-Emu/FEX):** tradutor dinâmico de código x86-64 para ARM64.
- **[Bloodborne-Android](https://github.com/ducvd89/Bloodborne-Android):** referências e componentes históricos utilizados na integração Android da linhagem gow3_android.
- **[deadinside28 — bloodborne_pc](https://github.com/deadinside28/bloodborne_pc):** referência de runtime/integração citada pela base Android.
- **[fexdroid](https://github.com/cobrabm12/fexdroid):** referências para pontes de display e input da integração Android.
- **[Mesa](https://mesa3d.org/):** projeto de drivers gráficos e infraestrutura Vulkan; Turnip pertence à linhagem Android, não ao backend iOS deste fork.
- **[ps4-pkg-tools](https://github.com/xXJSONDeruloXx/ps4-pkg-tools):** ferramenta referenciada pela linhagem Android para operações com pacotes PS4.

### Portabilidade iOS, JIT e referências recentes

- **[Will Faust — FEX iOS port](https://github.com/willfaust/FEX/tree/ios-port-2607):** referência de alterações FEX para Darwin/iOS, incluindo JIT dual-mapped e compatibilidade com o ambiente Apple.
- **[Will Faust — Madeira](https://github.com/willfaust/Madeira):** referência para execução x86-64 em iOS, integração JIT, pareamento no próprio dispositivo e decisões de arquitetura de aplicativo.
- **[EnermaxFR — MaxPS4](https://github.com/EnermaxFR/MaxPS4):** referência exploratória para FEXCore standalone, JIT e build iOS.
- **[StikJIT](https://github.com/StephenDev0/StikJIT):** infraestrutura utilizada pelo helper de JIT; respeitar a licença MPL-2.0 e os avisos do componente.
- **[LocalDevVPN](https://github.com/LocalDevVPN/LocalDevVPN):** componente/referência de conectividade local usado pelo fluxo de pareamento documentado.
- **[KytyPS5 — PR #1083](https://github.com/KytyPS5/KytyPS5/pull/1083):** investigação de referência sobre metadados de push descriptors no MoltenVK.

### Bibliotecas e projetos de terceiros

- **[KhronosGroup — Vulkan-Headers](https://github.com/KhronosGroup/Vulkan-Headers)** e **[MoltenVK](https://github.com/KhronosGroup/MoltenVK):** APIs Vulkan e implementação Vulkan sobre Metal.
- **[Dear ImGui](https://github.com/ocornut/imgui):** interface gráfica imediata.
- **[Vulkan Memory Allocator](https://github.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator):** gerenciamento de alocação de memória Vulkan.
- **[LibAtrac9](https://github.com/Thealexbarney/LibAtrac9):** decodificação ATRAC9.
- **[magic_enum](https://github.com/Neargye/magic_enum):** utilitários de enumeração C++.
- **[miniz](https://github.com/richgel999/miniz):** biblioteca de compressão.
- **[robin-map](https://github.com/Tessil/robin-map):** containers hash map.
- **[SDL](https://github.com/libsdl-org/SDL):** componentes de áudio/input usados pela base e adaptados conforme a plataforma.
- **[Expo](https://github.com/expo/expo)** e **[React Native](https://github.com/facebook/react-native):** shell do aplicativo e integração multiplataforma.
- **[Rust](https://www.rust-lang.org/):** linguagem usada na biblioteca de pareamento do projeto.

Se algum autor ou projeto foi omitido, abra uma issue ou pull request com a referência exata e a contribuição correspondente para que os créditos possam ser corrigidos.

## Licença e avisos legais

O repositório distribui o código sob **GNU General Public License v3.0**, conforme o arquivo [LICENSE](LICENSE). Componentes de terceiros podem ter licenças próprias; consulte os arquivos de licença e avisos de cada dependência e submódulo.

God of War é uma marca registrada de seus respectivos titulares. Este é um projeto independente, sem vínculo com Sony Interactive Entertainment ou Santa Monica Studio. O usuário é responsável por obter e utilizar seus próprios arquivos de jogo de forma legal. Nenhum conteúdo proprietário do jogo é fornecido por este repositório.
