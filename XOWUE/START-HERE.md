# XOWUE — início rápido

Branch de trabalho: `XOWUE`, no repositório `joao9vegeto-stack/KintTany`.

A geração AOT do `default.xex` foi concluída: 344 arquivos de funções mais `ppc_func_mapping.cpp`, 345 unidades C++ no total. As partes compactadas em `dist/` são reunidas pelo workflow de macOS para montar o IPA. O original `default.xex` e os assets permanecem fora do Git.

O runtime inicial carrega o XEX, monta o mapa de funções e chama `_xstart`. `NtAllocateVirtualMemory` e `NtFreeVirtualMemory` têm suporte básico no heap guest; `HalReturnToFirmware` encerra o diagnóstico com a rotina solicitada. Os outros 258 imports Xbox/XAM continuam fail-closed. O teste do host chega a `HalReturnToFirmware(routine=1)`, portanto isso ainda não é um boot jogável.

Leia `HANDOFF-XOWUE.md` para comandos, arquitetura e limites do runtime. O app cria a pasta **Arquivos > No Meu iPhone > XOWUE > Jogos** e detecta automaticamente o `default.xex`; também aceita uma pasta pelo seletor ou abrir o `.xex` diretamente. A IPA aparece no app como **Build 1**, depois Build 2, Build 3… e continua unsigned até receber assinatura Apple.
