# XOWUE — X-Men Origins: Wolverine (Xbox 360)

**Title ID:** `41560816` · **Branch:** `XOWUE` · **Backend gráfico:** KosmicKrisp (Vulkan → Metal)

## Estado comprovado

- A Action #24, commit `75cab56`, publicou o Build 10 ([artifact](https://github.com/joao9vegeto-stack/KintTany/actions/runs/40011161715)). IPA SHA-256: `0e9251550e5289b31b4db5caab90c3a3553469136f533f2c5d766ff0cd823c6a`.
- O Build 8 fechava no início por `EXC_BAD_ACCESS` em `PC=0`. A causa identificada eram 87.736 aliases PPC weak, resolvidos como weak dyld lookups. O Build 9 ainda continha todos eles, apesar do workflow verde.
- O Build 10 corrige os fontes AOT reconstruídos e adiciona uma validação do Mach-O antes de empacotar. O IPA foi reinspecionado: 133.351 definições AOT fortes, zero aliases/referências weak, zero weak lookups; `sub_8237CA18` agora está ligado como símbolo forte.
- KosmicKrisp permanece como backend Vulkan → Metal e a Action compilou seu ICD arm64. O Build 10 ainda não foi testado no aparelho, então não há frames de jogo confirmados nesta versão.

## App e arquivos do jogo

Coloque a pasta do jogo em **Arquivos → No Meu iPhone → XOWUE → Jogos** ou importe uma pasta/`default.xex` pelo app. Os diagnósticos `diagnostico-build-N.txt` e `crash-build-N.txt` ficam acessíveis pelo app Arquivos. O jogo, saves, DLC e title updates não são incluídos na branch nem no IPA.

O IPA da Action é arm64 e sem assinatura. A instalação exige assinatura Apple compatível.

## Árvore da branch

Os diretórios `Runtime/`, `iOS/`, `generated/`, `dist/`, `patches/`, `tools/` e `upload/` ficam diretamente na raiz desta branch. `.github/workflows/xowue-ios.yml` constrói o IPA. A árvore versionada contém apenas arquivos do XOWUE e o workflow; o conteúdo de `main` não faz parte da árvore atual.

Leia [HANDOFF-XOWUE.md](HANDOFF-XOWUE.md) para arquitetura, validações e comandos. Consulte [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) antes de redistribuir.
