# Link2iOS — Breath of the Wild

Projeto independente para compilar **The Legend of Zelda: Breath of the Wild no iOS** usando NX2Apple Route C / Shared Shell.

A branch `Link2iOS` foi criada diretamente de `main`. Os arquivos não relacionados ao port foram removidos somente desta branch. `main` e `Kleo2iOS` não são alteradas.

## Pasta de entrada no Google Drive

Compartilhe a pasta com a service account como **Editor**. Estrutura:

```
BOTW/
├── base/
│   └── base-game.nsp
├── update/
│   └── update-1.9.0.nsp
├── dlc/
│   ├── dlc-1.nsp
│   └── dlc-2.nsp
└── prod.keys
```

Os nomes podem variar. O NXNative identifica base, update e DLC pelo conteúdo dos NSPs, não pelos nomes. O perfil aceito é BOTW `01007EF00011E000`, versão **1.9.0 / v1114112**, SDK 20.5.22. A entrada deve incluir os NSPs de DLC que deseja utilizar. `prod.keys` é necessário para descriptografar os NSPs e nunca será enviado ao GitHub.

## Fluxo completo

**Colab/Linux:** acessa o Drive com service account, baixa NSPs e keys, sincroniza NX2Apple v1.3.1-rc2 e o commit fixo do NXNative, verifica os pacotes, extrai os conteúdos, reescreve módulos AArch64 e prepara o pacote NVN de shaders. A execução para antes do estágio Metal/Xcode.

Em seguida, o Colab publica no Drive:
- `pipeline/botw-work.tar.zst`: somente arquivos necessários à continuação do build;
- `games/01007EF00011E000/romfs.img`;
- `games/01007EF00011E000/aoc/<index>.img`: cada DLC separadamente.

O workspace não contém o RomFS/AOC, NSPs, `prod.keys`, caches NCA grandes, ferramentas Linux ou arquivos temporários. Ele mantém os módulos reescritos, o pacote NVN de shaders e sua chave de conteúdo. O upload separado evita duplicar o conteúdo do jogo dentro do arquivo de build.

**Última célula do Colab:** pede o Fine-grained PAT e atualiza `handoff.json` na branch `Link2iOS`. Esse commit dispara o workflow.

**GitHub Actions/macOS:** baixa do Drive somente o workspace preparado e os arquivos externos `romfs.img`/AOC; verifica SHA-256 e restaura esses arquivos no mesmo layout. Não baixa NSPs nem `prod.keys` e não repete extração, rewrite ou shader split. Importa os helpers do NXNative fixado, valida a chave do pacote NVN produzida no Colab, compila apenas as bibliotecas iOS Metal e chama `build_ipa.sh` com `DM_FRAMEWORK_ONLY`. Depois `build_shell.sh` embute `DmGame01007EF00011E000.framework` no Shared Shell; o workflow assina ad-hoc e empacota a IPA.

## A IPA não contém o jogo

A IPA contém o launcher Shared Shell, o framework do BOTW, módulos reescritos, tabelas, configurações, bibliotecas Metal e componentes de runtime. Ela é verificada para garantir que **não contenha `romfs.img`, diretório AOC, NSPs, `prod.keys` nem arquivos PSO `.mtl4a`**.

O RomFS e DLC permanecem em uma pasta independente no Drive. O Shared Shell já oferece o seletor de dados externos e bookmark por jogo. O arquivo precisa estar disponível com acesso aleatório para leitura. A integração do provedor Google Drive no seletor do iOS precisa ser validada no dispositivo; se o provedor não oferecer a semântica de arquivo necessária, use uma pasta local ou iCloud Drive. O build não copia o RomFS para dentro da IPA.

## Configuração

1. Compartilhe a pasta de entrada com a service account como Editor.
2. No Colab, crie o Secret `LINK2IOS_GOOGLE_SERVICE_ACCOUNT_JSON`.
3. Em GitHub → Settings → Secrets and variables → Actions, crie `GOOGLE_SERVICE_ACCOUNT_JSON` com o mesmo JSON.
4. Gere um Fine-grained PAT restrito a este repositório com **Contents: Read and write**.
5. Abra o [notebook Link2iOS_BOTW.ipynb no Google Colab](https://colab.research.google.com/github/joao9vegeto-stack/KintTany/blob/Link2iOS/colab/Link2iOS_BOTW.ipynb), informe o ID da pasta e execute as células em ordem.

## Isolamento

Existe apenas `.github/workflows/link2ios.yml`. Ele é acionado somente por `push` em `refs/heads/Link2iOS` que altere `handoff.json`. O job repete a validação da ref. Não há gatilho em `main`, `Kleo2iOS`, `workflow_dispatch` ou workflow auxiliar nesta branch. Uma execução nova cancela outra execução Link2iOS ainda ativa.

## Perfil e pontos de atenção

- O perfil BOTW usa reserva de memória de 4 GiB, alias de 256 MiB, stack de 256 MiB e app pool de aproximadamente 3,2 GiB.
- O upstream registra BOTW jogável em iPhone, com 60 FPS no perfil 1.9.0. Os testes descritos incluem iPhone 17 Pro Max e iOS 27.0.1; isso não garante o resultado no iPhone 17 Pro com iOS 26.5.1.
- Para evitar PSO `.mtl4a` do SDK mais novo no alvo iOS 26, o estágio macOS passa `DM_PSO_GPUS=none` ao `build_ipa.sh` e mantém as bibliotecas de shader necessárias. O dispositivo prepara os pipeline bases no primeiro uso; o primeiro carregamento pode demorar mais.
- IPA construída com sucesso não significa gameplay validado. O teste no aparelho continua necessário.

## Pins

- NX2Apple: https://github.com/LNPANDY/NX2Apple/tree/v1.3.1-rc2
- NXNative: https://github.com/seedds/nxnative/tree/81906931262fb25d774cce8bca2db8926439e5a2
- Perfil BOTW: https://github.com/seedds/nxnative/tree/81906931262fb25d774cce8bca2db8926439e5a2/dm/games/01007EF00011E000
