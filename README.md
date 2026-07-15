# CS2 Detector de Suspeitos 🔍

Analisa **demos de CS2** (Premier/MM) e gera um relatório visual com score de
suspeita de cheat (0–100) por jogador — combinando estatísticas de eventos com
**análise da mira tick a tick** (64 medições/segundo) e **geometria real do
mapa** (raycast de linha de visão).

> **Filosofia:** o score aponta, o olho humano confirma. Estatística sugere,
> não prova — cada momento suspeito vem com o round e o comando
> `demo_gototick` pra você assistir antes de denunciar. Melhor deixar passar
> um suspeito do que acusar um inocente.

## O que ele detecta

| Sinal | Como funciona | Força |
|---|---|---|
| ⚡ Flick sobre-humano | Giro ≥35° em 125 ms parando na cabeça com ≤47 ms de mira no alvo | Muito forte |
| ⏱️ Reação inumana | Mira chega no alvo e mata em ≤31 ms (humano: 150–250 ms) | Forte |
| 🚨 Tracking através de parede | Mira SEGUINDO alvo em movimento com parede na linha de visão ≥70% do tempo (raycast na geometria do mapa) | Muito forte se repetido em vítimas diferentes |
| 🧲 Tracking pré-confronto | Mira acompanhando alvo em movimento por ≥1,5 s antes da kill | Média |
| 💨 Kill por smoke | Só pontua tiro preciso (≤4 tiros/2 s) a ≥7 m — spam de posição conhecida não conta | Forte se repetido |
| 🧱 Wallbang / 🫣 kill cego | Eventos da própria demo | Média / Forte |
| 🎯 Precisão anormal | % de tiros que acertam (típico 15–35%) e % na cabeça (típico 15–25%) | Média |

E o que ele **descarta de propósito** (anti-falso-positivo, lições em
[APRENDIZADOS.md](APRENDIZADOS.md)): segurar ângulo parado, vítima que atirou
ou jogou granada nos 5 s anteriores (🔊 posição revelada), atacante que viu o
alvo segundos antes (👀 última posição conhecida), spam através de smoke (🌫️)
e repetição de sinal na mesma vítima.

## Instalação (Windows)

1. [Python 3.12+](https://www.python.org/downloads/) (`winget install Python.Python.3.12`)
2. `pip install -r requirements.txt`
3. Geometria e radares dos mapas oficiais (uma vez só):
   ```
   awpy get tris
   awpy get maps
   ```
4. *(Opcional)* copie `config.example.json` para `config.json` e cole sua
   [chave de API da Steam](https://steamcommunity.com/dev/apikey) (grátis,
   domínio "localhost") — adiciona nível Steam e horas de CS2 aos relatórios.
   Sem chave, tudo funciona via perfis públicos.

## Uso

1. Baixe a demo no CS2: **Assistir → Suas Partidas → Baixar**
2. Dê dois cliques em **`ANALISAR-DEMO.bat`** — ele acha sozinho a demo mais
   recente nas suas bibliotecas Steam (ou arraste um `.dem` em cima do `.bat`)
3. O relatório abre no navegador: score por jogador, momentos suspeitos com
   `demo_gototick`, radar 2D de onde cada lance aconteceu, contexto da conta
   Steam e links pra csstats.gg/Leetify

Ou via terminal: `python analisar.py caminho\para\partida.dem`

### Rastreador de bans (o loop de validação)

Rode **`CHECAR-BANS.bat`** de tempos em tempos: ele reconsulta na Steam todos
os jogadores que você já analisou e avisa quem tomou VAC/ban de jogo desde a
última checagem — dizendo inclusive se o detector tinha marcado a pessoa.
É a taxa de acerto do detector medida contra a realidade.

## Como denunciar (Premier)

1. **Assista primeiro**: abra a demo, console (`'`), cole o `demo_gototick`
   do relatório, espectate na visão do suspeito com X-ray
2. **No jogo**: Tab → jogador → Denunciar (alimenta o VACnet)
3. **Na Steam**: perfil do jogador → Mais → Denunciar violação

## Limites e ética

- **Nenhum detector por demo é infalível.** Demos gravam a 64 ticks/s com
  interpolação; lances isolados enganam. O score pesa repetição e sinais
  independentes se corroborando.
- A ferramenta lê **apenas o replay público das suas próprias partidas**.
  Não acessa a máquina de ninguém, não roda em tempo real e não automatiza
  denúncias — o veredito final é sempre seu, com os próprios olhos.
- Publique resultados com responsabilidade: score não é prova, e expor
  jogadores publicamente com base em estatística é injusto com inocentes.

## Documentos do projeto

- [ROADMAP.md](ROADMAP.md) — histórico de versões e o que vem por aí
- [APRENDIZADOS.md](APRENDIZADOS.md) — base de conhecimento de calibração:
  cada falso positivo descoberto virou regra codificada

## Créditos

Construído sobre [demoparser2](https://github.com/LaihoE/demoparser) (parsing
de demos) e [awpy](https://github.com/pnxenopoulos/awpy) (geometria e radares
dos mapas). Desenvolvido em par com Claude Code.

Licença: [MIT](LICENSE)
