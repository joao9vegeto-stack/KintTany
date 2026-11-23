# Fairy2iOS KTGL — auditoria de causa, 23-11-2026

CRASH CONFIRMADO: run 45100431103, artefato 14784783270. Ambos hooks G1T e G1S acionados; mesmo abort main+0xbfe2a8. Backtrace main+c10b90 > main+c11928 > main+c6ff10 > main+c723bc. Mensagem do abort: can't create resource Name[Unknown] Hash[0xac9ed13e].

IO comprovado: 45 leituras FDATA monitoradas tiveram got=want; leitor KTGL recebeu quota zero para 20 bytes (G1T) e estado 0/0/0/0 para 184 bytes (G1S). Os dois objetos originais foram criados sem conteúdo disponível; G1T/G1S fallback não eliminou a origem. Não é jetsam (footprint ~0.80 GB).

Prova original assinada: run 45094304340 artifact 14782159778; SHA IPA b1792f9eb522de53b2b252e3a85229584831434999edda98f31c87c7c8c256cd. Disassembly: main+c095c8 chama vtable+0x18 para avançar e em main+c095f0 sub x8,x20,x0, indicando que x0 contém bytes consumidos nesta chamada. main+c09604 chama vtable+0x20 para ler e em main+c0962c sub x8,x20,x0. Ambos clampam pedido à quota. O fallback anterior f2_skip retornava cursor absoluto e f2_read retornava zero em leitura parcial. Este é um defeito material comprovado por teste C, corrigido na fonte e testado sem gerar IPA.

ORIGEM AINDA EM ABERTO: stream produtor KTGL main+c10510..c10b90 e main+c11b60..c11fc0 entrega quota zero. Corrigir apenas substituto de leitor NAO prova correção da causa-raiz. Bloquear mais builds especulativos até garantir a origem, a semântica e o ciclo de vida do objeto, com comparação estática/execução Mac.

Referência comprovadamente funcional: seedds/nxnative dm/games/0100C2A01A730000, ROMANCE OF THE THREE KINGDOMS 8 REMAKE, SDK17.5.3, KTGL moderno RDB/RDX/FDATA modo4; iPhone executa e Mac percorre gameplay e saves. Fairy Tail 2 SDK17.5.4. Não confundir parser de arquivo mode4 em shader_split.py com leitor de recurso de runtime KTGL.

Referências: https://github.com/joao9vegeto-stack/KintTany/actions/runs/45100431103 ; https://github.com/joao9vegeto-stack/KintTany/actions/runs/45094304340 ; https://github.com/joao9vegeto-stack/KintTany/actions/runs/45063871048 ; https://github.com/seedds/nxnative/tree/main/dm/games/0100C2A01A730000
