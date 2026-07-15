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
