# Aprendizados — base de conhecimento do detector

Documento vivo que fecha o ciclo de aprendizado do projeto:
**perícia (agentes) descobre → lição registrada aqui → codificada no
`analisar.py` → próxima perícia não precisa redescobrir.**

Regra do processo: todo agente de diagnóstico ou veredito DEVE ler este
arquivo antes de trabalhar, e todo veredito DEVE terminar listando lições
novas (ou declarando que não há). Lição codificada = o agente de veredito
fica desnecessário para aquele padrão.

## Lições codificadas (já no analisar.py)

| # | Lição | Origem | Código |
|---|-------|--------|--------|
| L1 | Kill por smoke sem contexto é sinal fraco: spam de posição conhecida é jogada padrão. Só pontua tiro preciso (≤4 tiros/2 s) a ≥7 m; resto vira 🌫️ informativo. | Ground truth do autor do projeto (Cache) | v6.1, filtro no evento thrusmoke |
| L2 | Wall-track isolado pode ser rastreio por som; repetição é o sinal. 1x pesa pouco. | Calibração Nuke | v6, escada 1→10/2→22/3→35 |
| L3 | **Checar movimento da vítima não basta: a MIRA precisa seguir o alvo.** Segurar ângulo parado enquanto a vítima anda dentro do cone de 6° não é tracking (falha que flagrava 4-5 jogadores/partida). | Perícia Cache: 4/4 vereditos refutados (um flagrado girou a mira só 2° em 2,2 s) | v6.2, TRACK_MIN_GIRO=12° sobre a direção atacante→alvo |
| L4 | Vítima que atirou nos ~5 s anteriores revelou a posição (som + tracer + radar). Tracking depois disso é info legítima. | Perícia Cache (a vítima spammava M4 sem silenciador; o modelo de audibilidade só olhava passos) | v6.2, janela de 320 ticks sobre weapon_fire → 🔊 TRACK-INFO, 0 pts |
| L5 | Granada/decoy jogada também revela posição, não só tiro. | Veredito de uma AWP por smoke (vítima soltou decoy 9 s antes) | v6.3, "barulho" inclui granadas |
| L6 | Atacante que TEVE linha de visão para o alvo segundos antes da janela joga por "última posição conhecida" — não é wallhack. | Dois vereditos da perícia do Cache (num deles o atacante viu o alvo 3,6 s antes) | v6.3, raycast em [janela−3 s] → 👀 TRACK-VIU, 0 pts |
| L7 | Repetição de sinal na MESMA vítima não é padrão (a vítima pode ser previsível — um top-frag disparou o sinal de 3 atacantes diferentes). Escalada de score exige vítimas DISTINTAS. | Vereditos da perícia do Cache | v6.3, escadas de smoke/track/parede contam vítimas distintas |

## Lições de processo (para os workflows de perícia)

- Diagnóstico parcial engana: um "caso fortíssimo" virou refutação com
  confiança alta quando o cético mediu o giro da mira. Nunca reportar
  suspeito ao usuário antes do veredito adversarial.
- Vereditos: só para jogadores MÉDIO+; modelo opus, esforço médio (config do
  autor — velocidade > acurácia nessa fase).
- Duração de track "2,25 s" repetida é artefato do teto da janela (144 ticks),
  não um padrão.
- Assinatura de mira humana medida 2x (30 jogadores): dp de reação 400–880 ms,
  jerk z entre −1,7 e +2,2, zero spins. Triggerbot teria dp de dezenas de ms.
  Esses números são a baseline de referência.
- **Limite de precisão angular:** só interpretar diferenças de mira MAIORES
  que o tamanho angular da hitbox na distância do lance (cabeça ≈ 9 u →
  ~0,28° a 35 m). A "checagem de altura de cabeça" (em pé vs agachado) só
  discrimina em range curto — a longa distância é ruído. Erro cometido e
  corrigido por ground truth do autor (demo confirma `ducked=False` via
  parse_ticks; o estado de agachamento é sempre verificável, não presuma).
- **Protocolo de evidência de ESP:** "mira na parede" não é um sinal por si
  só. Para marcar um candidato, registrar alvo oculto, geometria/smoke,
  movimento angular do alvo e da mira, duração, última visão e todo sinal
  legítimo disponível (tiro, granada, teammate/radar quando extraível). Sem
  poder excluir explicação legítima, classificar como ambíguo e `peso=0`.
- **Ordem de implantação:** extração → anotação com `peso=0` → revisão em
  primeira pessoa → calibração com casos legítimos e suspeitos → regra de
  score. Nunca introduzir limiar e peso no mesmo passo; todo sinal novo deve
  sobreviver aos falsos positivos já documentados.
- **Limite da demo:** ausência de evidência de call/áudio não é evidência de
  ausência. Voz, atenção ao radar, configuração de som e intenção do jogador
  não são observáveis de forma confiável; o relatório deve declarar essa
  incerteza quando ela for relevante ao lance.
- **ESP sem aim assist:** mira humana (erros, overshoot, reação e mortes
  normais) não elimina a hipótese de ESP. Nesse perfil, procurar a vantagem
  antes do tiro: ângulo escolhido, rota segura, entrada sem risco, timing de
  avanço e seleção de duelo. A análise não deve exigir lock-on ou flick para
  abrir um candidato observacional.
- **Informação negativa e sincronismo de decisão:** ignorar repetidamente
  ângulos vazios, checar os ocupados ou mudar de plano logo após uma mudança
  invisível do inimigo só vale como padrão quando não há explicação legítima
  registrada. Uma decisão que funcionou é resultado; evidência é a correlação
  repetida entre decisão e posição oculta, com contraprovas aplicadas.

## Pendentes (descobertos, ainda não codificados)

- **Spotted por teammate:** vítima marcada no radar por um companheiro do
  atacante = info legítima (usado nos vereditos, mas exige extrair o estado
  "spotted" da demo — pesquisar suporte no demoparser2).
- **Audibilidade com atenuação:** passo audível tem alcance (~1100 unidades) e
  oclusão; o modelo atual usa só velocidade >110 u/s.
- **Reação pós-LOS:** medir o tempo entre a linha de visão abrir e o tiro
  (≥200 ms = humano) para kills que terminam wall-tracks.
- **Assinatura da mira no pipeline:** integrar o protótipo validado (dp de
  reação, jerk, spinbot) como sinais nativos do analisar.py.
- **Correlação de tracking (forense):** corr entre Δdireção-ao-alvo e Δmira
  distingue wallhack de tracking (corr→+1) de prefire/posição (corr~0). Alvo
  PARADO derrota o teste — precisa de alvo em movimento. Validado no caso
  Dust2: 7 lances suspeitos, zero tracking.
- **Timing de gatilho em alvo cruzando smoke:** disparar a ±40 ms do instante
  em que a cabeça invisível cruza a mira parada é mensurável (série de erro
  mira→cabeça); repetido, indica ESP de posição — o cheat que a correlação
  não pega. **Status: codificado como anotação sem peso (v6.4)** — smoke kill
  precisa + alvo ≥150 u/s + mira girando ≤3° no último segundo = "GATILHO
  CIRÚRGICO". Primeiros dados (Dust2): suspeito principal 3x, outros dois
  jogadores 1x cada. Ganha peso no score quando houver baseline de mais
  partidas (regra do projeto: sinal novo observa antes de pontuar).
