# Auditoria do fluxo iOS e comparação dos launchers

## Falha que fechou o app

O IPS de 20/10 mostra `SIGSEGV` dentro de `memmove`. O host reservou uma VM
guest de `0x10000000` bytes (256 MiB), mas o setup do processo copiava PT_TLS
para `vm_base + 0x10f00000`, 15 MiB depois do limite. Corrigi a posição da
imagem TLS para depois da pilha e validei os limites antes de copiar/zerar a
imagem. O teste estático de regressão foi adicionado ao conjunto que o Actions
executa.

## O que o projeto executa hoje

1. O seletor importa um ELF privado; o código confere tamanho, SHA-256 e
metadados ELF.
2. Antes do runtime PS3Recomp, a tela executa em série os checkpoints PPC
históricos M6.0–M6.7.6. Eles são microprovas do bootstrap, não uma sessão de
 jogo e não são pré-requisito técnico do dispatcher M7.72. É trabalho
 redundante no caminho que o usuário chama de iniciar.
3. Com `USRDIR` reconhecido, o host inicializa o runtime recompilado, monta a
 pasta autorizada como VFS e prepara thread principal, TLS e `argv` PS3.
4. O dispatcher roda com orçamento de 32.768 instruções e depois a VM, o
   runtime e a autorização da pasta são encerrados. O processo não fica vivo.
   O código não entrega o controle a um loop de jogo persistente.
5. A aba Metal apresenta quadros de diagnóstico criados pelo host. Não há
   caminho demonstrado de comandos RSX do Ascension para Metal nem primeiro
   quadro do jogo.

## Problema principal de progresso

O gargalo deixou de ser “o app não abriu o ELF”. O host está fazendo uma prova
limitada de entrada e encerrando-a. Ainda faltam runtime de sessão persistente,
tratamento completo das chamadas de sistema e serviços bloqueantes do título,
continuação dos dispatches até a inicialização de recursos do jogo, renderer
RSX para Metal e gate de apresentação no primeiro quadro guest. Isso explica
por que a interface podia ficar em execução ou mostrar Metal azul sem mostrar
progresso visual do jogo. Chamar o fluxo atual de “executar jogo” era enganoso.

## Comparação com as referências

- O launcher do [gow-ascension-pc](https://github.com/arnaldolima1/gow-ascension-pc)
  mantém etapas de preparação, inicia um processo de jogo separado, acompanha
  sua saída em log e trata encerramento/falha. O relatório de FPS citado pelo
  projeto é resultado de PC; não prova compatibilidade iOS. A UI iOS agora
  prioriza seleção do ELF e arquivos, e deixa os testes RSX na aba separada.
- O host iOS de [gow2-recomp](https://github.com/andrebrumdev/gow2-recomp)
  executa o guest em thread própria e só apresenta a tela de jogo quando recebe
  um quadro guest real. É um padrão de ciclo de vida aplicável. O backend GoW2
  não é um renderer intercambiável para Ascension.
- O runtime vinculado é o [ps3recomp](https://github.com/sp00nznet/ps3recomp)
  fixado pelo workflow. A tabela AOT estática está ligada ao app; isso não
  transforma o teste limitado atual numa sessão de jogo completa.

## Estado contra as passagens do projeto

M0–M4 seguem parciais: artefato e loader são construídos, há runtime nativo,
VFS autorizado e preparação de entrada PS3, mas o CRT ainda precisa provar que
avança até chamadas de arquivos do jogo. M5 não passou: os quadros são testes
Metal, não saída RSX do Ascension. M6 e o critério de 30 FPS M7 não passaram:
não existe primeiro quadro de gameplay medido neste port. `M7.72` é número da
versão, não aprovação do marco M7.

## Mudanças desta revisão

- Corrigido o endereço/limite de PT_TLS que causava o encerramento do app.
- A tela inicial agora é um launcher escuro; o fundo azul de diagnóstico só
  aparece na aba RSX/Metal. O ELF aparece como ação principal e as opções de
  preparação vêm em seguida.
- O texto diferencia “prova de boot nativo” de gameplay e não apresenta o
  quadro de diagnóstico como se fosse imagem do jogo.
- Adicionada cobertura de regressão para o limite TLS, executada pelo workflow
  de CI.

O próximo avanço de runtime exige que o relatório do dispositivo mostre
despachos M7.72 aumentando e contadores `cellFsOpen`/`cellFsRead` positivos.
Depois disso, o próximo bloqueio é o caminho RSX→Metal até um primeiro quadro
real; FPS só faz sentido medir após esse marco.
