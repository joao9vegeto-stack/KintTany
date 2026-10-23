# HANDOFF — XOWUE

Data-base: 23/10/2026  
Projeto: X-Men Origins: Wolverine — Uncaged Edition, Xbox 360  
Title ID: 41560816  
Repositório: joao9vegeto-stack/KintTany  
Branch de trabalho: XOWUE, criada a partir de main  
Destino pretendido: aplicativo iOS arm64, usando o projeto PoPTST como referência de organização e integração.

## Estado entregue

A recompilação estática do default.xex foi executada com XenonRecomp, com suporte adicionado para as instruções encontradas neste executável. O resultado foi gerado em generated/ppc e os 345 arquivos C++ passaram por clang++-18 em modo syntax-only.

- Arquivo recebido: 23.052.288 bytes.
- SHA-256: b5afa6ff191194e5cc0a29302878b154baccfa7073868108c5e7416d08b3aa9a.
- XEX2; Title ID 41560816; Media ID 09FF5403.
- Version raw e BaseVersion raw: 0x00000001. Não apresentar como “versão 1.0” sem confirmar a semântica do campo.
- Saída: 345 unidades C++, 288.403.878 bytes de C++ gerado.
- Análise de saltos: 37 tabelas detectadas; 36 mantidas como switch tables estáticas.
- Validação de sintaxe: 345/345 arquivos aprovados com clang++-18, -std=gnu++23 e -fsyntax-only.
- OpCodes não reconhecidos no log final: 0.
- debugtrap emitidos: 0.
- Avisos de condição RC: 0.
- Erros de salto entre funções: 0.

O patch em patches/XenonRecomp-XOWUE.patch foi feito contra o commit upstream ddd128bcca99fe8bfbb99bea583c972351fa6ace. Ele inclui as instruções faltantes observadas no XEX, BLRL, VCM BFP, conversões float16_2 de VPKD3D128/VUPKD3D128 e tratamento de BDZF/BDNZF que salta para uma função separada. Há uma referência de código BSD-3-Clause, indicada em THIRD_PARTY_NOTICES.md.

## Ponto de análise ainda aberto

O log ainda contém 161 falhas de decodificação consecutivas entre 0x83263D50 e 0x83263FE4. O trecho mede 0x298 bytes (664 bytes) e termina no fim da seção .text, cujo intervalo observado é 0x822A0000–0x83263FE8. O mapeamento de funções cria entradas de 4 em 4 bytes nesse trecho; a saída os representa como .long, não como instruções traduzidas. Isso parece um bloco de dados ou preenchimento incluído no fim de .text, mas não foi provado. Antes de remover essas entradas, verificar referências de código, função, relocation e seção; não mascarar o aviso.

A tabela analisada em 0x82BD174C foi removida da lista de switches estáticos porque seus oito destinos são inícios de funções independentes. O XenonRecomp emite uma observação para o BCTR em 0x82BD1770; no C++ gerado o salto usa PPC_CALL_INDIRECT_FUNC(ctx.ctr.u32) e retorna. Não há erro de fronteira nessa saída.

## Limite do que está pronto

Este pacote contém o C++ AOT do default.xex, a configuração e a tradução necessária para repetir a geração. Não contém runtime Xbox 360, ligação de todas as funções, kernel/XAM, mapeamento de memória, implementação Xenos/D3D, XMA/áudio, leitura dos assets, app iOS integrada, IPA ou prova de execução no aparelho. A checagem de sintaxe não é link nem boot.

O usuário forneceu default.xex e uma gravação de tela da estrutura WGame. A pasta completa de assets não foi recebida. Não adicionar default.xex, title updates, DLC, assets ou o C++ gerado ao GitHub. O .gitignore do kit cobre esses arquivos. O ZIP local de recompilação inclui o C++ gerado para transferência ao usuário.

## Próximas ações do agente com acesso ao GitHub

1. Trabalhar somente na branch XOWUE de joao9vegeto-stack/KintTany. A branch já existe e parte de main; não criar branch alternativa nem modificar main.
2. Ler XOWUE/README.md, XOWUE/HANDOFF-XOWUE.md, XOWUE/PROMPT-AGENTE-XOWUE.txt e XOWUE/THIRD_PARTY_NOTICES.md.
3. Revalidar o patch na revisão pinned do XenonRecomp e executar as ferramentas versionadas em XOWUE/tools.
4. Investigar com evidência o trecho final de .text e registrar se são dados ou código. Preservar a descoberta, a decisão e o teste na branch.
5. Auditar imports e chamadas de Xbox kernel/XAM, endereços indiretos, inicialização, relocations e arquivos realmente abertos pelo jogo.
6. Pedir ao usuário a pasta WGame completa quando a integração de assets depender dela. Produzir manifesto local de nomes/tamanhos sem incluir conteúdo no Git.
7. Integrar o código AOT à arquitetura iOS já existente em KintTany. Construir as partes de runtime do Xbox 360 necessárias, testar link arm64, boot, abertura de asset, draw/present e controles.
8. Só declarar jogo executável depois de apresentar um frame real do jogo. Só declarar entrega para iPhone depois de testar no iPhone 17 Pro e fornecer IPA assinável.

## Comandos reproduzíveis

~~~bash
# Clonar o repositório e entrar na branch remota XOWUE
git clone https://github.com/joao9vegeto-stack/KintTany.git
cd KintTany
git fetch origin
git switch --track origin/XOWUE

# Clonar a versão de XenonRecomp usada para esta geração
git clone --recursive https://github.com/hedge-dev/XenonRecomp.git XOWUE/vendor/XenonRecomp
git -C XOWUE/vendor/XenonRecomp checkout ddd128bcca99fe8bfbb99bea583c972351fa6ace
git -C XOWUE/vendor/XenonRecomp submodule update --init --recursive
git -C XOWUE/vendor/XenonRecomp apply "$PWD/XOWUE/patches/XenonRecomp-XOWUE.patch"

# Compilar as ferramentas no host Linux com Clang 18
cmake -S XOWUE/vendor/XenonRecomp -B XOWUE/vendor/XenonRecomp/build-xowue \
  -DCMAKE_C_COMPILER=clang-18 \
  -DCMAKE_CXX_COMPILER=clang++-18 \
  -DCMAKE_BUILD_TYPE=Release
cmake --build XOWUE/vendor/XenonRecomp/build-xowue \
  --target XenonAnalyse XenonRecomp -j"$(nproc)"

# Fornecer o XEX localmente e repetir geração e validação
XENONRECOMP_ROOT="$PWD/XOWUE/vendor/XenonRecomp" \
XENONRECOMP_BUILD_DIR="$PWD/XOWUE/vendor/XenonRecomp/build-xowue" \
XOWUE_XEX="/caminho/local/default.xex" \
XOWUE/tools/run_xowue_codegen.sh

XENONRECOMP_ROOT="$PWD/XOWUE/vendor/XenonRecomp" \
python3 XOWUE/tools/check_generated_cpp_syntax.py
~~~

O script de geração não copia nem publica o XEX. A saída C++ fica em XOWUE/generated/ppc e é ignorada pelo Git.

## Arquivos do pacote

- README.md e START-HERE.md: entrada rápida.
- HANDOFF-XOWUE.md e PROMPT-AGENTE-XOWUE.txt: contexto e instruções do agente.
- XOWUE-INPUT-VERIFICADO.json: metadados e hash da entrada.
- tools/audit_xowue_input.py: auditoria local sem copiar conteúdo do jogo.
- tools/scan_ppc_helpers.cpp: encontra as funções auxiliares usadas na configuração.
- tools/prepare_switch_tables.py: remove apenas a tabela de dispatch de funções já verificada.
- tools/run_xowue_codegen.sh: repete XenonAnalyse, curadoria e geração.
- tools/check_generated_cpp_syntax.py: valida todas as unidades C++ geradas.
- patches/XenonRecomp-XOWUE.patch: alterações para a versão pinned do XenonRecomp.
- generated/config/: TOML, tabelas analisadas/curadas, endereços auxiliares e log final.
- generated/ppc/: C++ AOT completo para entrega local; não deve ser commitado no repositório.

