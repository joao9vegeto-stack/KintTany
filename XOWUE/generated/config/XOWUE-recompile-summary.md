# Resultado da recompilação — XOWUE

Data: 23/10/2026  
Title ID: 41560816  
Entrada: default.xex, 23.052.288 bytes, SHA-256 b5afa6ff191194e5cc0a29302878b154baccfa7073868108c5e7416d08b3aa9a  
XenonRecomp: ddd128bcca99fe8bfbb99bea583c972351fa6ace, com patches em patches/XenonRecomp-XOWUE.patch.

## Resultado

| Verificação | Resultado |
|---|---:|
| Unidades C++ geradas | 345 |
| Bytes de C++ | 288.403.878 |
| Unidades aprovadas no syntax-only | 345/345 |
| Instruções não reconhecidas | 0 |
| debugtrap emitidos | 0 |
| Avisos RC | 0 |
| Erros de fronteira de switch | 0 |
| Tabelas estáticas mantidas | 36 |

A tabela de dispatch em 0x82BD174C foi excluída da lista de switches estáticos porque seus destinos são inícios de funções. O BCTR em 0x82BD1770 é traduzido para chamada indireta via PPC_CALL_INDIRECT_FUNC.

## Item pendente

161 falhas de decodificação cobrem 0x83263D50–0x83263FE4, exatamente os 664 bytes finais antes do fim observado da seção .text em 0x83263FE8. O mapa os trata como símbolos a cada 4 bytes e XenonRecomp escreve .long. Isso sugere dados ou padding, mas é necessário verificar referências antes de removê-los.

## O que a validação não prova

O resultado prova que o tradutor gerou C++ e que cada unidade passa pelo parser do Clang. Não prova link, comportamento equivalente, boot, leitura de assets, renderização, áudio, controles, IPA ou execução em iPhone.

## Repetir

~~~bash
XENONRECOMP_ROOT="/caminho/XenonRecomp" \
XENONRECOMP_BUILD_DIR="/caminho/XenonRecomp/build-xowue" \
XOWUE_XEX="/caminho/local/default.xex" \
tools/run_xowue_codegen.sh

XENONRECOMP_ROOT="/caminho/XenonRecomp" \
python3 tools/check_generated_cpp_syntax.py
~~~

