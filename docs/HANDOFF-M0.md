# AscensionRecomp — Handoff M0 (2026-10-14)

## Escopo imutavel
- Alvo: God of War: Ascension PS3; ARM64 iPhone 17 Pro; 30 fps reais e estaveis, 60 fps meta secundaria.
- Repositorio: joao9vegeto-stack/KintTany, branch unica `AscensionRecomp`.
- As outras branches nao podem ser modificadas, nao disparar CI de nenhuma delas.
- Um commit por build, um workflow por commit, acompanhar Actions antes de declarar sucesso.
- Nao usar bypasses especificos de cena; comparar comportamento ao RPCS3.
- Nenhum jogo/firmware/chaves/binaries proprietarios no GitHub publico.

## O que o M0 realmente faz
- Repositorio limpo com workflow exclusivo em macos-26.
- Analise local ELF64 PPU / ELF32 SPU big endian, SHA256, PT_LOAD e limites.
- Unittest com fixtures artificiais para PPU, SPU, SELF incorreto, segmento invalido, maquina invalida, CLI.
- Biblioteca upstream ps3recomp 0.11.0 compilada macOS arm64 com Metal configurado por CMake (build de link nao prova rendering).
- Artefato CI: static lib e logs, NAO IPA. Uma build bem-sucedida so comprova ferramentas.

## Premissas tecnicas a validar
- eboot PPU legivel pelo ppu_loader.py: gerar functions/imports/image/loader JSON.
- Cobertura de funcoes OPD + branches indiretos + toc; nao assumir que PPU lift integral fecha.
- Modulos SPU podem estar empacotados dentro de arquivos ou carregados dinamicamente; revisar runtime/cellSpurs.
- RSX com fidelidade (queries, reservations, tiling, depth, MSAA) e shader pipeline; Metal upstream pode nao atender Ascension.
- So medir 30fps apos gameplay real; ver frametime PPU/SPU/RSX/Metal e p5 de FPS por cenas e sessoes prolongadas.

## Pedido concreto ao usuario para M1
Solicitar, de sua copia, **EBOOT.ELF descriptografado** (nao EBOOT.BIN SELF),
**PARAM.SFO** e o Title ID/versao (BCUS98232/BCES... conforme arquivo real);
se houver, lista de modulos SPU/SPR X, mas nao necessaria no primeiro contato.
Enviar por canal privado/conversa, nao commitar ao GitHub; alternativamente rodar
`tools/elf_inventory.py` e enviar so manifest JSON.
O `EBOOT.ELF` sera necessario para efetivamente liftar o titulo.

## Proximas gates
M1 manifest real + loader; M2 PPU lift e imports; M3 SPU e DMA;
M4 boot iOS; M5 imagem; M6 estabilidade; M7 30fps; M8 60fps.
