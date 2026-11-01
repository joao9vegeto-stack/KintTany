# PandaiOS

Port nativo iOS do cliente Panda Cloud Gaming. O desenvolvimento fica isolado nesta pasta e na branch \`PandaiOS\`.

## Estado inicial

- Aplicativo SwiftUI nativo e projeto XcodeGen.
- Player de diagnóstico HLS usando AVPlayer. Isso testa somente streams HLS; não é ainda o transporte confirmado do Panda.
- Workflow manual para build iOS e, opcionalmente, análise estática do APK com REA.
- Nenhuma URL, API, credencial, endpoint ou protocolo de sessão foi presumido.

## Evidências iniciais do APK recebido

- SHA-256 do APK original recebido: `72d3f472a778e400473095407b24244b780e9871b1541345099f9422b937716b`.
- Package ID observado em strings DEX: \`com.qudian.qudianyun\`.
- DEX primário: \`classes.dex\` (~1,0 MB); o payload também contém \`assets/classes0.jar\` (~7,4 MB) e \`assets/1728530695\` (~6,4 MB), que precisam ser caracterizados.
- Bibliotecas ARM64: \`libijkplayerplugin.so\`, \`libmmkv.so\`, \`libsgcore.so\`, \`libzeus_direct_dex.so\`, \`libSecShell.so\`, entre outras.
- O payload secundário contém referência a \`libttmplayer_lite.so\` e \`assets/mapnaveinfoox111.dex\`.
- Indicadores \`DexFile\`, \`PathClassLoader\` e \`dexElements\` sugerem carregamento dinâmico; SecShell torna insuficiente analisar apenas o DEX principal.
- Ainda não foi estabelecido se o jogo usa HLS, RTSP, WebRTC ou protocolo proprietário. IJKPlayer, isoladamente, não prova o protocolo.

## Próximos passos

1. Rodar REA/JADX no APK original e registrar Evidence, manifesto, componentes, classes e referências.
2. Investigar o carregador SecShell e o payload secundário sem executar o APK.
3. Localizar login, seleção de região/servidor, criação de sessão, negociação de transporte e input remoto.
4. Identificar codec, transporte, áudio, latência, controles e keepalive.
5. Implementar o transporte real em Swift/Network.framework e a decodificação adequada.
6. Testar com uma sessão legítima do serviço; só então considerar o port funcional.

## Build

O workflow gera um IPA não assinado para assinatura posterior. O IPA não assinado não instala diretamente em um iPhone.
