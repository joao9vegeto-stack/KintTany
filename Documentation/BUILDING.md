# Compilação pelo navegador do iPhone

O usuário não precisa de Mac nem de Xcode local. Existem dois pipelines oficiais no repositório:

- `codemagic.yaml` para Codemagic;
- `.github/workflows/ios.yml` para GitHub Actions.

## Codemagic (recomendado para uso direto pelo iPhone)

1. Garanta que `codemagic.yaml` esteja na raiz do repositório.
2. No Codemagic, conecte o repositório e selecione a branch `main`.
3. Toque em **Check for configuration files**.
4. Selecione **KintTany iOS - Unsigned IPA** e inicie o build.
5. O runner executará XCTest, build `iphoneos` sem assinatura e empacotará `KintTany-unsigned.ipa`.
6. Em Artifacts, baixe o IPA pelo iPhone e siga seu fluxo de assinatura/sideload.

O pipeline está fixado em Xcode 26.5 para evitar mudanças inesperadas de toolchain.

## GitHub Actions

### Execução

1. Envie o projeto para um repositório GitHub.
2. No navegador do iPhone, abra **Actions → KintTany iOS CI**.
3. Use **Run workflow** ou faça um commit/push pelo GitHub.
4. Aguarde os passos **Run XCTest**, **Build unsigned iphoneos app** e
   **Upload build artifacts**.
5. Em **Artifacts**, baixe `KintTany-iOS-*` e extraia o `.ipa` ou `.app`.

Pull requests também executam o mesmo teste e build, permitindo validar cada
alteração antes do merge.

## O que o workflow produz

Sem assinatura configurada:

- `KintTany-unsigned.ipa`: pacote IPA com o `.app` não assinado;
- `KintTany.app`: app não assinado para o fluxo posterior de sideload.

Com assinatura configurada através dos Secrets do repositório, o mesmo run
também produz `KintTany.ipa` assinado por distribuição Ad Hoc.

## Secrets de assinatura

Configure em **Settings → Secrets and variables → Actions**:

- `IOS_DISTRIBUTION_CERTIFICATE_BASE64` — conteúdo Base64 do certificado `.p12`;
- `IOS_DISTRIBUTION_CERTIFICATE_PASSWORD` — senha do `.p12`;
- `IOS_PROVISIONING_PROFILE_BASE64` — conteúdo Base64 do `.mobileprovision`;
- `APPLE_TEAM_ID` — Team ID da Apple;
- `KEYCHAIN_PASSWORD` — opcional, apenas para o keychain temporário do runner.

O workflow importa o certificado somente no runner efêmero, instala o perfil,
gera o archive, exporta o IPA e publica o resultado como artifact. Nenhum
segredo é salvo no projeto.

## Validação local opcional

Se algum colaborador tiver Mac, poderá abrir o projeto no Xcode, mas isso não é
necessário para o fluxo do usuário nem para a validação oficial.
