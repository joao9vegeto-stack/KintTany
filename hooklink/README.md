# HookLink2iOS

Integração do pipeline HookLink/nxnative na branch isolada `HookLink2iOS` do KintTany.

## Escopo do jogo

- Jogo: The Legend of Zelda: Ocarina of Time (Nintendo Switch 2 Edition)
- Title ID: `0400486024DEC000`
- Update: `v131072`
- Engine: `dsi-hub/nxnative`, branch upstream `hooklink`
- Pin do engine: `cf2a2fecc6ce3fb841131ffeffa90915cdadf109`
- GPU preset inicial: `g18p` (família A19 / iPhone 17)

Este builder está configurado para esse alvo específico, não é um conversor universal de NUPs.

## Fluxo

1. Execute `colab/HookLink2iOS_Colab.ipynb`.
2. Forneça um dump próprio em `.nup` ou um arquivo compactado que contenha exatamente um NUP (`.rar`, `.zip`, `.7z`, tar etc.). O notebook não contém um URL de jogo predefinido.
3. O Colab/Linux valida o arquivo compactado, extrai o NUP e mantém o NUP. O arquivo compactado é removido somente depois que a geração e validação do RomFS terminam.
4. O Colab clona o nxnative no commit fixado e usa `scripts/pack_nup.py` para criar `RomFS.img` diretamente do NUP em `extract/v131072/RomFS.img`. O conteúdo do RomFS não é expandido em milhares de arquivos.
5. O Colab produz o overlay de resolução HookLink e envia NUP, `romfs.img` e overlay para uma pasta exclusiva de execução no Google Drive, com verificação de tamanho, SHA-256 e MD5.
6. O Colab atualiza somente `hooklink2ios/handoff.json` na branch `HookLink2iOS`.
7. O Actions baixa os arquivos do Drive, verifica integridade, executa o builder iOS no runner `macos-26` com Xcode/Metal 27.2 e `--romfs separate`.
8. O Actions publica a IPA como artifact e tenta enviar IPA, overlay e relatório ao Google Drive. Se o upload ao Drive falhar, o artifact do Actions continua sendo gerado.

A preparação Linux é responsável pela entrada NUP, pela imagem RomFS e pelo overlay. O builder ainda realiza no Mac as etapas upstream que dependem do ambiente macOS/Xcode/Metal, incluindo a geração das bibliotecas Metal/shaders e a compilação da IPA.

## Isolamento de workflows

- O novo workflow tem trigger `push` na branch `HookLink2iOS` e no caminho único `hooklink2ios/handoff.json`.
- O job também verifica `github.ref == refs/heads/HookLink2iOS`.
- Os workflows preexistentes de Link2iOS continuam limitados à branch `Link2iOS`; não foram alterados.
- Não existe `workflow_dispatch`, `workflow_run`, `schedule` ou trigger por tag no novo workflow.
- Adicionar/editar os arquivos do builder não dispara a compilação. Somente a gravação de um handoff Colab válido inicia o Actions nessa branch.

## RomFS no iPhone

A IPA não contém o conteúdo grande do jogo. O NUP é entrada de build; a imagem externa deve ser copiada para o container de dados do app instalado:

```text
AppDataContainer/
└── Documents/
    ├── romfs.img
    └── res_overlay/
        └── Pack/
            └── Bootup.Nin_Ounce_NVN2.pack.zs
```

Não coloque `romfs.img` na raiz da IPA nem em qualquer pasta pública de Files. Use o script upstream copiado em `hooklink/scripts/push_romfs.sh` quando o app já estiver instalado e houver um Mac conectado ao iPhone. Ele suporta AFC/afcclient e devicectl, com verificação de integridade e publicação atômica do arquivo.

## Segredos e permissões

Configure no repositório GitHub o secret `GOOGLE_SERVICE_ACCOUNT_JSON` com uma conta de serviço que tenha acesso de leitura/escrita à pasta de execução no Drive. O compartilhamento da pasta pai deve dar acesso a essa conta.

No Colab, autentique sua conta Google com acesso à pasta pai e forneça um GitHub PAT com permissão Contents read/write somente para este repositório. O PAT é solicitado ocultamente e não é gravado no notebook.

Nenhum NUP, ROMFS, arquivo de jogo, IPA, chave ou dado derivado é versionado no Git.

## Upstream

- HookLink snapshot: `dsi-hub/HookLink` commit `b329fa5443ad4bfea016dfd366042a305f221071`
- nxnative: `dsi-hub/nxnative` commit `cf2a2fecc6ce3fb841131ffeffa90915cdadf109`
- HookLink e nxnative license files estão incluídos sob `hooklink/`.
