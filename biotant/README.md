# BioiOSMutant — Biomutant para iOS 26

**Origem Git:** `BladesTime` (sem alterar a branch original). **Title ID:** `01004BA017CD6000`.  
**Pasta do Google Drive:** [biotant](https://drive.google.com/drive/folders/1yrL87jYVf08FGB2eWV5CY0jBp2OTHYAs) sob a pasta principal `19HXEJCK-26NfBVKeUP3wqFxMFpoF3ykm`.

## Notebook Colab

Abrir [BioiOSMutant_Biomutant.ipynb](colab/BioiOSMutant_Biomutant.ipynb) no Colab e executar em ordem:

1. Autenticar Google Drive.
2. Clonar/atualizar exclusivamente a branch `BioiOSMutant`.
3. **RAR → NSP → Drive, em chunks**: baixa os dois RARs com **6 conexões HTTP Range paralelas e blocos de 64 MiB**, índice SHA-256 por bloco e retomada de blocos íntegros; caso o host ignore Range, usa **streaming sequencial de 8 MiB** informado no log. Descompacta **um RAR por vez no Linux**, confere assinatura PFS0, envia `base.nsp` e `update.nsp` à pasta `biotant` em uploads retomáveis de 64 MiB, confere tamanho/MD5 remoto e só então apaga o RAR. Se já existir no Drive, não repete o download. URLs temporárias podem expirar.
4. Recuperar um handoff já verificado em `biotant/BioiOSMutant_Biomutant_*/handoff.json`, quando existir.
5. Se não existir handoff, executar `build_ipa_from_nsp.py` no Colab: análise real de NCA/CNMT, título e versão do update, survey e perfil provisório quando faltar perfil, extração/merge de RomFS, rewrite ARM64, split e decode de shaders que forem viáveis em Linux. `NX2Apple` usa o pin `b526a50b85e4cfa3142c111e1ad491d9fd11f0eb`.
6. Verificar relatório de conteúdo, shader split, chaves de integridade, origem das NSPs e RomFS externa.
7. Publicar **somente** `biotant/handoff.json`. O push aciona exatamente **um** workflow específico: [biomutant.yml](../.github/workflows/biomutant.yml), branch `BioiOSMutant`.
8. Após o Actions publicar uma IPA válida, usar a última célula para transferência GitHub → Colab → `biotant/ipa` com relatório de proveniência e hash.

## Divisão de trabalho e integridade

| Colab/Linux | Actions/macOS (xcode-27) |
| --- | --- |
| Download RAR, extração NSP, upload Drive e deleção RAR | Restauração do workspace verificado |
| LibHac/native `nx_extract` para Linux, scan e merge base+update | Capturas genuinamente dependentes do Apple Silicon |
| Perfil real/temporário a partir do `build_ipa_from_nsp.py` | Metal iOS e, se inevitável, shader split dependente de host |
| Rewrite AArch64, decode UE sem Oodle, split NVN possível em Linux | Framework por Title ID, Xcode, assinatura ad-hoc, IPA thin |
| RomFS externa, cache de shaders e workspace compacto enviados ao Drive | Verificação do Metal library/hash dentro da IPA |

A IPA não deve carregar `base.nsp`, `update.nsp`, `prod.keys`, `romfs.img` ou DLC. O arquivo de jogo permanece externo em `Documents/games/01004BA017CD6000/romfs.img` (ou pasta escolhida pelo shell). O finalizador embute a biblioteca Metal real, verifica o framework e apresenta seleção **30/60 FPS** — 60 FPS é experimental e não constitui desbloqueio garantido do motor.

O pipeline falha se o NSP tem Title ID errado, base/update duplicados, update sem versão válida, arquivos truncados, shader split alegadamente concluído sem chave, RomFS de outro jogo, framework sem executável ou Metal, IPA assinada sem os arquivos exigidos, ou tentativa de incluir dados do jogo.

O mesmo transporte por **6 × 64 MiB HTTP Range** (`biotant/drive_chunks.py`, com verificação SHA-256 e MD5) é aplicado aos downloads **Drive → Colab** (NSP, cache, recuperação) e **Drive → Actions** (workspace, RomFS e versões necessárias). O fallback usa chunks sequenciais de 32 MiB quando a API não fornece bytes parciais autenticados. Os testes offline de chunks e retomada ficam em `biotant/tests/test_rar_chunks.py` e `test_drive_chunks.py`.

Os patches exclusivamente Dagor/Blades of Time foram excluídos da série aplicada nesta branch, preservando o backport geral `0076` relativo à compilação de shaders Vulkan. Não há lista de shaders Dagor ou versão fixa de update na execução do Biomutant.

## Estado

Infraestrutura publicada e arquivos do fluxo preparados. **Nenhum NSP de Biomutant foi ainda analisado**, pois os arquivos estão nos links externos e a importação deve ocorrer na célula do Colab autenticado. A criação de perfil, a tradução dos shaders e a execução no iPhone só podem ser validadas depois da preparação e de um build real; não presumir compatibilidade sem esses testes.
