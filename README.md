# AscensionRecomp — PS3 → iOS ARM64

**Branch de trabalho:** `AscensionRecomp` · **Versão de software em preparação:** M7.73.0

O objetivo é executar God of War: Ascension nativamente em iPhone, usando código
PPU/SPU recompilado para ARM64 e serviços de sistema iOS. O app não executa
código PowerPC por interpretador no caminho M7.73. A cópia do jogo e o ELF são
fornecidos pelo proprietário e ficam no dispositivo.

## Estado atual

- O workflow monta o lift PS3Recomp validado para `NPUA80918`: 29.849 funções
  PPU completas e quatro imagens SPU.
- A entrada do ELF `0x00010410` é chamada como uma função AOT completa, com a
  preparação de thread, TOC, PT_TLS, pilha, `argv` e continuações do
  `ppu_run()` upstream.
- O launcher permite importar o ELF validado, escolher a pasta do jogo, iniciar
  em uma fila de execução fora da interface e abrir um relatório ao vivo de
  chamadas AOT e atividade guest de arquivos.
- A bancada RSX/Metal disponível é sintética. O app ainda não apresentou um
  quadro de Ascension, menu ou gameplay. Não há medição de FPS do jogo no iOS.
- O app gerado pelo workflow é uma IPA iOS sem assinatura. A instalação depende
  do método de sideload do aparelho.

O gate do próximo run físico é observar chamadas AOT aumentando e, em seguida,
leituras guest bem-sucedidas de arquivos do jogo. Depois, falta conectar a
saída RSX ao renderer Metal e alcançar o primeiro quadro real. Versão M7.73.0
não significa que o marco de gameplay M7 foi aprovado. Consulte
[`docs/AUDITORIA-FLUXO-IOS-M7.72.md`](docs/AUDITORIA-FLUXO-IOS-M7.72.md) para a
análise das causas, a comparação com os ports de PC e GoW2 e o estado de cada
critério.

## Build

Um commit na branch `AscensionRecomp` dispara o workflow iOS em
`.github/workflows/ascension-recomp-m0.yml`. O job recompila a tabela completa,
confere os símbolos no Mach-O final, empacota a IPA e publica logs e artefato
temporário do GitHub Actions. CI comprova compilação e link ARM64; execução em
um iPhone continua sendo necessária para comprovar comportamento guest.

Não edite `main` nem outras branches para este port. O runtime PS3Recomp é
fixado pelo workflow; o código do renderer de PC não é uma dependência de iOS.

## Referências

- [PS3Recomp](https://github.com/sp00nznet/ps3recomp): lifter, runtime e
  processo de entrada PPU.
- [GoW2 Recomp](https://github.com/andrebrumdev/gow2-recomp): ciclo de vida
  nativo iOS/SwiftUI e referência de primeiro frame.
- [Ascension PC](https://github.com/arnaldolima1/gow-ascension-pc): fluxo de
  launcher, renderer de PC e patches específicos de SPURS/GCM/SPU.
- [GoW3 Android](https://github.com/zFitness/gow3_android/tree/android):
  referência de launcher, importação e configurações mobile.

Os ports de PC e GoW2 usam revisões, regiões do ELF e backends próprios. Seus
dados de jogo, shaders e patches não entram automaticamente neste binário iOS.
