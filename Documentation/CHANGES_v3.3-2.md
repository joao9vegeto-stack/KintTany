# KintTany v3.3 — Build 78

## Escopo

Redesign visual da interface SwiftUI sobre a base funcional da v3.2 build 76.
O motor de automação, protocolo, WebSocket, Presence, persistência, banco,
background processing e safe exit não foram alterados.

## Interface

- novo dashboard mobile denso inspirado prioritariamente na referência principal;
- masthead noturno, connection strip e painéis compactos em navy/cyan;
- branding visível padronizado como `KintTany`;
- hero dinâmico vinculado à atividade realmente ativa;
- header com versão, build, conexão, duração da sessão e região;
- meta da sessão e progresso conectados ao `AppStore` existente;
- contexto de isca mantém as restrições reais de protocolo da pesca;
- seletor com as dez atividades e thumbnails específicas;
- telemetria, estatísticas e eventos continuam usando dados reais;
- log completo preserva copiar, exportar e limpar;
- componentes e tema foram extraídos do `RootView`.

## Assets

Foram adicionados dez banners horizontais em `Assets.xcassets/ActivityArtwork`.
As artes de Madeira e Cacti foram corrigidas para usar machado, preservando o
personagem, a cena, o enquadramento e a identidade visual das demais atividades.

## Correções da build 78

- restaurados os `Contents.json` válidos de Fishing e Silver;
- restaurado o PNG real de Iron Ore;
- removido `Contents-2.json`, metadado binário do macOS enviado por engano;
- adicionado preflight no GitHub Actions para bloquear JSON, PNG ou AppleDouble
  inválidos antes de executar o `actool`.
