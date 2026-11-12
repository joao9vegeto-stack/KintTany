# HookLink2iOS — recursos do port

Esta pasta contém os recursos do perfil HookLink usados pelo port nativo iOS de **The Legend of Zelda: Ocarina of Time — Nintendo Switch 2 Edition**. O fluxo de build, os requisitos de autenticação e as instruções operacionais estão documentados no [README principal](../README.md).

## Perfil de destino

- Title ID: `0400486024DEC000`
- Versão do pacote: `v131072`
- Engine: nxnative, commit `cf2a2fecc6ce3fb841131ffeffa90915cdadf109`
- Perfil GPU inicial: `g18p` (família A19 / iPhone 17 Pro)
- Build: iOS nativo, `--romfs separate`

## Conteúdo

- `Resources/tools/hl_resolution.py`: gera o overlay de resolução a partir do RomFS e do perfil HookLink.
- `Resources/presets/iphone.env`: variáveis de ambiente do alvo iOS.
- `Resources/presets/entitlements.plist`: entitlements usados na assinatura ad-hoc.
- `Resources/engine.json`: metadados do snapshot de engine utilizado.
- `scripts/push_romfs.sh`: utilitário de envio do RomFS/overlay ao container do aplicativo em um dispositivo conectado a um Mac.
- `LICENSE-HookLink` e `LICENSE-nxnative`: licenças dos componentes upstream.

## Regra de distribuição dos dados

NUP, RomFS, IPA e recursos derivados do jogo não devem ser adicionados ao Git. O NUP é entrada de build e fica no cache privado do Google Drive; RomFS e overlay são externos à IPA. No iPhone, os dados devem ficar em `Documents/romfs.img` e `Documents/res_overlay/Pack/Bootup.Nin_Ounce_NVN2.pack.zs` dentro do container de dados do app.
