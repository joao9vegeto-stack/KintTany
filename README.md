# KintTany iOS

Projeto iOS nativo Swift/SwiftUI baseado na baseline baseline legada v5.2.

## Fluxo oficial sem Mac

O repositório contém dois pipelines de compilação remota:

- `codemagic.yaml` — fluxo mais simples para compilar e baixar pelo iPhone usando Codemagic;
- `.github/workflows/ios.yml` — pipeline equivalente no GitHub Actions.

Nenhum dos dois exige Mac ou Xcode local.
Cada push ou pull request executa, em um runner macOS do GitHub:

1. seleção da toolchain Xcode disponível;
2. XCTest no simulador iOS;
3. build `iphoneos` sem assinatura;
4. geração de `KintTany-unsigned.ipa` e `KintTany.app`;
5. upload dos arquivos na aba **Actions → Artifacts**.

Assim, o projeto pode ser compilado e baixado inteiramente pelo navegador do
iPhone. Nenhuma etapa fundamental exige abrir o projeto no Xcode localmente.

## IPA assinado

Sem Secrets de assinatura, o workflow sempre gera o artefato não assinado para
o fluxo posterior de sideload. Para gerar também `KintTany.ipa` assinado,
configure no GitHub Actions os Secrets:

- `IOS_DISTRIBUTION_CERTIFICATE_BASE64`: certificado `.p12` em Base64;
- `IOS_DISTRIBUTION_CERTIFICATE_PASSWORD`;
- `IOS_PROVISIONING_PROFILE_BASE64`: perfil `.mobileprovision` em Base64;
- `APPLE_TEAM_ID`;
- `KEYCHAIN_PASSWORD` (opcional; há valor temporário para o runner).

O certificado, o perfil e as credenciais nunca são incluídos no repositório ou
nos artefatos não assinados.

Não inclua cookies, chaves privadas, carteiras ou arquivos `.env` no projeto.


## Codemagic

1. Suba o conteúdo desta pasta para a raiz do repositório GitHub.
2. Conecte esse repositório ao Codemagic.
3. Selecione a branch `main` e toque em **Check for configuration files**.
4. O workflow **KintTany iOS - Unsigned IPA** será encontrado a partir de `codemagic.yaml`.
5. Inicie o build. O runner Mac executará XCTest, compilará para `iphoneos` e publicará `KintTany-unsigned.ipa`.
6. Baixe o artifact diretamente pelo navegador do iPhone e assine-o pelo seu fluxo de sideload.

O workflow do Codemagic usa Xcode 26.5 em Mac mini M2 e não requer certificado Apple para o artifact sem assinatura.
