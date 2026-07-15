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

## Fase D — Evidência de ESP/wallhack por informação ilegítima 🔨

**Objetivo:** detectar padrões em que a decisão ou a mira acompanha a posição
real de um inimigo que o jogador não deveria conhecer. Um evento isolado nunca
é veredito: cada sinal novo nasce como anotação, é calibrado em demos rotuladas
e só então pode ganhar peso no score.

### D0. Contrato de evidência e baseline 🔨

- ✅ D0.1. Estrutura única de episódio forense (`contexto.py` +
  `dados/episodios.jsonl`): identidade com hash da demo e jogadores
  pseudonimizados, janelas temporais, geometria/oclusão, mira, distância,
  barulho e contraprovas. Fonte não extraível (radar/*spotted*, voz) é gravada
  como `desconhecido` COM razão — nunca `não`. Cada lance vira um registro
  versionado (schema/features/regras) e deduplicado por `episode_id`. Não
  altera score nem HTML (`peso` inalterado). Coberto por testes (`tests/`).
- ✅ D0.2. Candidatos e descartes registrados com motivo, no dataset E no
  relatório: v6.15 adiciona ao card o painel colapsável "Descartes e
  controles" com cada lance excluído (TRACK-PARADO, REFLEXO com info,
  trocas spotted, etc.) e o `demo_gototick` — a decisão é revisável sem
  reler o código.
- 🔨 D0.3. Ferramenta `rotular.py` criada (revisões **append-only** — nunca
  sobrescreve; `listar` + gravação por episódio) e **primeiras 4 revisões
  reais gravadas** (caso de calibração, revisor único: autor): 3
  `evidencia_forte` (wallbang com microajuste em alvo oculto; pré-mira em
  contexto; pré-mira com reflexo pós-LOS rápido) e 1 `legitimo_explicado`
  (falso positivo documentado do PRE-MIRA: abertura de round). Pendente:
  protocolo cego com dois revisores + adjudicação para o conjunto de ouro.

**Pronto quando:** todo sinal futuro recebe contexto e uma justificativa de
inclusão/exclusão reproduzível; nenhum limiar é escolhido somente por intuição.
**Estado:** a fundação de dados (M0 da ARQUITETURA-ML) está materializada; a
calibração assistida por revisão (D0.3) é o próximo passo.

### D1. Modelo de informação legítima 🔨

- ✅ D1.1. `spotted`/radar por teammate É extraível e confiável no
  `demoparser2` (`approximate_spotted_by` = lista de quem vê cada jogador;
  `team_num` = time). Incorporado como exclusão nativa: se um teammate do
  atacante via a vítima durante o tracking, a posição estava no radar do time
  → `TRACK-RADAR` (📡), peso 0. Tem prioridade sobre `TRACK-VIU`/`TRACK-PAREDE`.
  A contraprova `radar_spotted` do episódio deixa de ser sempre "desconhecido"
  e passa a `sim`/`nao` real nos trackings. Validado em caso real (kill onde
  só o teammate via a vítima → exclusão dispara).
- 🔨 D1.2. Trocar a regra binária de barulho por contexto de audibilidade.
  **v6.10:** estimativa de passos (corrida >110 u/s a ≤1100 u do atacante)
  anotada no episódio (`passos_audiveis_estimados`) — SEM mudar exclusões:
  o lance confirmado R21 tem passos=True, então exclusão cega contradiria o
  rótulo. Falta: oclusão acústica/atenuação, tipo do evento e calibração.
- ✅ D1.3. "Última posição conhecida" generalizada (v6.10): a idade da última
  LOS do próprio atacante é MEDIDA em toda a janela carregada (~5,5 s) e
  gravada no contrato (`idade_ultima_visao_s`) para tracks, pré-miras e
  reflexos. A regra binária de 3 s (👀 TRACK-VIU / re-peek) segue inalterada
  até haver rótulos suficientes para calibrar um limiar melhor.

**Pronto quando:** cada candidato de ESP responde: "que informação legítima
existia, para quem, e há quanto tempo?". Voz/discord continuam como limite
declarado da demo, não como certeza de ausência de call.

### D2. Correlação de mira com alvo oculto ⏳

- 🔨 D2.1. **v6.11:** para janelas de tracking (alvo em movimento angular
  material — giro ≥12°, que o teste exige), as séries Δdireção-ao-alvo e
  Δmira são correlacionadas com busca de defasagem (±375 ms) e gravadas no
  episódio (`correlacao_mira_alvo`, `correlacao_max`, `defasagem_ms`) e no
  desc. Duração/amplitude já eram gravadas. Falta: janelas de smoke (hoje só
  parede) e leitura calibrada dos valores (defasagem negativa = antecipação?
  visto 1x, em observação).
- ⏳ D2.2. Separar três estados: mira parada em ângulo comum (não é tracking),
  pré-aim plausível/ambíguo (anotação) e mira que acompanha o alvo oculto
  (candidato forte).
- 🔨 D2.3. **v6.14:** varredura contínua da partida (passo ~125 ms, FORA das
  janelas de kill — primeira análise não-kill-cêntrica do projeto): mira
  grudada ≥0,75 s em inimigo oculto (≥70%) que troca em ≤0,5 s para OUTRO
  inimigo oculto com giro ≥25°, sem kill, sem barulho/visão recente/spotted
  do novo alvo → anotação 🔀 `TROCA-OCULTA` (peso 0, ambíguo). Baseline
  6 partidas: 21 anotações em 13 jogadores (máx 4x; caso de calibração: 0 —
  ESP legit não encara paredes, o sinal mira o estilo descarado). **v6.16:**
  cada troca anota quantos OUTROS jogadores seguram o ângulo novo no mapa de
  ângulos comuns (na demo de calibração: de 1 a 9 — o piso de ruído virou
  número). Falta: rótulos para calibrar o limiar de "comum". A varredura é a
  fundação da linha do tempo de decisões (D4.1).

**Pronto quando:** cada card mostra duração, giro necessário, giro da mira,
correlação e as exclusões aplicadas. Validar visualmente todos os candidatos
em primeira pessoa antes de alterar `pontuar()`.

### D3. Smoke, prefire e timing de gatilho ⏳

- ⏳ D3.1. Evoluir "GATILHO CIRÚRGICO" para uma série temporal do erro angular
  mira→alvo, velocidade do alvo e instante do disparo. Manter observacional
  até haver baseline de partidas suficientes.
- 🔨 D3.2. Classificar prefire/wallbang. **v6.10:** cada PAREDE carrega
  spam vs tiro único (`tiros_2s`), oclusão pré-kill e `ajuste_oculto_deg`
  (correção da mira no alvo oculto no último ¾ s — no wallbang rotulado
  mediu 1,1° ≈ 4x a cabeça na distância, batendo com o veredito do autor).
  **v6.16:** cada PAREDE anota o ângulo comum do lineup (episódio). Falta:
  última posição e nota normalizada por hitbox.
- 🔨 D3.3. **v6.12:** `smokegrenade_detonate`/`expired` são confiáveis
  (duração real medida: ~22,1 s); registro de smokes ativas por partida e,
  em cada smoke kill, a idade da nuvem, o tempo restante e a distância do
  centro à linha de visão — porque `thrusmoke` não distingue nuvem opaca de
  uma DISSIPANDO (visão parcial legítima). Achado: os 3 GATILHO do caso de
  calibração foram por smokes com ≤2,6 s de vida (opacas). Limite conhecido:
  raio (144 u) e centro (z+64) são estimados — 1 kill com thrusmoke ficou sem
  smoke correspondente na LOS. Falta: volume/forma real e uso como oclusão.

**Pronto quando:** kills por smoke e prefire só são candidatas após passarem
pelo modelo de informação legítima da D1; nenhum recebe peso por ocorrer uma
única vez.

### D4. ESP sem assistência de mira: decisões e informação negativa ⏳

**Premissa:** um ESP "legit" pode preservar mira inteiramente humana — erro,
overshoot, reação normal e mortes ruins. A vantagem aparece antes do tiro:
saber qual ângulo, rota e momento são seguros. Portanto, esta etapa não deve
esperar flick, lock ou tracking perfeito para encontrar candidatos.

- ⏳ D4.1. Registrar uma linha do tempo de decisões: rotações, avanço/recuo,
  entrada/abandono de bombsite, save, escolha de duelo e uso de utility.
  Para cada decisão, guardar a informação observável e a posição real dos
  inimigos naquele instante.
- ⏳ D4.2. Medir **cobertura seletiva de ângulos**: quais setores perigosos o
  jogador checou, por quanto tempo e quais estavam ocupados/vazios. Procurar
  a assimetria "checa o ocupado, ignora o vazio" em muitas situações, sem
  confundir uma limpeza rápida com ângulo ignorado.
- ⏳ D4.3. Marcar **informação negativa** como observação: avanço solo por
  área realmente limpa, entrada sem flash, passagem por smoke ou abandono de
  ameaça quando ela de fato não existe. Ação que deu certo não basta; exigir
  ausência de fonte de informação e repetição em cenários independentes.
- ⏳ D4.4. Detectar **janelas seguras invisíveis**: o jogador espera para
  avançar exatamente quando o defensor oculto sai, vira, troca de posição ou
  rotaciona. Medir a defasagem entre a mudança do alvo e a mudança de plano.
- 🔨 D4.5. Detectar **pré-mira humana, porém informada**: crosshair se aproxima
  da posição real oculta, mas a correção final e o tiro continuam manuais.
  Diferenciar isto de pre-aim de canto comum com mapas de ângulos e de última
  posição conhecida. **v6.7:** anotação 🎯 `PRE-MIRA` (peso 0, classe ambíguo):
  mira parada (giro <12°) sobre alvo em movimento OCULTO ≥70%, sem visão
  prévia, barulho ou spotted. Baseline em 6 partidas: 1x/jogador é ruído
  normal; só o caso de calibração do autor repetiu (3x, vítimas distintas).
  **1ª revisão do autor: 2 dos 3 confirmados** (contexto; reflexo pós-LOS)
  **e 1 refutado** (abertura de round — falso positivo documentado); exclusão
  por timing foi calibrada e REFUTADA antes de virar regra (v6.8). Reação
  pós-LOS: ✅ v6.9 (anotação 🧠 REFLEXO). **v6.16:** mapa de ângulos comuns
  anotado em cada PRE-MIRA — e o primeiro dado REFUTA o ângulo como
  discriminador deste estilo: as 3 PRE-MIRAs do caso de calibração são em
  ângulos que 5–6 outros jogadores do lobby também seguram (ESP legit
  pré-mira o ângulo COMUM na hora certa; o discriminador segue sendo o
  timing/reflexo). Falta: escada por vítimas distintas.
- ⏳ D4.6. Reunir decisões de **prefire, wallbang e utility seletivos**: não
  apenas acertar alguém, mas escolher posição incomum/ocupada sem spam,
  lineup, visão recente ou outro sinal. D3 produz a evidência micro; aqui ela
  entra na sequência de decisão do round.
- ⏳ D4.7. Medir **seleção de risco/duelo**: evitar repetidamente o lado com
  vários inimigos e convergir para o isolado, ou chegar por trás sem qualquer
  informação de equipe. Tratar como corroborador fraco, pois leitura de jogo
  e calls podem explicar o evento.
- ⏳ D4.8. Comparar a decisão tomada com alternativas plausíveis do mesmo
  round e registrar explicitamente as contraprovas: visão recente, som,
  granada, radar/*spotted*, teammate e timing padrão. Voz/Discord continuam
  como incerteza declarada, não como prova de ausência de call.
- ⏳ D4.9. Agregar somente por padrões que se repetem em rounds, vítimas e
  partidas distintas. Decisões de D4 nunca recebem score sozinhas: elas
  corroboram sinais de D2/D3 ou entram primeiro como perfil observacional.
- ⏳ D4.10. Criar um detector observacional de **clutch sem medo**: em 1vX,
  registrar limpeza seletiva das ameaças reais, atravessar smoke sem suporte,
  abandono de ângulos perigosos vazios e avanço sem flash/backup. É um caso
  especial de informação negativa e só pode corroborar outros sinais, pois
  clutch tem forte componente de leitura, timing e call de teammate.

#### Matriz de cobertura: comportamentos de ESP sem aim assist

Todos os itens abaixo entram no roadmap mesmo quando a identificação ainda não
está clara. Enquanto não houver métrica e contraprovas confiáveis, o estado é
**exploratório/observacional** e o peso deve permanecer zero.

| Comportamento | Item do roadmap | Estado inicial |
|---|---|---|
| Seleção perfeita de ângulos | D4.2 — cobertura seletiva de ângulos | Observacional |
| Rota “segura” sem informação | D4.3 — informação negativa | Observacional |
| Timing de janela segura | D4.4 — janelas seguras invisíveis | Candidato forte, `peso=0` |
| Pré-mira discreta | D4.5 — pré-mira humana, porém informada | Anotação 🎯 sem peso (v6.7) |
| Prefire seletivo | D3.2 + D4.6 — classificação e sequência de decisão | Candidato forte, `peso=0` |
| Utilitário informado | D4.1 + D4.6 — utility e escolha de posição | Observacional |
| Clutch “sem medo” | D4.10 — detector específico de clutch | Exploratório, corroborador |
| Rotação que acompanha o inimigo | D4.1 + D4.4 — linha do tempo e sincronia com rotação oculta | Observacional |
| Escolha de duelo | D4.7 — seleção de risco/duelo | Exploratório, corroborador |
| Ação em resposta a mudança invisível | D4.4 — defasagem alvo→decisão | Candidato forte, `peso=0` |

**Pronto quando:** o relatório explica a cadeia "informação disponível →
decisão tomada → posição real", mostra o que o jogador deixou de checar e
declara as incertezas. Uma mira humana não exculpa nem condena; o foco é a
sincronia recorrente entre decisão e informação oculta.

### D5. Calibração, score e regressão ⏳

- ⏳ D5.1. Antes de pontuar um sinal, publicar no relatório a versão
  observacional por várias demos, incluindo falsos positivos confirmados.
- ⏳ D5.2. Calibrar por vítimas distintas, partidas distintas e, quando
  possível, mapas distintos; não deixar um único duelo previsível inflar o
  score.
- ⏳ D5.3. Só promover um sinal para `pontuar()` se ele acrescentar evidência
  independente, tiver contraprovas codificadas e sobreviver à revisão
  adversarial de todos os lances marcados.
- ⏳ D5.4. Adicionar testes de regressão com ticks/lances mínimos que cubram:
  ângulo segurado, última visão, barulho/utility, smoke spam, alvo parado,
  wall-track real, troca de alvo oculto, ângulo vazio ignorado, ângulo ocupado
  checado, rota segura por informação legítima e rota aparentemente segura sem
  informação observável.

**Pronto quando:** uma mudança de peso é acompanhada por casos de teste,
comparação antes/depois e justificativa em `APRENDIZADOS.md`.

### Roteiro para agentes de implementação

1. Ler `APRENDIZADOS.md`, esta fase e as funções `analisar_demo()` e
   `pontuar()` antes de editar. Confirmar quais dados a demo realmente expõe;
   não assumir que voz, áudio percebido ou radar estão disponíveis.
2. Implementar primeiro a extração e a anotação no relatório; manter
   `peso=0`. Inspecionar lances em primeira pessoa pelo `demo_gototick`.
3. Para cada candidato, registrar dados brutos, exclusões aplicadas e uma
   explicação curta. Se a explicação legítima não puder ser descartada, usar
   estado ambíguo, não "suspeito".
4. Validar contra os casos de regressão e demos completas. Só depois propor
   limiar, escada por vítimas distintas e peso — todos revisáveis em diff.
5. Atualizar `APRENDIZADOS.md` com o falso positivo ou a nova regra antes de
   encerrar. O resultado esperado é menos acusações erradas, não mais flags.

### Referências de pesquisa

- Estudo de comportamento de wallhack: frequência e continuidade de traços
  ilegítimos, com período de graça após visão legítima —
  [A Novel Approach to the Detection of Cheating in Online Games](https://research.tees.ac.uk/ws/files/6438470/111786.pdf).
- Dataset e modelo recente para CS2; recomenda agregar várias kills, já que
  lances individuais são ambíguos —
  [AntiCheatPT / CS2CD](https://arxiv.org/abs/2508.06348).
- Checklist comunitário de revisão de demo: pre-aim, tracking multi-alvo e
  smoke como sinais, mas com contexto obrigatório —
  [CSWatch](https://cswatch.gg/blog/reading-a-cs2-demo-checklist-cheat-detection).
- Pesquisa sobre *visual hack*/ESP como categoria distinta de assistência de
  mira — [Robust Vision-Based Cheat Detection](https://cdn.buttercms.com/iPaw9YUQBGIdZOB3OUT4).
- Relato comunitário útil para a hipótese de radar ESP: mesmo posição atrasada
  pode criar vantagem de rota e de leitura macro; usar apenas como contexto,
  não como evidência de que toda demo/partida seja afetada —
  [discussão no r/cs2](https://www.reddit.com/r/cs2/comments/1pe0bc6/radar_hack_with_your_own_demo_continuation/).

## Backlog (sem ordem)

- ✅ Assinatura da mira (v6.15, observacional): dp da reação, suavidade do
  yaw (z vs lobby) e spins no card de cada jogador — sem peso até calibrar
  em mais lobbies
- ⏳ Análise em lote de todas as demos + ranking consolidado de reincidentes
- ⏳ Checagem semanal automática de bans (agendador do Windows) — pedir quando quiser
- ⏳ Dataset rotulado via bans confirmados → futuro classificador ML

## Histórico

- 2026-07-15 · v6.16 (mapa de ângulos comuns — pendência de D2.3/D3.2/D4.5):
  todo ângulo SEGURADO ≥0,75 s por qualquer jogador (varredura contínua) vira
  baseline persistente por mapa (`dados/angulos_comuns.json`; célula 128 u +
  setor de yaw 15°; dedup por demo; jogadores pseudonimizados). PRE-MIRA,
  TROCA-OCULTA e PAREDE anotam quantos OUTROS jogadores seguram o mesmo
  ângulo (peso 0). Primeiro dado real (dust2): as 3 PRE-MIRAs do caso de
  calibração são em ângulos COMUNS (5–6 outros) — o ângulo não discrimina o
  ESP legit, confirma que o discriminador é o timing; TROCA-OCULTA variou de
  1 a 9 (instrumento do piso de ruído). Score inalterado; features d0.9;
  +13 testes (106).

- 2026-07-15 · v6.15 (D0.2 ✅ + assinatura da mira): painel "Descartes e
  controles" no card (decisões revisáveis sem reler código) e assinatura da
  mira nativa — dp da reação, suavidade (z vs lobby) e spins, tudo
  observacional. Primeiro dado da assinatura: caso de calibração com
  suavidade z=-2,3 (outlier extremo; hipóteses documentadas: suavizador OU
  quase-zero correção por pré-mira informada), dp de reação humana e zero
  spins no lobby.

- 2026-07-15 · v6.14 (D2.3): troca de mira entre alvos ocultos — primeiro
  sinal FORA das janelas de kill (varredura contínua da partida, ~125 ms).
  Largar um inimigo invisível e travar direto em outro invisível exige saber
  onde os dois estão: assinatura de radar, não de aimbot. Exclusões: kill no
  lance, barulho, visão recente, spotted. Baseline 6 partidas: 21 anotações /
  13 jogadores (piso de ruído de ângulos comuns — documentado); caso de
  calibração: 0 (perfil legit não encara parede). Peso 0; features d0.8;
  +7 testes (93). A varredura funda o D4.1 (linha do tempo de decisões).

- 2026-07-15 · v6.13 (D3.1): timing do disparo vs erro mínimo — 4 das 6 smoke
  kills do caso de calibração dispararam a ≤62 ms do erro mínimo (0,08–0,19°,
  o tamanho da cabeça invisível na distância; R16 a +16 ms). Observacional.

- 2026-07-15 · v6.12 (D3.3): dados reais de smoke. Registro de nuvens ativas
  (detonate→expired por entityid; ~22,1 s medidos) e anotação por smoke kill:
  idade, tempo restante e distância do centro à LOS. Endureceu o GATILHO
  CIRÚRGICO do caso de calibração: as 3 kills foram por smokes FRESCAS
  (0,6/1,7/2,6 s — totalmente opacas), uma delas cruzando a 27 u do centro.
  Registrada 1 discrepância (thrusmoke sem smoke na LOS estimada) — limite
  do raio/centro aproximados, documentado. Features d0.6; +7 testes (86).

- 2026-07-15 · v6.11 (D2.1 parcial): correlação mira↔alvo nativa. Para cada
  TRACK/TRACK-PAREDE, Pearson entre as variações angulares da direção ao alvo
  e da mira, com busca de defasagem (±3 amostras ≈ ±375 ms) — corr→+1 com
  defasagem positiva = mira seguindo informação; corr~0 = prefire/posição.
  Gravado no contrato (features d0.5) e no desc do lance. Primeiro dado real:
  um TRACK-PAREDE com defasagem NEGATIVA (mira antecipou o movimento do alvo
  oculto) — em observação. +6 testes (79 no total).

- 2026-07-15 · v6.10 (D1.2 + D1.3 + D3.2 parcial): contexto forense sem mudar
  regra nenhuma — implementação separada da calibração (pedido do autor).
  Idade da última visão medida e gravada no contrato; passos audíveis
  estimados como anotação (o lance confirmado R21 tem passos=True → exclusão
  cega contradiria o rótulo; 4 dos 5 reflexos anotados têm passos, o mais
  forte — 31 ms — é o único sem fonte alguma); wallbang classificado
  (spam/único + microajuste em alvo oculto: 1,1° medido no lance rotulado).
  Score e sinais idênticos; features d0.4. +8 testes (73 no total).

- 2026-07-15 · v6.9: anotação 🧠 REFLEXO (reação pós-LOS) — tiro letal ≤156 ms
  após a linha de visão abrir, vindo de oclusão sustentada, sem barulho/
  re-peek/spotted; wallbang, smoke e cego ficam fora. Limiar calibrado nos
  lances rotulados (confirmado = 31 ms, refutado = 250 ms). Baseline
  6 partidas/60 jogadores: zero anotações fora do caso de ground truth — que
  somou 5x em 3 vítimas distintas e agora concentra TRÊS sinais observacionais
  independentes (🎯 3x + 🧠 5x + 💨 gatilho 3x), todos com peso 0 aguardando
  escada calibrada. Geometria passa a carregar para toda demo com kills.
  +6 testes (65 no total).

- 2026-07-15 · v6.8 (D0.3): primeira rotulagem humana real + `rotular.py`
  (revisões append-only). O autor revisou 4 lances do caso de calibração em
  primeira pessoa: wallbang com microajuste em alvo oculto, PRE-MIRA em
  contexto e PRE-MIRA com reflexo pós-LOS rápido (3x `evidencia_forte`) +
  PRE-MIRA aos 4,8 s de round (`legitimo_explicado` — 1º falso positivo
  documentado do sinal). A exclusão por timing de round foi calibrada e
  REFUTADA antes de virar regra (lance confirmado aos 9,2 s); em vez disso,
  `segundos_no_round` entra como contexto de todo episódio (features d0.2).
  Próximo sinal: reação pós-LOS. +9 testes (59 no total).

- 2026-07-15 · v6.7 (D4.5): anotação 🎯 PRE-MIRA — o primeiro sinal desenhado
  para ESP "legit" (mira humana, informação ilegítima). O descarte de giro
  <12° (L3, anti aim-assist) escondia quem NÃO gira a mira porque já pré-mira
  certo; agora o TRACK-PARADO passa pela classificação e, se o alvo estava
  oculto ≥70% sem visão prévia/barulho/spotted, vira anotação sem peso, classe
  ambíguo. Calibrado com ground truth do autor (demo dust2): o jogador rotulado
  como wallhack legit foi o ÚNICO em 6 partidas (60 jogadores) a repetir o
  sinal — 3x em vítimas distintas, oclusão 100%; os demais tiveram no máximo
  1x (ruído de pré-aim comum). Score inalterado; +9 testes (50 no total).

- 2026-07-15 · v6.6 (D1.1): exclusão por radar de teammate. Descoberto que o
  `demoparser2` expõe `approximate_spotted_by` (quem vê cada jogador) + `team_num`
  de forma confiável. Novo sinal 📡 `TRACK-RADAR`: se um teammate do atacante
  via a vítima durante o tracking, a posição estava no radar do time (info
  legítima) — não pontua, prioridade sobre 👀/🚨. A contraprova `radar_spotted`
  do contrato D0.1 vira `sim`/`nao` real nos trackings. Só reduz falso positivo
  (nunca aumenta score). +6 testes (41 no total). Validado em 3 mapas + caso
  positivo real.

- 2026-07-15 · v6.5 (D0.1): fundação de dados forense. Cada lance suspeito ou
  descartado vira um **episódio** versionado e reproduzível em
  `dados/episodios.jsonl` (novo módulo `contexto.py`), seguindo o contrato de
  dados da ARQUITETURA-ML: hash da demo, jogadores pseudonimizados, janelas
  temporais, geometria, mira e contraprovas — com fonte não extraível marcada
  `desconhecido` + razão. Novo descarte `TRACK-PARADO` (mira segurando ângulo)
  passa a ser registrado. Zero mudança de score/relatório; primeira suíte de
  testes do projeto (`tests/`, 35 casos, `python -m unittest discover -s tests`).
  Validado em demo real (de_inferno, 203 kills → 39 episódios, dedup OK).

- 2026-07-14 · v6.4: forense de correlação de mira validada em caso real
  (7 lances: zero tracking por raio-x — wallhack de tracking descartado;
  restou perfil de ESP de posição, indistinguível de game sense por lance
  isolado). Nova anotação 💨 "GATILHO CIRÚRGICO" (alvo ≥150 u/s cruzando
  smoke com mira parada ≤3°/s) — em observação, sem peso no score ainda.

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
