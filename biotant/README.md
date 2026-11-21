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

## Recuperação após SIGKILL do rewrite do main

A preparação real do Biomutant identificou o update **v131072**, extraiu 166 arquivos (5,7 GB) e recuperou três módulos **subsdk0**, **sdk** e **nro0** a partir da pasta `patched_v131072.partial`. Duas tentativas de `patch_nso.py` no `main` foram mortas com `SIGKILL (-9)`, sem traceback e sem registro de `oom_kill` no cgroup consultado. **Não repetir o rewrite do main no Colab às cegas.**

Há uma rota opcional **Linux → Linux** para somente esse módulo: [`biomutant-main-linux.yml`](../.github/workflows/biomutant-main-linux.yml), separada do workflow da IPA.

1. **No mesmo Colab, mantenha `/content/biomutant` intacto** e execute novamente apenas a célula 2 para atualizar `/content/BioiOSMutant-repo`. NÃO execute a célula 5: ela tentaria outro rewrite do `main`.
2. Em uma **nova célula Colab**, crie o pacote privado e publique o pedido de rewrite. O script guarda no seu Drive o `main` do ExeFS, perfil e cópias dos três módulos recuperados; publica no GitHub somente os IDs do Drive e hashes, sem NSP, prod.keys ou código do jogo:

```python
import importlib
import offload_main
offload_main = importlib.reload(offload_main)
MAIN_REQUEST = offload_main.prepare(DRIVE_CLIENT)
```

3. Acompanhe a execução em [Actions / Biomutant main-only Linux](https://github.com/joao9vegeto-stack/KintTany/actions/workflows/biomutant-main-linux.yml). Um runner `ubuntu-latest` (não `xcode-27`) verifica o mesmo `patch_nso.py`, roda só o `main`, registra rastros Python a cada três minutos e atualiza **o arquivo de resultado vazio que o Colab já criou na pasta do usuário**. Essa última condição é importante: contas de serviço não podem criar novos arquivos no Meu Drive pessoal.
4. **Só depois de o Linux Actions concluir com sucesso**, no Colab execute:

```python
import importlib
import offload_main
offload_main = importlib.reload(offload_main)
MAIN_REPORT = offload_main.receive(DRIVE_CLIENT)
import run_colab
run_colab = importlib.reload(run_colab)
HANDOFF = run_colab.prepare(
    argparse.Namespace(drive_folder_id=DRIVE_PARENT_ID),
    api=DRIVE_CLIENT,
)
```

A importação verifica SHA-256 de cada saída e os fingerprints originais. Caso a sessão Colab anterior tenha sido encerrada, `receive` pode restaurar do pacote privado os três módulos recuperados, o perfil e o `main`, antes de prosseguir; as NSPs/ROMFS podem precisar ser baixadas ou extraídas novamente. **Não se garante o sucesso do rewrite no Linux Actions até executar o trabalho real.**

## Estado

**Observado nos logs de 21/11/2026:** base + update v131072 analisados, 166 arquivos extraídos (5,7 GB), `subsdk0`/`sdk`/`nro0` recuperados; rewrite do `main` encerrado duas vezes com sinal 9, apesar do segundo ser serializado. Rota alternativa Linux main-only preparada e testes offline aprovados; **a execução com os bytes reais do `main` ainda não ocorreu, não há workspace finalizado nem IPA gerada**. O port e sua compatibilidade em iOS não são afirmados como concluídos.
