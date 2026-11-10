# Link2iOS — Breath of the Wild

Projeto dedicado a compilar **The Legend of Zelda: Breath of the Wild no iOS** com NX2Apple Route C / Shared Shell.

## Entrada já configurada

O notebook utiliza diretamente a pasta Google Drive compartilhada com a service account:

`https://drive.google.com/drive/folders/19HXEJCK-26NfBVKeUP3wqFxMFpoF3ykm`

Na raiz dessa pasta, deixe `prod.keys`, `update.nsp`, `dlc1.nsp` e `dlc2.nsp` (os demais arquivos e pastas são ignorados; `prod.keys` continua obrigatório). O jogo base não precisa ficar no Drive antes da primeira execução.

Na primeira preparação, o notebook pede o link assinado do 7z por uma entrada protegida. O link não fica embutido no repositório público, não é impresso e não é gravado no Drive. O Colab baixa o 7z para seu armazenamento temporário, valida a assinatura, testa e extrai com 7-Zip. Para esta entrada, exige exatamente um NSP base com cabeçalho `PFS0` no início e envia somente esse NSP para `BOTW_Base_NSP/` no Drive. O extrator também mantém compatibilidade com uma entrada XCI única (`HEAD` no offset `0x100`). Arquivos auxiliares como HTML e README dentro do 7z são ignorados. O 7z temporário e a extração local são apagados.

O `prod.keys` e os três NSPs (update + duas DLCs) são baixados da raiz da pasta Drive para o runtime temporário do Colab e apagados após a preparação. O NSP base extraído permanece no Drive. Nas próximas execuções, o notebook reutiliza `BOTW_Base_NSP/` e não baixa o 7z novamente; também reconhece a pasta `BOTW_Base_XCI/` de execuções anteriores.

A entrada desta execução é BOTW base NSP v0 + update 1.9.0 + dois DLCs, Title ID `01007EF00011E000`, package `v1114112`. O NXNative/NX2Apple identifica o NSP base, o NSP de update e os dois NSPs de DLC pelos metadados internos e os combina para preparar a versão solicitada. Os dois DLCs são obrigatórios e precisam gerar imagens AOC.

## Fluxo completo

**Colab/Linux:** acessa o Drive com OAuth da conta Google autenticada no Colab, obtém `prod.keys`, baixa e extrai o 7z com o NSP base (somente na primeira execução), identifica os quatro NSPs por seus metadados internos, sincroniza NX2Apple v1.3.1-rc2 e o commit fixo do NXNative, verifica os pacotes, extrai os conteúdos, reescreve módulos AArch64 e prepara o pacote NVN de shaders. A execução para antes do estágio Metal/Xcode.

Em seguida, o Colab publica no Drive:
- `pipeline/botw-work.tar.zst`: somente os arquivos necessários à continuação do build;
- `games/01007EF00011E000/romfs.img`;
- `games/01007EF00011E000/aoc/<index>.img`, geradas a partir de `dlc1.nsp` e `dlc2.nsp`.

O workspace não contém RomFS/AOC, XCI/NSPs de origem, `prod.keys`, caches NCA grandes, ferramentas Linux ou arquivos temporários. Ele mantém os módulos reescritos, o pacote NVN de shaders e sua chave de conteúdo.

**Última célula do Colab:** pede o Fine-grained PAT e atualiza `handoff.json` na branch `Link2iOS`. Esse commit dispara o workflow.

**GitHub Actions/macOS:** baixa somente o workspace preparado e os arquivos externos RomFS/AOC; verifica SHA-256 e restaura os arquivos no mesmo layout. Não baixa NSPs nem `prod.keys` e não repete extração, rewrite ou shader split. Importa os helpers do NXNative fixado, valida a chave do pacote NVN produzida no Colab, compila as bibliotecas iOS Metal, chama `build_ipa.sh` com `DM_FRAMEWORK_ONLY`, compila o Shared Shell, assina ad-hoc e empacota a IPA.

## A IPA não contém o jogo

A IPA contém o launcher Shared Shell, o framework do BOTW, módulos reescritos, tabelas, configurações, bibliotecas Metal e componentes de runtime. A validação rejeita `romfs.img`, AOC, NSPs, `prod.keys` e arquivos PSO `.mtl4a` dentro da IPA.

RomFS e as imagens AOC dos dois DLCs permanecem no Drive externo. O Shared Shell precisa receber o RomFS externo por um provedor de arquivos que permita acesso aleatório; isso precisa ser validado no dispositivo. Se o provedor Google Drive do iOS não atender essa semântica, use uma pasta local ou iCloud Drive. O build não copia o RomFS para dentro da IPA.

## Configuração

1. Mantenha `prod.keys`, `update.nsp`, `dlc1.nsp` e `dlc2.nsp` na raiz da pasta Drive. Para o GitHub Actions, a pasta também precisa estar compartilhada com a service account configurada nos Secrets do repositório; os demais itens da raiz são ignorados.
2. No Colab, autentique sua própria conta Google na primeira célula do notebook (`auth.authenticate_user()`). Não é necessário configurar Secret de service account no Colab.
3. Em GitHub → Settings → Secrets and variables → Actions, configure `GOOGLE_SERVICE_ACCOUNT_JSON` com a credencial de leitura do Drive.
4. Gere um Fine-grained PAT restrito a este repositório com **Contents: Read and write**.
5. Abra o [notebook Link2iOS_BOTW.ipynb no Google Colab](https://colab.research.google.com/github/joao9vegeto-stack/KintTany/blob/Link2iOS/colab/Link2iOS_BOTW.ipynb), cole o link do 7z quando solicitado e execute as células em ordem.

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


## Retomada sem repetir a preparação

Após uma preparação BOTW concluída, o notebook grava `handoff.json` dentro da pasta `Link2iOS_BOTW_*` no Drive. Em uma sessão nova, execute autenticação, clone e a célula **Recuperar preparação**. Ela filtra pelo projeto, Title ID `01007EF00011E000`, versão `v1114112` e presença de workspace/RomFS/AOC. Não baixa novamente o NSP base/NSPs nem repete a extração, reescrita de módulos ou shader split. Pastas de Kleo2iOS são ignoradas.

Durante a primeira preparação, downloads exibem bytes efetivos, tamanho conferido e tempo decorrido. O Colab mantém em `/content/link2ios` o 7z original, a extração, os quatro NSPs, `prod.keys`, o checkout NX2Apple/NXNative e o workspace de build. Retentativas na mesma sessão conectada reutilizam esses dados; o código remove apenas pacotes NSP/XCI duplicados ou obsoletos da pasta de entrada. APT, módulos Python e .NET 10 também são verificados antes de instalar, evitando reinstalações quando já estão presentes.

**Limite do armazenamento local:** os 225 GB do runtime do Colab são temporários. Eles sobrevivem a novas execuções de células enquanto o mesmo runtime continuar ativo, mas não a um runtime desconectado, reciclado ou substituído. A cópia de recuperação dos pacotes continua no Google Drive; após um runtime novo, os arquivos podem ser copiados novamente do Drive, mas o 7z original não precisa ser baixado de sua URL se a pasta `BOTW_Base_NSP` já existir.


### Validação obrigatória das duas DLCs BOTW

O construtor NXNative identifica os conteúdos pelos metadados internos, não pelos nomes dos arquivos. Para BOTW, os IDs de DLC são `01007EF00011F001` e `01007EF00011F002`; o builder escreve seus RomFS como `aoc/1.img` e `aoc/2.img` (índice = title ID − base title ID − `0x1000`). O pipeline exige exatamente esses dois arquivos não vazios antes de enviar o handoff ao Actions. Uma preparação com apenas uma DLC não é aceita.
