# HookLink2iOS — The Legend of Zelda: Ocarina of Time

Port nativo para iOS de **The Legend of Zelda: Ocarina of Time — Nintendo Switch 2 Edition**, usando HookLink sobre nxnative. Esta branch é isolada: todo handoff e build deste projeto pertencem a `HookLink2iOS`.

## Alvo fixo

| Propriedade | Valor |
|---|---|
| Projeto | `HookLink2iOS` |
| Jogo | Ocarina of Time — Nintendo Switch 2 Edition |
| Title ID | `0400486024DEC000` |
| Update | `v131072` |
| Engine | [dsi-hub/nxnative — HookLink pin](https://github.com/dsi-hub/nxnative/tree/cf2a2fecc6ce3fb841131ffeffa90915cdadf109) |
| Engine commit | `cf2a2fecc6ce3fb841131ffeffa90915cdadf109` |
| Perfil inicial | `g18p` — família A19 / iPhone 17 Pro |
| Runner | `macos-26` |
| Xcode | `27.2` |
| RomFS | Externo à IPA (`--romfs separate`) |

O pipeline não é um conversor genérico: valida o Title ID e a versão antes de publicar o handoff.

## Fluxo de build — mesmo modelo operacional da Link2iOS

O pipeline tem duas etapas, como o fluxo BOTW da branch `Link2iOS`: preparação Linux no Colab e build iOS no GitHub Actions/macOS. O Colab não tenta executar Xcode/Metal; o Actions não baixa o pacote de origem nem repete o trabalho Linux.

### 1. Colab: origem, cache, RomFS e handoff

Abra o [notebook HookLink2iOS no Google Colab](https://colab.research.google.com/github/joao9vegeto-stack/KintTany/blob/HookLink2iOS/colab/HookLink2iOS_Colab.ipynb) e execute as células em ordem.

- O notebook autentica o Google Drive pela conta Google do Colab, reutilizando a pasta raiz já configurada no notebook Link2iOS: [pasta compartilhada](https://drive.google.com/drive/folders/19HXEJCK-26NfBVKeUP3wqFxMFpoF3ykm).
- Cole diretamente uma URL HTTPS de um `.nup` ou de um arquivo compactado que contenha **exatamente um** NUP. São reconhecidos RAR, ZIP, 7z e formatos tar compactados. Não há escolha de modo `drive/url`.
- A identidade do endereço é calculada sem os parâmetros temporários de assinatura. Ao reutilizar o mesmo arquivo com uma URL assinada renovada, o notebook procura primeiro o NUP já guardado no Drive e evita novo download.
- Na primeira execução, o Colab baixa a origem, valida e extrai o NUP quando necessário, e envia o NUP para `HookLink2iOS/Inputs`. O arquivo compactado local só é excluído depois que o upload do NUP foi verificado por tamanho e MD5.
- O nxnative é clonado no commit fixo. `scripts/pack_nup.py` confirma o Title ID/versão e gera `extract/v131072/RomFS.img`; em seguida, o script do perfil HookLink gera o overlay de resolução.
- O NUP persistente, o RomFS e o overlay são enviados ao Drive com tamanho e hashes SHA-256/MD5. O Colab publica então apenas `hooklink2ios/handoff.json` na branch `HookLink2iOS`.

Layout no Google Drive:

```text
<pasta raiz já configurada>
└── HookLink2iOS/
    ├── Inputs/
    │   └── <NUP validado e reutilizável>
    └── HookLink2iOS-<request_id>/
        ├── romfs.img
        └── Bootup.Nin_Ounce_NVN2.pack.zs
```

### 2. GitHub Actions: build nativo iOS

O commit do handoff aciona `.github/workflows/hooklink2ios.yml`. O workflow:

1. aceita somente `push` na branch `HookLink2iOS` que altere `hooklink2ios/handoff.json` e confirma o SHA do checkout;
2. valida projeto, Title ID, versão, pin do engine e os hashes dos três arquivos do handoff;
3. usa `macos-26`, Python 3.12 e Xcode 27.2;
4. busca exatamente o commit fixado do nxnative;
5. baixa NUP, RomFS e overlay do Google Drive e verifica tamanho, SHA-256 e MD5;
6. executa o builder iOS com `--romfs separate`;
7. publica IPA, overlay e `build-report.json` no artifact `HookLink2iOS-Ocarina-<run_number>`.

**A autenticação do Actions segue o padrão funcional de Link2iOS:** o runner usa o secret permanente `GOOGLE_SERVICE_ACCOUNT_JSON` do repositório para acessar o Drive. A conta de serviço precisa ter permissão sobre a pasta raiz indicada acima. O OAuth autenticado no Colab permanece no Colab: não é copiado para GitHub, não é gravado como secret temporário e não exige permissão `Secrets` no PAT.

### 3. Retorno da IPA ao Drive

Depois do build, o notebook identifica a execução pelo **commit exato** do handoff, baixa apenas o artifact HookLink2iOS correspondente, confere o digest do ZIP e valida a IPA contra o `build-report.json`. Em seguida, envia a IPA, o overlay e o relatório à pasta daquela execução no Drive. O upload final é feito pelo OAuth do Colab e validado por tamanho/MD5.

O notebook solicita um Fine-grained PAT restrito a este repositório com:
- `Contents: Read and write` — publicar o handoff;
- `Actions: Read` — localizar o workflow e baixar o artifact.

Não precisa conceder `Secrets` ao PAT.

## Preparação do repositório

O repositório precisa manter o secret de Actions `GOOGLE_SERVICE_ACCOUNT_JSON` já usado pelo pipeline Link2iOS. O JSON é a credencial da conta de serviço; compartilhe a pasta raiz do Drive com o e-mail dessa conta, concedendo leitura e escrita. O notebook não pede nem grava esse JSON.

Nenhum NUP, RomFS, overlay, IPA, chave ou dado derivado do jogo é versionado no Git.

## RomFS no iPhone

A IPA não inclui o RomFS. Depois de instalar o app, coloque os arquivos externos no container de dados do aplicativo:

```text
AppDataContainer/
└── Documents/
    ├── romfs.img
    └── res_overlay/
        └── Pack/
            └── Bootup.Nin_Ounce_NVN2.pack.zs
```

O script upstream incluído em `hooklink/scripts/push_romfs.sh` automatiza a transferência para um dispositivo conectado a um Mac, usando AFC/afcclient ou devicectl e verificando o arquivo antes da publicação. Não coloque `romfs.img` dentro da IPA.

## Isolamento e segurança

- Trabalhar somente na branch `HookLink2iOS`; `main` e `Link2iOS` não fazem parte deste fluxo.
- O workflow tem gatilho único: `push` em `HookLink2iOS` com alteração em `hooklink2ios/handoff.json`.
- O job confirma `GITHUB_REF`, branch, commit do checkout e identidade do handoff antes de compilar.
- Uma execução nova na mesma branch cancela a execução anterior ainda ativa.
- Não existem gatilhos `workflow_dispatch`, `workflow_run`, schedule ou tag neste workflow.
- URLs assinadas são mantidas apenas no runtime Colab e não são publicadas no handoff.
- Arquivos de entrada são tratados como dados não confiáveis: o arquivo compactado é inspecionado antes da extração e deve conter exatamente um NUP.

## Retomada

Se o Colab desconectar depois que NUP/RomFS/overlay forem enviados, abra novamente o notebook, autentique o Drive, cole a mesma URL (ou uma URL assinada renovada para o mesmo caminho) e execute as células. O notebook procura primeiro o handoff e os arquivos persistidos no Drive e não repete o download/preparação quando encontra uma combinação íntegra. Se o Actions já concluiu, recupera a execução ligada àquele commit e transfere o artifact correspondente.

## Upstream e licenças

- HookLink snapshot: `dsi-hub/HookLink`, commit `b329fa5443ad4bfea016dfd366042a305f221071`.
- nxnative: `dsi-hub/nxnative`, commit `cf2a2fecc6ce3fb841131ffeffa90915cdadf109`.
- Os avisos/licenças dos componentes upstream estão incluídos em `hooklink/`.
