# Atualização da fonte comprovada — 22/11/2026

O usuário forneceu a IPA original: https://drive.google.com/file/d/1cd85ZhbrJXZo5VK1GMQPxA-8R17qpPPD/view?usp=drivesdk. Metadados lidos pelo Drive: nome OcarinaOfTime-HookLink2iOS.ipa, 3.476.939.759 bytes, criada em 13/11/2026, na pasta HookLink2iOS; uma conta de serviço tem permissão writer. Não foi possível baixar localmente a IPA inteira pelo conector devido ao limite de 256 MiB por download; o Actions usa a própria API Google em chunks de 16 MiB e verifica MD5 oficial antes de repack.

O workflow .github/workflows/hooklink2ios-perf-repack.yml aceita explicitamente o ID e por padrão usa esta IPA. O modo inicial no novo launcher é balanced30fg (30 quadros reais mais intermediários MetalFX até 60 mostrados), com opções 30 e 60 preservadas. Sem recompilação de shader, sem NUP, sem portar X2 incompatível.

**Correção fundamental:** alterar apenas dm/env.txt não é suficiente nem garante que os presets surtam efeito, porque o launcher pode fixar ou substituir os mesmos parâmetros. Agora scripts/hooklink2ios_perf_repack.py valida dm/launcher.json e altera seus valores padrão, mantendo DM_FRAME_MODE selecionável, opções de FPS de 30 e 60, escolhas persistidas e Documents/env.txt. A configuração de usuário salva pode continuar substituindo o padrão; use Reset to defaults no launcher para medir o perfil novo se você já personalizou os modos.

**Limite técnico:** ainda não há port de código nativo X2, pois sem relink validado da imagem do jogo e da cadeia de shaders seria arriscar a IPA original. As alterações deste commit são pipeline/repack/launcher e não afirmam otimizações de CPU/GPU de código novo. Nenhuma medição de FPS no iPhone foi feita neste commit.

---

# HookLink2iOS — auditoria e repack incremental (22/11/2026)

## Base e limites

Branch HookLink2iOS: 9dbf0208472c36e3f4c657f7fcf146006e69f517 (13/11/2026).
NXNative do build validado: cf2a2fecc6ce3fb841131ffeffa90915cdadf109.
HookLink original X2.0.1: 698b46bc5b14510fffc0a4b8fd4bf78309004e4c; 345 commits à frente.

A cadeia de tradução Metal mudou entre as versões. dmsh_xlate passou de b59d042d9425c229 para ce15b871c7dc0a2d e xlate_source de 657232fd201f16a1 para c75f3cb403920cde. O cache de shader do build antigo não pode ser declarado compatível com a engine X2. Este repack NÃO atualiza motor nem compila shader.

## Testes efetivos no iPhone 17 Pro

- Build #18: run 43429056395 concluído com sucesso em 13/11/2026; 42.848 bibliotecas Metal iOS e IPA 3.476.939.759 bytes; RomFS externo e GPU none, sem PSO .mtl4a offline.
- Em 22/11, a API do Actions retornou zero artefatos para o run #18. Sucesso histórico NÃO significa IPA disponível para download hoje.
- Primeiro boot falhou em reserva virtual e passou após ativar Increased Memory Limit; outro encerramento veio da proteção de armazenamento (menos de 2 GB livres, pipeline cache perto de 9,17 GB). Não desligar os guards.
- Perfil padrão: 29,0 FPS, frame p50 34,31 ms, GPU p50 31,65 ms. Perfil experimental anterior PIOROU: 26,3 FPS, frame p50 37,96 ms, GPU p50 35,45 ms. Ambos estado térmico 2.
- Outra sessão (~11m18s) atingiu janela 59,8 FPS, GPU mediana 5,40 ms, sem descartes em 300 frames, depois 47,6–53,8 FPS por carga e compilação de pipelines, com aquecimento. SIGSEGV reportado na saída para o Shell, não comprovado como crash de gameplay.

## Implementação (sem full build)

- scripts/hooklink2ios_perf_repack.py: recebe IPA ou ZIP de artefato com exatamente uma IPA, valida Title ID 0400486024DEC000, update v131072, iOS 26, DmIOS.app, msl/b-*.img, marcador RomFS externo; muda apenas dm/env.txt, preserva CRC/tamanho dos shaders, re-assina ad hoc no macOS e gera relatório SHA-256. A assinatura final deve ser aplicada pelo instalador do usuário.
- scripts/hooklink2ios_fetch_source.py: fonte por artifact ID GitHub ou ID Drive de IPA/ZIP real, baixa com HTTP Range de 16 MiB, retoma e valida bytes/digest quando disponível. Não baixa NSP/NUP/romfs.
- .github/workflows/hooklink2ios-perf-repack.yml: SOMENTE workflow_dispatch, branch HookLink2iOS, runner xcode-27, um job; rejeita fonte inexistente, publica apenas IPA de repack válida e relatório. Nenhuma recompilação de jogo/shaders e nenhum fallback silencioso ao NUP.
- colab/HookLink2iOS_IPA_Chunks.ipynb: busca a última execução success COM artefato disponível desta branch; Actions → Colab em chunks Range 16 MiB; extração da IPA em blocos, verificação SHA-256, ZIP CRC, Title ID e imagem Metal; Colab → Drive por upload resumable de 16 MiB, MD5 e readback. Admite cópia anterior no Drive/Colab quando o Actions está expirado.

## Presets

- stable30: DM_FRAME_MODE=1; resolução dinâmica e MetalFX; DM_RT_COMP=auto, FPS monitor. 30 quadros reais.
- balanced30fg: DM_FRAME_MODE=2; DM_FRAMEGEN_SCALE=0.75; MetalFX e resolução dinâmica. Render 30 + mostra até 60 interpolados, não representa 60 FPS de lógica/entrada.
- native60: DM_FRAME_MODE=0; DM_FPS_TARGET=60; DM_FRAMEGEN=0; resolução dinâmica e MetalFX. Não há garantia de 60 contínuos ao aquecer.

Preservar os ajustes não envolvidos: DM_QOS_MAP, DM_THERMAL_CAP, memória, proteção de armazenamento. Documents/env.txt do usuário tem prioridade sobre dm/env.txt do app.

## Não portável apenas por env/repack

As melhorias X1/X2 de threads A19, texture table reuse, liberação de render targets em lotes, limite de espera por pipeline, 12.188 entradas de prewarm, Shadow Half/Quarter, ampliação alias VA para 16 GiB, render scale hook e correções de GPU/pool exigem novo binário, compatibilidade de shader e testes. Não são falsamente marcadas como implementadas.

## Execução

1. Identifique uma cópia IPA real e íntegra (o run #18 não a oferece pela API).
2. Guarde saves, cache e Documents/env.txt; não desinstale o app.
3. Actions → HookLink2iOS - safe no-shader IPA repack → Run workflow na branch HookLink2iOS; informe source_artifact_id NÃO expirado OU source_drive_file_id compartilhado com o Service Account; selecione preset.
4. Após repack verde, abra o notebook no Safari/Colab e transfira em chunks ao Drive/HookLink2iOS/ipa.
5. Meça FPS/tempo de quadro p50/p95, tempo de GPU, temperatura, transições e saída para o Shell em sessões de 20–30 minutos. Sem IPA de origem, não é possível gerar outra sem recompilar.

Referências: https://github.com/joao9vegeto-stack/KintTany/actions/runs/43429056395
https://github.com/dsi-hub/HookLink/blob/main/CHANGELOG.md
https://github.com/dsi-hub/nxnative/compare/cf2a2fecc6ce3fb841131ffeffa90915cdadf109...698b46bc5b14510fffc0a4b8fd4bf78309004e4c
