# XOWUE — X-Men Origins: Wolverine (Xbox 360)

**Title ID:** 41560816
**Branch:** XOWUE
**Último teste em aparelho:** Build 6 (Action #19, sucesso). O próximo IPA contém o adapter corrigido para o bloqueio APC observado nesse build.

## Estado do runner

No Build 6, o iPhone validou o XEX2 (base `0x82000000`, entry `0x82C3CAA8`, 261 imports), executou `XGetVideoMode` e inicializou o ring buffer Xenos. A chamada seguinte, `KiApcNormalRoutineNop`, era tratada pelo gerador como import não implementado, embora o Xenia a exporte como stub que retorna zero. Esta revisão liga esse adapter e registra o retorno no runtime.

O diagnóstico do Build 6 registrou `guest_frames=0`, `guest_swaps=0`, `draws=0` e `rptr=0`; a falha ocorreu antes da primeira submissão gráfica. A próxima execução deve verificar o avanço do boot. O caminho real de imagem permanece em KosmicKrisp.

## App, arquivos e relatórios

- A pasta local é Arquivos → No Meu iPhone → XOWUE → Jogos.
- O app detecta default.xex na raiz de Jogos ou em uma subpasta. O seletor também aceita pasta ou executável.
- Build aparece no cabeçalho do app e é gravado em CFBundleVersion.
- Diagnósticos ficam na raiz Documentos com os nomes diagnostico-build-N.txt e crash-build-N.txt.
- O IPA não inclui default.xex nem assets do jogo e precisa de assinatura Apple para instalação.

## Gráficos

KosmicKrisp permanece o backend Vulkan → Metal; o Build 6 confirmou device, surface, swapchain e presents do host na Apple A19 Pro. O runtime lê o ring Xenos, processa buffers indiretos, reconhece swaps e decodifica framebuffer em dois formatos. Ainda não executa os opcodes de draw nem traduz estado e shaders do jogo; por isso, o contador de draws reais segue em zero até o XEX avançar e enviar comandos.

## Compile e continuidade

Leia HANDOFF-XOWUE.md para comandos do build host, execução no telefone, diagnóstico e handoff para o próximo agente. Leia THIRD_PARTY_NOTICES.md antes de redistribuir artefatos.

O IPA mais recente é publicado como artifact do workflow [XOWUE iOS IPA](https://github.com/joao9vegeto-stack/KintTany/actions/workflows/xowue-ios.yml). Somente uma Action concluída com sucesso gera um novo número de Build.

O jogo, WGame, DLC, title updates e assets derivados permanecem fora do Git.
