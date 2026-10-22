# PoPTST Build 15 — encerramento súbito em LiveContainer

## Evidência
No vídeo recebido, a Build 14 abre a interface, inicia a retail e o processo
retorna à tela do iOS, sem apresentar um erro no launcher. O vídeo **não**
demonstra Jetsam, nem distingue SIGSEGV de SIGILL, SIGABRT ou _exit.

## Hipóteses (não confirmadas)
1. Mapeamentos VA do Xbox ou page faults ARM64 não tratados;
2. RECOMP_UNIMPL ou chamada AOT incompleta disparando SIGILL / SIGABRT;
3. Saída explícita do runtime Xbox ou do host;
4. Encerramento pelo iOS ou incompatibilidade do LiveContainer.

Não ampliar RAM física nem reservar páginas fixas inseguras sem evidência.

## Instrumentação nova
- Arquivo em Arquivos > No Meu iPhone > PoPTST:
  **PoPTST-Crash-Build-15.txt**.
- Abertura da janela SDL e da thread registrada antes de criar o guest.
- Passos da VM gravados/forçados em disco, do mapping RAM ao tile/contig.
- SIGSEGV, SIGBUS, SIGILL e SIGABRT não tratados gravam sinal, endereço host
  e PC ARM64 com `write` async-signal-safe e delegam ao handler anterior.
- Logs do app: PoPTST-Diagnostico-Build-15.txt; mostram rastros da tentativa
  anterior se o processo for reaberto. Nenhum SIGILL é ignorado.
- Nunca inclua ROMs, XBE ou assets retail no GitHub/IPA.

## Verificação decisiva
Instale a Build 15 sem apagar os dados da retail; reproduza; no app Arquivos
abra PoPTST-Crash-Build-15.txt e o diagnóstico da Build 15, caso disponível.
O último estágio + PC/hostaddr localiza o fault real. Se houver somente uma
sequência de VM sem sinal fatal, investigar exit/_exit/Jetsam/LiveContainer.

### Referências
- RePOP pinned `4ee36260e71d39fd8b02028fd614b1907a0d451b`;
- PsTJohn/KosmicKrisp `db014165eb39429ae37d1946db6fc83c600c63b3`;
- Build 14 commit raiz `c4a567efb44673cedc957e91ea1b465130314a8b`;
- PoPTST no repo `joao9vegeto-stack/KintTany`, branch órfã apenas;
- Um commit raiz e um workflow por build. Outras branches intocadas.

**Não há evidência suficiente ainda para declarar problema de limite de RAM.**
O sucesso do runner Xcode não valida mapeamento real no aparelho.
