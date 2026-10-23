# Auditoria da Build 14 e do caminho gráfico XOWUE

## Evidência do dispositivo

A Build 14 abriu o app, carregou o `default.xex` do Title ID `41560816`, validou 12 seções e resolveu 261 imports. O entry point do XEX é `0x82C3CAA8`. O LiveContainer terminou a execução com o guard PPC, sem um crash do processo.

O ponto de parada foi `sub_8237CA18`: `guestTarget=0x8237CAE8`, mas esse endereço é um bloco local da própria função, não uma função exportada. O XEX contém uma tabela absoluta de 11 entradas em `0x8237CAA4`; depois da subtração do seletor em r11, a terceira entrada aponta para `0x8237CAE8`. A sequência que prepara o BCTR em `0x8237CA64` ordena as instruções diferentemente do padrão detectado pelo XenonAnalyse. O `LR/callsite` impresso no log é um candidato antigo do prólogo, não o endereço real do BCTR.

A telemetria marcou 24 opcodes de draw no ring PM4, mas `swaps=0` e `frames=0`. Esses 24 são contagens de comandos; não provam que vértices foram submetidos à GPU.

## Correção incluída

A tabela foi extraída do XEX e validada como controle local da função. O workflow agora aplica `tools/patch_xowue_manual_switches.py` depois de extrair a fonte AOT e antes da compilação. O script verifica a função, a redução do seletor, o guard default, todos os rótulos e os destinos; não transforma blocos internos em funções falsas.

A validação local gerou 37 tabelas mantidas, removeu uma tabela que representa chamadas de função, comparou o corpo recompilado byte a byte com a saída do XenonRecomp usando a tabela manual e confirmou que a aplicação repetida não muda o arquivo.

Isso remove a parada observada na Build 14. Ainda precisa de execução no dispositivo para confirmar até onde o jogo avança depois do BCTR.

## Comparação das referências

| Projeto | Execução e backend | O que serve de referência para XOWUE |
|---|---|---|
| [MCX360 Edition](https://github.com/DevZer0D4Y/MCX360-EDITION) | Recompilação estática com ReXGlue; Vulkan sobre Metal via MoltenVK. O CMake do app liga o runtime ReXGlue, o plugin gráfico Xenos e MoltenVK. | A referência mais próxima para integrar AOT e um command processor Xenos genérico. A infraestrutura inclui decoding de comandos, primitivas, shaders Xenos, texturas/render targets e backend Vulkan. |
| [Theft4](https://github.com/KoreanSeats1/Theft4) | Recompilação estática de GTA IV, com backend Metal específico do título além da fundação ReXGlue/LibertyRecomp. | Mostra a integração Metal e passes do jogo, mas seus shaders, estados e passes de GTA IV não são diretamente os de Wolverine. |
| [MCLA 4iOS](https://github.com/KoreanSeats1/MCLA-4iOS) | LARecomp/ReXGlue com renderer Metal específico de Midnight Club; a documentação declara 603 shaders empacotados. | Evidencia o trabalho de cobertura de shaders por título. A lista atual de problemas ainda registra dois programas de shader ausentes e quatro draws rejeitados. |
| [SpeedBreaker iOS](https://github.com/SpeedBreakerProject/speedbreaker/blob/main/scripts/ios/README.md) | Recompilação estática de Need for Speed: Most Wanted, renderer Xenos/Vulkan e MoltenVK no iOS. | Demonstra um segundo caminho Vulkan para iOS e uma cadeia explícita de dependências; o README classifica a distribuição IPA como experimental. |

## Diferença atual no XOWUE

O XOWUE tem código AOT e um backend iOS Vulkan/Metal para apresentar buffers RGBA de CPU. O módulo KosmicKrisp preservado na branch é um teste de WSI/surface, não um renderer Xenos; o backend não converte comandos da GPU Xbox em comandos Vulkan/Metal.

O caminho atual lê/contabiliza alguns pacotes PM4 e reconhece um conjunto limitado de formatos em `VdSwap`. Ainda não liga os comandos Xenos de desenho a uma implementação que decodifique estado e primitivas, traduza shaders do jogo, construa pipelines, mantenha texturas/render targets, emule EDRAM/ROP ou faça resolve para o buffer apresentado. Por isso `draws>0` pode coexistir com `swaps=0` e tela preta.

As quatro referências confirmam que AOT por si só não basta: cada port acopla uma implementação Xenos/D3D funcional ao backend da plataforma e precisa de shaders/cobertura próprios do jogo. A correção desta revisão elimina o bloqueio de fluxo observado; ela não declara o renderer completo nem um frame de Wolverine.

## Fontes do XOWUE

- [Build workflow](../.github/workflows/xowue-ios.yml)
- [Tabelas PPC](../generated/config/XOWUE_switch_tables.toml)
- [Resumo da recompilação](../generated/config/XOWUE-recompile-summary.md)
- [KosmicKrisp WSI](../Runtime/Graphics/KosmicKrisp/README.md)
