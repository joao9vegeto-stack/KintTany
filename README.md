# HookLink2iOS — The Legend of Zelda: Ocarina of Time

Port nativo para iOS de **The Legend of Zelda: Ocarina of Time — Nintendo Switch 2 Edition**, usando a estrutura nxnative do HookLink. Todo o trabalho desta implementação fica isolado na branch \`HookLink2iOS\`.

## Alvo fixo

| Propriedade | Valor |
|---|---|
| Projeto | \`HookLink2iOS\` |
| Jogo | Ocarina of Time — Nintendo Switch 2 Edition |
| Title ID | \`0400486024DEC000\` |
| Update | \`v131072\` |
| Engine | [dsi-hub/nxnative — HookLink pin](https://github.com/dsi-hub/nxnative/tree/cf2a2fecc6ce3fb841131ffeffa90915cdadf109) |
| Engine commit | \`cf2a2fecc6ce3fb841131ffeffa90915cdadf109\` |
| Deployment target | **iOS 26.0** |
| Build toolchain | runner \`xcode-27\`, Xcode 27.2 |
| GPU / PSO offline | \`none\` — igual ao Link2iOS |
| RomFS | Externo à IPA (\`--romfs separate\`) |

Xcode 27.2 é a ferramenta de compilação. O aplicativo continua com requisito mínimo iOS 26.0, confirmado no projeto XcodeGen e auditado no \`MinimumOSVersion\` do Info.plist da IPA.

## Pipeline: mesma divisão de etapas do Link2iOS

A única diferença de jogo não deve criar um fluxo de build diferente. O HookLink usa o mesmo nxnative e a mesma divisão de trabalho em Colab/Linux e Actions/macOS. A finalização permanece no builder simplificado do próprio HookLink/nxnative (\`dm/ios/tools/build_ipa.sh\`); não usa Shared Shell nem NX2Apple Route C.

### 1. Colab — preparação Linux

Abra o [notebook HookLink2iOS no Google Colab](https://colab.research.google.com/github/joao9vegeto-stack/KintTany/blob/HookLink2iOS/colab/HookLink2iOS_Colab.ipynb) e execute as células em ordem.

O Colab autentica no Drive pela conta Google já configurada e reutiliza a pasta raiz do fluxo Link2iOS: [pasta compartilhada](https://drive.google.com/drive/folders/19HXEJCK-26NfBVKeUP3wqFxMFpoF3ykm).

O helper reutiliza primeiro \`/content/hooklink2ios-work/input/game.nup\`, se ainda existir. Caso contrário, localiza o NUP validado em \`HookLink2iOS/Inputs\` no Drive; a URL externa só é baixada se não houver cache. O NUP continua sendo usado no Colab, nunca pelo Actions.

Com o commit nxnative fixado, o Colab executa os estágios Linux do builder:
1. identificação do NUP, Title ID e update;
2. extração do jogo, ExeFS, RomFS e DLC/AOC;
3. rewrite dos módulos ARM64 e geração das tabelas/fixups;
4. separação dos shaders NVN e validação do pacote de shaders.

A execução é interrompida intencionalmente na fronteira da etapa Apple. A compilação Metal para iPhone e o empacotamento Xcode ficam para o macOS.

O Colab gera o overlay de resolução HookLink, persiste o RomFS e o overlay separadamente e compacta o workspace preparado em \`tar.zst\`. O archive inclui os arquivos extraídos necessários, módulos reescritos, shader package e tabelas; exclui o NUP original, o RomFS externo, ferramentas e temporários. O handoff schema 3 grava os hashes e a identidade de cada artefato.

### 2. GitHub Actions — Metal e IPA nativa

O push do handoff na branch \`HookLink2iOS\` inicia o workflow. O Actions:

1. valida o handoff schema 3, o pin nxnative, o profile Ocarina, o shader chain, GPU none e o alvo iOS 26.0;
2. restaura o workspace preparado pelo Colab e baixa separadamente apenas o RomFS e o overlay;
3. verifica hashes, identidade do RomFS, módulos reescritos, chave do pacote de shaders e compatibilidade da chain;
4. compila as bibliotecas iOS Metal com o nxnative \`dmsh_build.py\`, reutilizando o shader split do Colab;
5. executa o finalizador nativo simplificado \`dm/ios/tools/build_ipa.sh\`, com \`DM_PSO_GPUS=none\` e \`DM_COPY_ROMFS=NO\`;
6. audita o Info.plist da IPA: \`MinimumOSVersion=26.0\`, biblioteca Metal presente, RomFS externo e nenhum arquivo PSO offline \`.mtl4a\`;
7. publica IPA, overlay e \`build-report.json\` no artifact \`HookLink2iOS-Ocarina-<run_number>\`.

**O Actions não baixa o NUP, não refaz a extração, não reescreve módulos e não repete o shader split.** Não há a etapa de descarregar 25,6 GB do NUP no runner. O arquivo de entrada permanece no cache privado do Drive.

**GPU none não significa remover os shaders.** As bibliotecas Metal iOS continuam sendo compiladas e incorporadas à IPA; somente o archive PSO offline fica ausente, como no Link2iOS.

### 3. Retorno da IPA ao Drive

Depois do Actions, o notebook acompanha somente o run ligado ao commit exato do handoff. Verifica o digest do ZIP do GitHub, a proveniência do workspace, o shader split, o hash da IPA, o alvo mínimo iOS 26.0 e o relatório. Só então envia IPA, overlay e relatório para a subpasta exclusiva daquela execução.

O PAT do notebook precisa apenas de:
- \`Contents: Read and write\` para publicar o handoff;
- \`Actions: Read\` para acompanhar o workflow e baixar o artifact.

O secret permanente \`GOOGLE_SERVICE_ACCOUNT_JSON\` já utilizado pelo pipeline Link2iOS é reutilizado pelo Actions; não é necessário recriá-lo.

## Layout no Drive

\`\`\`text
<pasta raiz existente>
└── HookLink2iOS/
    ├── Inputs/
    │   └── <NUP validado e reutilizável>
    └── HookLink2iOS-<request_id>/
        ├── hooklink2ios-work.tar.zst
        ├── romfs.img
        ├── Bootup.Nin_Ounce_NVN2.pack.zs
        └── actions-<run_number>-<run_id>/
            ├── OcarinaOfTime-HookLink2iOS.ipa
            ├── Bootup.Nin_Ounce_NVN2.pack.zs
            └── build-report.json
\`\`\`

## RomFS no iPhone

A IPA esperada é aproximadamente 5 GB, conforme o layout HookLink, mas o tamanho final só será confirmado após o build e a auditoria. O RomFS (aproximadamente 24,5 GiB) permanece separado da IPA.

No container de dados do app, os recursos externos devem ficar em:

\`\`\`text
Documents/
├── romfs.img
└── res_overlay/
    └── Pack/
        └── Bootup.Nin_Ounce_NVN2.pack.zs
\`\`\`

O utilitário \`hooklink/scripts/push_romfs.sh\` auxilia a transferência para um dispositivo conectado a um Mac e verifica o arquivo antes de publicá-lo.

## Retomada e isolamento

- Trabalhar somente na branch \`HookLink2iOS\`; \`main\` e \`Link2iOS\` são referências protegidas e somente leitura.
- O workflow só inicia com push em \`HookLink2iOS\` alterando \`hooklink2ios/handoff.json\`.
- A concorrência cancela uma execução antiga da mesma branch quando um novo handoff válido inicia outro run.
- Handoff schema 2 é legado: não contém workspace preparado e nunca pode ser tratado como um build pronto. O notebook precisa preparar o workspace schema 3 antes de iniciar o novo fluxo.
- NUP, RomFS, IPA, keys e dados derivados do jogo não são versionados no Git.
- URLs assinadas ficam somente no runtime Colab e não são publicadas no handoff.

## Upstream e licenças

- HookLink snapshot: \`dsi-hub/HookLink\`, commit \`b329fa5443ad4bfea016dfd366042a305f221071\`.
- nxnative: \`dsi-hub/nxnative\`, commit \`cf2a2fecc6ce3fb841131ffeffa90915cdadf109\`.
- Os avisos e licenças dos componentes upstream estão incluídos em \`hooklink/\`.
