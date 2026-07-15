# -*- coding: utf-8 -*-
r"""
Linha do tempo de decisões — D4.1 do ROADMAP
============================================
Um ESP "legit" pode ter mira 100% humana: a vantagem aparece ANTES do tiro,
nas decisões — que ângulo segurar, quando avançar, quando recuar. Este módulo
extrai da varredura contínua (~125 ms) os pontos de DECISÃO observáveis do
movimento de cada jogador e os registra com o contexto que D4.2–D4.4 vão
consumir: a informação observável no instante e a posição real dos inimigos.

Tipos de decisão registrados nesta primeira versão:

  * ``reversao``            — o jogador vinha andando numa direção e passa a
                              andar na (quase) oposta: recuo, rotação, desistir
                              de uma entrada.
  * ``avanco_apos_parada``  — ficou parado ≥3 s (segurando posição) e decide
                              sair. O "quando" desse avanço é a matéria-prima
                              do D4.4 (janelas seguras invisíveis).
  * ``utility``             — jogou granada (HE/flash/smoke/molotov/decoy).

Disciplina (a mesma da Fase D inteira): isto é REGISTRO, não sinal. Nenhuma
decisão pontua, nenhum limiar acusa; o dataset existe para que a sincronia
decisão↔informação-oculta seja medida sobre MUITAS situações, com contraprovas
(D4.8/D4.9), antes de qualquer peso. Voz/Discord seguem como incerteza
declarada — uma decisão "sem fonte observável" pode ter vindo de um call.

Aproximações declaradas:
  * passo da varredura ~125 ms: micro-jiggle e strafes de duelo não são
    "decisões" aqui (e não devem ser — o filtro de velocidade/duração corta).
  * heading do MOVIMENTO, não da mira: onde o jogador vai, não onde olha.
  * granada registrada no tick do arremesso; lineup/intenção não são inferidos.
"""

import os
import json
import math

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_DECISOES = os.path.join(PASTA, "dados", "decisoes.jsonl")

SCHEMA_DECISAO = "d4.1"

VEL_MOVENDO = 60.0        # u/s: abaixo disso não é deslocamento intencional
VEL_PARADO = 30.0         # u/s: acima disso não conta como "segurando posição"
JANELA_LADO = 8           # amostras (~1 s) de movimento antes/depois p/ heading
MIN_LADO_MOVENDO = 6      # amostras em movimento exigidas em cada lado
REVERSAO_MIN_DEG = 120.0  # mudança de heading que caracteriza reversão
MIN_PARADO_AMOSTRAS = 24  # ~3 s parado antes de um "avanço após parada"
DEDUP_AMOSTRAS = 16       # ~2 s: reversões mais próximas que isso são uma só


def _norm180(a):
    while a > 180.0:
        a -= 360.0
    while a < -180.0:
        a += 360.0
    return a


def _media_angular(graus):
    """Média de ângulos por soma vetorial (não quebra no wrap 359°→0°)."""
    sx = sum(math.cos(math.radians(g)) for g in graus)
    sy = sum(math.sin(math.radians(g)) for g in graus)
    if sx == 0 and sy == 0:
        return None
    return math.degrees(math.atan2(sy, sx))


def _passos(seg, passo_s):
    """Velocidade (u/s) e heading (graus) de cada passo de um segmento.

    `seg` = [(tick, x, y, z), ...] contíguo (jogador vivo, sem buracos).
    Retorna listas paralelas de tamanho len(seg)-1.
    """
    vels, heads = [], []
    for i in range(1, len(seg)):
        dx = seg[i][1] - seg[i - 1][1]
        dy = seg[i][2] - seg[i - 1][2]
        d = math.hypot(dx, dy)
        vels.append(d / passo_s)
        heads.append(math.degrees(math.atan2(dy, dx)) if d > 0.5 else None)
    return vels, heads


def detectar_reversoes(seg, passo_s=0.125):
    """Pontos onde o heading do MOVIMENTO virou ≥ REVERSAO_MIN_DEG.

    Compara a média angular do ~1 s de movimento anterior com a do ~1 s
    seguinte; exige MIN_LADO_MOVENDO amostras em movimento de cada lado
    (parada no meio-tempo é assunto do detector de avanço, não deste).
    Retorna [(tick, giro_deg, heading_antes, heading_depois), ...].
    """
    if len(seg) < 2 * JANELA_LADO + 1:
        return []
    vels, heads = _passos(seg, passo_s)
    out = []
    ultimo = -DEDUP_AMOSTRAS
    for i in range(JANELA_LADO, len(vels) - JANELA_LADO):
        antes = [heads[j] for j in range(i - JANELA_LADO, i)
                 if vels[j] >= VEL_MOVENDO and heads[j] is not None]
        depois = [heads[j] for j in range(i, i + JANELA_LADO)
                  if vels[j] >= VEL_MOVENDO and heads[j] is not None]
        if len(antes) < MIN_LADO_MOVENDO or len(depois) < MIN_LADO_MOVENDO:
            continue
        h_a, h_d = _media_angular(antes), _media_angular(depois)
        if h_a is None or h_d is None:
            continue
        giro = abs(_norm180(h_d - h_a))
        if giro >= REVERSAO_MIN_DEG and i - ultimo >= DEDUP_AMOSTRAS:
            out.append((seg[i][0], giro, h_a, h_d))
            ultimo = i
    return out


def detectar_avancos(seg, passo_s=0.125):
    """Pontos onde o jogador SAI de uma parada longa (≥3 s segurando posição).

    Exige que o ~1 s seguinte seja majoritariamente movimento real (não um
    ajuste de meio passo). Retorna [(tick, parado_s, heading_saida), ...].
    """
    if len(seg) < 2:
        return []
    vels, heads = _passos(seg, passo_s)
    out = []
    parado = 0
    i = 0
    while i < len(vels):
        if vels[i] <= VEL_PARADO:
            parado += 1
            i += 1
            continue
        if parado >= MIN_PARADO_AMOSTRAS and i + JANELA_LADO <= len(vels):
            movendo = [j for j in range(i, i + JANELA_LADO)
                       if vels[j] >= VEL_MOVENDO and heads[j] is not None]
            if len(movendo) >= MIN_LADO_MOVENDO:
                h = _media_angular([heads[j] for j in movendo])
                out.append((seg[i][0], parado * passo_s, h))
        parado = 0
        i += 1
    return out


# ---------------------------------------------------------------------------
# Persistência (JSONL, dedup por demo)
# ---------------------------------------------------------------------------

def demos_registradas(caminho=ARQ_DECISOES):
    """Hashes de demo que já têm linha do tempo gravada (reanálise não duplica)."""
    hashes = set()
    if not os.path.exists(caminho):
        return hashes
    with open(caminho, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                hashes.add(json.loads(linha)["demo_hash"])
            except (ValueError, KeyError):
                continue
    return hashes


def salvar_decisoes(registros, caminho=ARQ_DECISOES):
    """Anexa os registros de decisão ao JSONL. Retorna o nº gravado."""
    if not registros:
        return 0
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "a", encoding="utf-8") as f:
        for r in registros:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(registros)
