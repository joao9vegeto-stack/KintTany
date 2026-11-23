# Plano de regressão/recuperação do produtor KTGL — 2026-11-23

Somente candidato de reparo; não há gameplay verificado no iPhone. Duas falhas do nosso leitor C host constatadas na IPA do run 45100431103 e testadas em x86_64/ARM64 clang (retorno cursor absoluto versus bytes consumidos por operação; rejeição de leitura parcial). O código corrigido mantém os parsers G1T/G1S originais e usa dados IDRK do FDATA com SHA256 validado.

Disassembly AArch64 original da IPA assinada, read-only run 45094304340: main+c107d8 f40319aa MOV x20,x25 após chamar main+c10d80, seguido de main+c107dc TBZ w0,0 (decisão do produtor mode4). main+c11f54 880640f9 LDR x8,[x20,#8], seguido de main+c11f5c que limpa a fonte se for não-zero. O host emula exatamente MOV/LDR e registra resultado original, pointer, quota/contadores da rota de leitura direta. Portanto o próximo dispositivo dará a primeira transição produtor→fonte vazia sem inventar bytes ou alterar o sinal de retorno.

Evidência de falha anterior: no log real os buffers KTGL `main+2a644f8` (quota0) encaminham a `main+2a64b50` (leitor direto) com `inner_data=0`. Isso não prova que a fonte foi inicialmente nula: `main+c11f54` explicitamente zera `reader+8` ao transitar pela falha. O observador atual reporta os campos antes de zerar, para distinguir falha de descompressão/producer versus objeto inicial sem fonte. Não generalizar os resultados do FDATA: got=want no HLE filesystem não prova sucesso do codec.

Referência funcional: ROMANCE OF THE THREE KINGDOMS 8 REMAKE upstream seedds/nxnative dm/games/0100C2A01A730000 (KTGL moderno RDB/RDX/FDATA, iPhone confirmado). As funções da engine NXNative h_fs_ReadFile eram iguais no pin/HEAD; o bug observado é pós-FS.

Critério de conclusão real: iPhone passa da factory, inicia título/cena, texturas e FPS são verificadas. Build/CRC/32 testes C/Python não equivalem a esse teste.
