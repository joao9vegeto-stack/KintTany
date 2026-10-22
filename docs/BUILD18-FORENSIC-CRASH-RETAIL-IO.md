# PoPTST Build 18 – relatório forense e correção do crash da Build 17

## Evidência do iPhone
Os dois arquivos LiveContainer-2026-10-21-231824.ips enviados são cópias byte a byte idênticas (SHA-256: 173cb4cf89cd382d54e423d88f366bb8261741ad708c72779a4d96c12bfd1615).

O crash iOS NÃO é Jetsam/OOM: EXC_BREAKPOINT, SIGTRAP, faultThread 5,
PC 0x10BBC47D4, libPoPTSTRetail.dylib UUID 39EE5DAA-71AB-3965-A61F-7A11C6EC7E11.
O frame corresponde à função C recompilada sub_00373454, +3004 ARM64,
proveniente do código x86 em source/xbox-retail/gen/xdk/d3d8/d3d8_0000.c.

Disassembly autenticado do binário da Build 17:
  0x126C7D0: bl _recomp_unimpl
  0x126C7D4: brk #0x1
Correspondência do lift em x86 VA 0x00373580:
  RECOMP_UNIMPL("out dx, al", 0x00373580u);
  edx=0x80C0, al=0x01 (via ebx)
O port tratava essa instrução x86 legítima como não implementada e
forçava SIGTRAP. O arquivo do jogo continua autêntico, e o crash
ocorre no código recompilado D3D8, não dentro de KosmicKrisp/Metal.

## Build 18
- Porta I/O 0x80C0 Xbox vídeo: OUT8 conserva byte em registrador do
  dispositivo; IN8 devolve bit 5 como paridade do campo do vídeo,
  aproximado por clock monotônico 59,94 Hz enquanto o contador de
  vblank real da GPU ainda não é exposto; preserva bits restantes.
- Suporte explícito aos endereços x86 comprovados:
  OUT8 0x00373580, IN8 0x0037246C/0x0037266D,
  WBINVD 0x00371224 com fence seq_cst. Isso corrige os
  opcodes e NÃO simula sucesso para os outros 721 sites.
- Falha fechada em todo outro opcode desconhecido; registra VA/texto
  na pasta Documents, para que novo bloqueio não pareça Jetsam.
- Alterações exclusivamente na branch órfã PoPTST; rePOP upstream e
  PsTJohn intocados; UI e diagnóstico passam a Build 18.
- Não publicar XBE/game assets no IPA nem no repositório.

## Próximos bloqueios potenciais
O trace Build17 mostra erros NtCreateFile: caminho TDATA contendo
prefixos de contêiner de app duplicados e tentativa de criar ERRasser.log.
Isto pode ser real falha de caminho/LiveContainer, mas NÃO explica o
SIGTRAP do PC: aquele trap está comprovadamente no opcode OUT.
Se o próximo teste atingir e falhar um acesso a arquivo, investigue a
tradução Xbox path e RootDirectory/SYMLINK (não falsifique dados).
Se o próximo trace mostrar RECOMP_UNIMPL diferente, recupere opcode
com source-referenced VA e implemente semantics comprovadas.
Renderização real não é comprovada até o app registrar um frame NV2A
e mostrar conteúdo do guest no iPhone.
