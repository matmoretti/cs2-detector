# Roadmap — CS2 Detector de Suspeitos

Documento vivo: status atualizado a cada evolução do projeto.
Legenda: ✅ feito · 🔨 em andamento · ⏳ pendente · 🧱 bloqueado

## Fase A — Rastreador de bans + contexto de conta (Steam) ✅

- ✅ A1. `config.json` com chave de API da Steam (opcional — sem chave usa
  o perfil público XML, com menos campos)
- ✅ A2. `steam_info.py` — bans (VAC/jogo), idade da conta, nível, horas de
  CS2, privacidade; API oficial com chave, fallback público sem
- ✅ A3. `checar_bans.py` + `CHECAR-BANS.bat` — reconsulta todo o
  `historico.json` e avisa bans novos + taxa de acerto do detector
- ✅ A4. Relatório: chips de contexto (☠ já banido / 🐣 conta nova /
  🔒 perfil privado) + links csstats.gg e Leetify
- ✅ A5. Testado com os 10 jogadores da demo real — **na primeira checagem
  já achou 1 VAC ban (justamente num jogador que o detector tinha marcado)**

**Upgrade opcional:** chave em steamcommunity.com/dev/apikey (grátis, domínio
"localhost") → colar em `config.json` → ganha nível Steam + horas de CS2.

## Fase B — Visibilidade real (geometria do mapa) ✅

- ✅ B1. `awpy` instalada; geometria (.tri) de todos os mapas oficiais baixada
  em `~/.awpy/tris` (validação: wallbangs do jogo dão "invisível", kills
  abertas dão "visível" em 92%)
- ✅ B2. Sinal novo 🚨 TRACK-PAREDE: tracking com parede na linha de visão em
  ≥70% do tempo (checado por raycast na geometria)
- ✅ B3. Recalibrado: 1x pesa pouco (pode ser rastreio legítimo pelo som),
  repetição pesa muito — 1→10, 2→22, 3+→35 pontos

## Fase C — Radar visual das kills suspeitas ✅

- ✅ C1. Imagens de radar + calibração de coordenadas (awpy) em `~/.awpy/maps`,
  copiadas pra `cs2-detector/maps/` junto do relatório
- ✅ C2. Posições de atacante/vítima gravadas em cada momento suspeito
- ✅ C3. Mini-mapa no card: linha atacante→vítima, cor por gravidade, tooltip
  com round/vítima, suporte a mapas de 2 andares (Nuke/Vertigo/Train)

## Backlog (sem ordem)

- ⏳ Assinatura da mira: variância do tempo de reação (triggerbot), suavidade
  do traçado (aimbot humanizado), detector de spinbot
- ⏳ Análise em lote de todas as demos + ranking consolidado de reincidentes
- ⏳ Checagem semanal automática de bans (agendador do Windows) — pedir quando quiser
- ⏳ Dataset rotulado via bans confirmados → futuro classificador ML

## Histórico

- 2026-07-14 · v1: estatísticas de eventos (HS%, smoke, wallbang, cego)
- 2026-07-14 · v5: análise de mira tick a tick (flick, reação, tracking),
  precisão real, score 0–100, histórico de reincidentes, relatório novo
- 2026-07-14 · v6: Fases A+B+C — rastreador de bans Steam (1º VAC ban
  encontrado na 1ª checagem!), tracking através de parede por geometria real,
  radar visual no relatório
- 2026-07-14 · v6.1: filtro anti-falso-positivo em kills por smoke (só tiro
  preciso ≥7 m pontua; spam vira 🌫️ informativo) — calibrado com ground truth
  do próprio autor, flagrado injustamente por smoke spam; geometria
  do de_cache construída a partir dos arquivos do jogo (agente do workflow)
- 2026-07-14 · v6.2: correção de falha sistemática achada pela perícia
  multi-agente do Cache (4 céticos refutaram os 4 flagrados com confiança
  alta — um deles tinha girado a mira só 2° em 2,2 s de suposto "tracking"):
  o detector checava se a VÍTIMA se movia, mas não se a MIRA a seguia
  — segurar ângulo parado contava como tracking. Agora: tracking exige a
  direção até o alvo mudando ≥12° com a mira acompanhando, e vítima que
  atirou nos 5 s anteriores (posição revelada por som) vira 🔊 sem pontuar.
  Re-análise das 3 demos: zero suspeitos remanescentes — lobbies limpos,
  confirmado por assinatura de mira 100% humana nos 30 jogadores.
- 2026-07-14 · v6.3 + ciclo de aprendizado: criado APRENDIZADOS.md (base de
  conhecimento que os agentes de perícia leem antes de trabalhar e alimentam
  depois — cada lição codificada torna o veredito desnecessário para aquele
  padrão). Codificadas L5 (granada/decoy revela posição), L6 (👀 atacante viu
  o alvo ~3 s antes = última posição conhecida, não pontua) e L7 (escalada de
  score exige vítimas DISTINTAS). Pendentes no APRENDIZADOS.md: spotted por
  teammate, atenuação de som, reação pós-LOS, assinatura da mira nativa.
