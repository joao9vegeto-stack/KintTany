# XOWUE Build 105 — auditoria de progressão de frames

## Evidência da Build 104.3
Telemetria disponível: 720 apresentações do host, um único upload/frame CPU decodificado, zero guest swaps registrados no caminho observado e thread 12 parada em PC 0x82C4D4A8. Isso não demonstra progresso do jogo; as apresentações repetiam o mesmo framebuffer.

## Falha da Build 271
A etapa Build arm64 AOT engine falhou porque o caminho NtReadFile referenciava kNtStatusPending sem declarar NTSTATUS STATUS_PENDING (0x00000103). A constante foi adicionada e incluída no teste de contrato.

## Comparação com MW2 Recompiled iOS
- Dwords zero são padding PM4 e não podem consumir o próximo header.
- INDIRECT_BUFFER (0x3F) e INDIRECT_BUFFER_PFD (0x37) são tratados.
- Buffers indirectos exigem alinhamento de 32 bytes, limite de 16K dwords e profundidade máxima 4.
- SET_BIN_MASK/SELECT e predicação do bit 0 são aplicados.
- VdSwap escreve XE_SWAP na primeira posição dos 64 dwords reservados, seguido por NOPs; não injeta fetch constants no segmento nem apresenta diretamente um framebuffer CPU.
- XE_SWAP consumido pelo command processor, não uma chamada direta de VdSwap, é a fronteira de frame.

## Alterações consolidadas
1. STATUS_PENDING declarado.
2. NtReadFile publica IOSB e sinaliza evento antes de enfileirar a notificação APC; contexto APC nulo não suprime o callback.
3. Parser PM4 alinhado aos limites e à semântica de padding/predicação do MW2.
4. VdSwap segue o layout reservado de 64 dwords, registra endereços/ring e deixa contagem e apresentação ao command processor.
5. XE_SWAP notifica o backend nativo mesmo sem fetch CPU válido.
6. Framebuffer CPU só é novo se seus bytes mudarem; uma imagem antiga não bloqueia XDProcessDraws.
7. KKRenderFrame só apresenta após um XE_SWAP novo, impedindo que CADisplayLink seja contado como frame do jogo.

## Critérios obrigatórios de runtime
- Build ARM64 AOT e IPA concluídos.
- XOWUE_VDSWAP_PACKET_QUEUED e XOWUE_PM4_XE_SWAP para os pacotes reais.
- Serial XOWUE_NATIVE_GUEST_FRAME crescente.
- XENOS_GPU_DRAWS_SUBMITTED crescente; observed_draws/queued não bastam.
- XENOS_COMPOSITED_GPU_READBACK com pixels/checksum variando durante gameplay.
- Thread 12 sai de 0x82C4D4A8 e os swaps continuam crescendo após o copyright.
- Não declarar gameplay funcional apenas por compilação ou por um framebuffer decodificado.

A cobertura total de shaders, texturas e EDRAM só pode ser considerada comprovada pelo resultado real do runtime.

## PM4 completion parity added
- LOAD_ALU_CONSTANT (0x2F) now copies bounded big-endian guest memory into the correct Xenos constant window.
- EVENT_WRITE_CFL (0x59) now writes its guest fence value and is ordered after already submitted native frames.
- WAIT_FOR_IDLE (0x26), EVENT_WRITE_SHD and EVENT_WRITE_CFL now request a bounded native-frame completion wait.
- XE_SWAP itself blocks the CP worker until the matching Vulkan queue submission/present completes (maximum 500 ms); timeout is explicitly logged rather than hanging the guest forever.

## Resultado da auditoria global PPC AOT (Build 281)
- 344 unidades PPC nativas analisadas.
- 115.125 funções nativas encontradas.
- 57.587 chamadas indiretas ainda presentes; são arestas de dispatch, não automaticamente funções ausentes.
- 370 switches locais nativos já identificados pelo CFG audit.
- 54 tabelas XEX verificadas e correspondidas ao source.
- 1.158 destinos de tabela classificados como alvos locais nativos; zero destinos de tabela não resolvidos.
- 18 callsites foram ignorados pelo pass genérico porque o trecho não continha o wrapper exato PPC_CALL_INDIRECT_FUNC. Isso não prova ausência de código: o próximo passo agora registra owner, unidade e trecho para distinguir switch/goto nativo já existente de dispatch ainda guardado.
- Nenhuma continuação cross-function adicional foi necessária neste conjunto (native_continuations=0), pois os destinos verificados estavam dentro dos owners nativos.
