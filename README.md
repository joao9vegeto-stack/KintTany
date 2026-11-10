# Link2iOS — Breath of the Wild

Projeto dedicado a compilar **The Legend of Zelda: Breath of the Wild no iOS** com NX2Apple Route C / Shared Shell.

## Entrada já configurada

O notebook utiliza diretamente a pasta Google Drive compartilhada com a service account:

`https://drive.google.com/drive/folders/19HXEJCK-26NfBVKeUP3wqFxMFpoF3ykm`

Deixe `prod.keys` na raiz dessa pasta. Não crie pastas `base/`, `update/` ou `dlc/`.

Na primeira execução, o notebook pede o link assinado do RAR por uma entrada protegida. O link não fica embutido no repositório público, não é impresso e não é gravado no Drive. O Colab baixa o RAR para seu armazenamento temporário, valida e extrai com 7-Zip, procura os NSPs recursivamente e envia apenas os NSPs extraídos para uma pasta `BOTW_Extracted/` criada automaticamente no Drive. O RAR temporário é apagado.

O `prod.keys` é baixado da raiz da pasta Drive para o runtime temporário do Colab e apagado após a preparação. Os NSPs extraídos permanecem no Drive. Nas próximas execuções, o notebook reutiliza `BOTW_Extracted/` e não baixa o RAR novamente; o campo do link pode ficar vazio.

A entrada desta execução é o BOTW base + update 1.9.0, Title ID `01007EF00011E000`, package `v1114112`. **DLC é opcional**: sem DLC, o build segue sem imagens AOC e sem conteúdo de expansão.

## Fluxo completo

**Colab/Linux:** acessa o Drive com service account, obtém `prod.keys`, baixa e extrai o RAR (somente na primeira execução), identifica os NSPs de base/update, sincroniza NX2Apple v1.3.1-rc2 e o commit fixo do NXNative, verifica os pacotes, extrai os conteúdos, reescreve módulos AArch64 e prepara o pacote NVN de shaders. A execução para antes do estágio Metal/Xcode.

Em seguida, o Colab publica no Drive:
- `pipeline/botw-work.tar.zst`: somente os arquivos necessários à continuação do build;
- `games/01007EF00011E000/romfs.img`;
- `games/01007EF00011E000/aoc/<index>.img`, somente quando DLC tiver sido fornecido.

O workspace não contém RomFS/AOC, NSPs, `prod.keys`, caches NCA grandes, ferramentas Linux ou arquivos temporários. Ele mantém os módulos reescritos, o pacote NVN de shaders e sua chave de conteúdo.

**Última célula do Colab:** pede o Fine-grained PAT e atualiza `handoff.json` na branch `Link2iOS`. Esse commit dispara o workflow.

**GitHub Actions/macOS:** baixa somente o workspace preparado e os arquivos externos RomFS/AOC; verifica SHA-256 e restaura os arquivos no mesmo layout. Não baixa NSPs nem `prod.keys` e não repete extração, rewrite ou shader split. Importa os helpers do NXNative fixado, valida a chave do pacote NVN produzida no Colab, compila as bibliotecas iOS Metal, chama `build_ipa.sh` com `DM_FRAMEWORK_ONLY`, compila o Shared Shell, assina ad-hoc e empacota a IPA.

## A IPA não contém o jogo

A IPA contém o launcher Shared Shell, o framework do BOTW, módulos reescritos, tabelas, configurações, bibliotecas Metal e componentes de runtime. A validação rejeita `romfs.img`, AOC, NSPs, `prod.keys` e arquivos PSO `.mtl4a` dentro da IPA.

RomFS e DLC (quando existentes) permanecem no Drive externo. O Shared Shell precisa receber o RomFS externo por um provedor de arquivos que permita acesso aleatório; isso precisa ser validado no dispositivo. Se o provedor Google Drive do iOS não atender essa semântica, use uma pasta local ou iCloud Drive. O build não copia o RomFS para dentro da IPA.

## Configuração

1. Mantenha `prod.keys` na raiz da pasta Drive já compartilhada com a service account.
2. No Colab, configure o Secret `LINK2IOS_GOOGLE_SERVICE_ACCOUNT_JSON`.
3. Em GitHub → Settings → Secrets and variables → Actions, configure `GOOGLE_SERVICE_ACCOUNT_JSON` com a credencial de leitura do Drive.
4. Gere um Fine-grained PAT restrito a este repositório com **Contents: Read and write**.
5. Abra o [notebook Link2iOS_BOTW.ipynb no Google Colab](https://colab.research.google.com/github/joao9vegeto-stack/KintTany/blob/Link2iOS/colab/Link2iOS_BOTW.ipynb), cole o link do RAR quando solicitado e execute as células em ordem.

## Isolamento

Existe apenas `.github/workflows/link2ios.yml`. Ele é acionado somente por `push` em `refs/heads/Link2iOS` que altere `handoff.json`. Não há gatilho em `main`, `Kleo2iOS`, `workflow_dispatch` ou workflow auxiliar nesta branch. Uma execução nova cancela outra execução Link2iOS ainda ativa.

## Perfil e pontos de atenção

- O perfil BOTW usa reserva de memória de 4 GiB, alias de 256 MiB, stack de 256 MiB e app pool de aproximadamente 3,2 GiB.
- O upstream registra BOTW jogável em iPhone no perfil 1.9.0. Isso não garante o resultado no iPhone 17 Pro com iOS 26.5.1.
- Para evitar PSO `.mtl4a` do SDK mais novo no alvo iOS 26, o estágio macOS usa `DM_PSO_GPUS=none`, mantendo as bibliotecas de shader. O dispositivo prepara os pipeline bases no primeiro uso.
- IPA construída com sucesso não significa gameplay validado. O teste no aparelho continua necessário.

## Pins

- NX2Apple: https://github.com/LNPANDY/NX2Apple/tree/v1.3.1-rc2
- NXNative: https://github.com/seedds/nxnative/tree/81906931262fb25d774cce8bca2db8926439e5a2
- Perfil BOTW: https://github.com/seedds/nxnative/tree/81906931262fb25d774cce8bca2db8926439e5a2/dm/games/01007EF00011E000
