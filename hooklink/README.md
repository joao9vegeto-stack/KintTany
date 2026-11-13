# HookLink2iOS — recursos do port

Esta pasta contém os recursos do perfil HookLink usados pelo port nativo iOS de **The Legend of Zelda: Ocarina of Time — Nintendo Switch 2 Edition**. O fluxo de compilação, o Drive e o Actions estão descritos no [README principal](../README.md).

## Perfil de destino

- Title ID: \`0400486024DEC000\`
- Versão do pacote: \`v131072\`
- Engine: nxnative, commit \`cf2a2fecc6ce3fb841131ffeffa90915cdadf109\`
- Deployment target: **iOS 26.0**
- Toolchain: Xcode 27.2 no runner \`xcode-27\`
- GPU: \`none\` — sem PSO offline; bibliotecas Metal iOS continuam obrigatórias
- RomFS: externo à IPA (\`--romfs separate\`)

## Pipeline

A preparação Colab/Linux reproduz as etapas usadas pelo Link2iOS: extração do NUP, rewrite dos módulos AArch64, separação dos shaders NVN e criação do workspace tar.zst. O Actions restaura esse workspace, compila as bibliotecas Metal iOS e executa a finalização simplificada do HookLink/nxnative por \`dm/ios/tools/build_ipa.sh\`. Não baixa o NUP bruto nem refaz as etapas Linux. Não usa Shared Shell/Route C.

## Conteúdo

- \`Resources/tools/hl_resolution.py\`: gera o overlay de resolução a partir do RomFS e do perfil HookLink.
- \`Resources/presets/iphone.env\`: variáveis de ambiente do alvo iOS.
- \`Resources/presets/entitlements.plist\`: entitlements usados na assinatura ad-hoc.
- \`Resources/engine.json\`: metadados do snapshot de engine utilizado.
- \`scripts/push_romfs.sh\`: utilitário de envio do RomFS/overlay ao container do aplicativo em um dispositivo conectado a um Mac.
- \`LICENSE-HookLink\` e \`LICENSE-nxnative\`: licenças dos componentes upstream.

## Regra de distribuição dos dados

NUP, RomFS, IPA e recursos derivados do jogo não devem ser adicionados ao Git. O NUP fica no cache privado do Google Drive e é usado na preparação do Colab. O workspace preparado, RomFS e overlay são transferidos ao Actions para compilação; RomFS e overlay permanecem externos à IPA. No iPhone, os dados devem ficar em \`Documents/romfs.img\` e \`Documents/res_overlay/Pack/Bootup.Nin_Ounce_NVN2.pack.zs\` dentro do container de dados do app.
