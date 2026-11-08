# Aida1iOS — Thin IPA para nxnative

Esta branch é uma árvore limpa criada a partir de `main`. O aplicativo KintTany, patches e workflows herdados foram removidos. O único código de motor é o submódulo `engine/`, fixado em um commit específico de **NXNativeWindows**.

## Objetivo

Produzir dois arquivos independentes para instalação e uso no iPhone:

- **Aida1iOS.ipa** — executável iOS/ARM64 recompilado, motor nxnative, perfil do jogo, launcher, bibliotecas Metal e dependências.
- **romfs.img** — dados do jogo em imagem DMROMFS1, fora do IPA.

Depois de instalar o IPA, copiar `romfs.img` diretamente para a pasta visível do aplicativo em **Arquivos → No meu iPhone → Aida1iOS**. O motor NXNativeWindows já reconhece `Documents/romfs.img`; o arquivo não deve ser colocado em `games/<title ID>` nem extraído em centenas de milhares de arquivos.

## Empacotador Thin IPA

`tools/thin_ipa.py` recebe um IPA completo já compilado, retira somente `Payload/<app>.app/romfs.img`, grava essa imagem como arquivo externo e recria o IPA preservando os demais arquivos e os métodos de compressão.

Exemplo:

```powershell
python tools/thin_ipa.py full-game.ipa Aida1iOS.ipa romfs.img
```

A ferramenta verifica:
- existência de um único app dentro de `Payload/`;
- `Info.plist` e executável do app;
- assinatura do cabeçalho `DMROMFS1` e limites do índice;
- remoção do RomFS do IPA final e preservação do restante do pacote.

Teste local:

```powershell
python tools/thin_ipa.py --self-test
```

## Motor fixado

- Repositório: https://github.com/zenvyzenshiro/NXNativeWindows
- Commit do submódulo: `269d61ff974b2e8e073d7357466ae130c3f6812f`
- Perfis Zelda no motor:
  - BOTW: `01007EF00011E000`
  - TOTK: `0100F2C0115B6000`

O motor Windows substitui Xcode por LLVM/ld64.lld, Metal Developer Tools for Windows e o iPhoneOS SDK. BOTW e TOTK não exigem a etapa de captura de shaders no Mac, segundo a documentação desse motor.

## Workflow isolado

A branch contém somente `.github/workflows/aida1ios.yml`. Ele executa apenas ao receber `push` em `Aida1iOS` ou quando iniciado manualmente a partir dessa branch. O job também verifica a referência da branch antes de executar.

Esse workflow inicial valida o empacotador e o submódulo; **não afirma que um IPA Zelda já foi compilado**.

## Limitação que precisa ser resolvida antes do build real

Os runners Windows hospedados padrão do GitHub têm 14 GB de SSD. A imagem RomFS de BOTW/TOTK é maior que isso em alguns perfis, e a extração também precisa ler o dump original e gravar arquivos intermediários. Portanto, simplesmente baixar o dump e chamar o compilador no runner padrão não é uma solução executável confiável. O build real precisa de armazenamento de trabalho externo compatível com acesso aleatório, ou de um runner com disco suficiente. Não vou esconder essa restrição produzindo um IPA vazio ou chamando um shell de IPA jogável.

As chaves e dumps pessoais não são armazenados nesta branch. Nunca coloque `prod.keys`, NSP ou XCI no Git.
