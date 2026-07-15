# -*- coding: utf-8 -*-
r"""
Mapa de ângulos comuns — pendência compartilhada de D2.3, D3.2 e D4.5
=====================================================================
"Pré-mirar um ângulo comum é jogada normal" (L3/APRENDIZADOS) — mas até aqui
"comum" era intuição. Este módulo materializa a medição: todo ângulo que
QUALQUER jogador da partida SEGURA (mira estável por ≥ ~0,75 s na varredura
contínua) vira um registro persistente por mapa. Com o baseline acumulado,
cada candidato (🎯 PRE-MIRA, 🔀 TROCA-OCULTA, wallbang) pode responder:
"quantos OUTROS jogadores seguram esse mesmo ângulo desse mesmo lugar?".

Princípios (mesma disciplina da Fase D):

  * anotação, não regra: o valor consultado vai para o episódio e para o
    desc do lance com peso 0 — nenhum limiar de "comum o suficiente" é
    escolhido aqui (isso é calibração, D5, com rótulos).
  * o próprio lobby da partida alimenta o baseline ANTES da consulta, então
    mesmo a primeira análise de um mapa tem os outros 9 jogadores como
    referência; demos seguintes só enriquecem.
  * dedup por hash da demo: reanalisar a mesma partida não infla contagens.
  * jogadores ficam pseudonimizados (mesmo salt do contexto.py) — contar
    JOGADORES DISTINTOS é o que interessa (L7: repetição só vale entre
    fontes distintas), e o dataset segue não-reversível fora desta máquina.

Aproximações declaradas (documentadas, não escondidas):
  * célula de posição de 128 u e setor de yaw de 15°: dois pontos próximos
    da mesma célula olhando o mesmo setor contam como "mesmo ângulo" mesmo
    que mirem coisas ligeiramente diferentes. Bom para piso de ruído, não
    para prova.
  * pitch é ignorado: ângulos comuns de CS são majoritariamente horizontais;
    um pixel-angle vertical raro não será separado do horizontal comum.
  * uma run longa (segurar 30 s) conta UMA ocorrência — o que importa é
    "alguém segura aqui", não por quanto tempo.
"""

import os
import json
import math

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ_ANGULOS = os.path.join(PASTA, "dados", "angulos_comuns.json")

CELULA_XY = 128.0      # lado da célula de posição no plano (unidades)
CELULA_Z = 128.0       # altura da célula (separa andares de Nuke/Vertigo)
SETOR_YAW = 15.0       # largura do setor de direção da mira (graus)
MIN_AMOSTRAS = 6       # ~0,75 s de varredura (passo ~125 ms) segurando
MAX_GIRO_AMOSTRA = 5.0  # °/amostra acima disso a mira está girando, não segurando


def _norm180(a):
    while a > 180.0:
        a -= 360.0
    while a < -180.0:
        a += 360.0
    return a


def bucket(x, y, z, yaw):
    """Chave discreta (célula de posição + setor de yaw) de um ângulo segurado."""
    cx = math.floor(x / CELULA_XY)
    cy = math.floor(y / CELULA_XY)
    cz = math.floor(z / CELULA_Z)
    setor = int((yaw % 360.0) // SETOR_YAW) % int(360 / SETOR_YAW)
    return f"{cx}:{cy}:{cz}:{setor}"


def coletar_runs(lk, ticks, sids):
    """Extrai os ângulos SEGURADOS por cada jogador na varredura contínua.

    `lk` é o lookup (tick, sid) -> (x, y, z, yaw, pitch, vivo, time) do
    analisar.py; `ticks` são os ticks da varredura (passo ~125 ms). Uma run é
    uma sequência de ≥ MIN_AMOSTRAS amostras consecutivas com o jogador vivo
    e |Δyaw| ≤ MAX_GIRO_AMOSTRA entre amostras. Retorna uma lista de tuplas
    (sid, x, y, z, yaw) — uma por run, na amostra do MEIO (representativa da
    posição/direção seguradas).
    """
    runs = []
    for sid in sorted(sids):
        seq = []          # amostras (x, y, z, yaw) da run corrente
        yaw_ant = None
        for t in ticks:
            p = lk.get((t, sid))
            ok = p is not None and p[5] and p[6] in (2, 3)
            if ok and (yaw_ant is None
                       or abs(_norm180(p[3] - yaw_ant)) <= MAX_GIRO_AMOSTRA):
                seq.append((p[0], p[1], p[2], p[3]))
            else:
                if len(seq) >= MIN_AMOSTRAS:
                    x, y, z, yaw = seq[len(seq) // 2]
                    runs.append((sid, x, y, z, yaw))
                seq = [(p[0], p[1], p[2], p[3])] if ok else []
            yaw_ant = p[3] if ok else None
        if len(seq) >= MIN_AMOSTRAS:
            x, y, z, yaw = seq[len(seq) // 2]
            runs.append((sid, x, y, z, yaw))
    return runs


class MapaAngulos:
    """Baseline persistente de ângulos segurados, por mapa do CS2.

    Formato em disco (dados/angulos_comuns.json):
        {mapa: {"demos": [hash, ...],
                "buckets": {chave: {pseudo: n_ocorrencias, ...}}}}
    """

    def __init__(self, caminho=ARQ_ANGULOS):
        self.caminho = caminho
        self.dados = {}
        if os.path.exists(caminho):
            try:
                with open(caminho, encoding="utf-8") as f:
                    self.dados = json.load(f)
            except (OSError, ValueError):
                self.dados = {}

    def _mapa(self, mapa):
        return self.dados.setdefault(str(mapa),
                                     {"demos": [], "buckets": {}})

    def n_demos(self, mapa):
        return len(self._mapa(mapa)["demos"])

    def ingerir(self, mapa, demo_hash, runs, pseudonimizar):
        """Alimenta o baseline com as runs de uma demo (dedup por hash).

        Retorna o nº de runs ingeridas (0 se a demo já estava no baseline).
        """
        m = self._mapa(mapa)
        if demo_hash in m["demos"]:
            return 0
        m["demos"].append(demo_hash)
        pseudo_de = {}
        for sid, x, y, z, yaw in runs:
            b = m["buckets"].setdefault(bucket(x, y, z, yaw), {})
            if sid not in pseudo_de:
                pseudo_de[sid] = pseudonimizar(sid)
            b[pseudo_de[sid]] = b.get(pseudo_de[sid], 0) + 1
        self.salvar()
        return len(runs)

    def consultar(self, mapa, x, y, z, yaw, excluir=None):
        """Quantos OUTROS jogadores seguram este mesmo ângulo no baseline?

        Vizinhança: células adjacentes (3x3x3) e setores de yaw ±1 — segurar
        praticamente o mesmo ângulo de um passo ao lado conta. `excluir` é o
        pseudônimo do próprio jogador consultado (as runs dele não devem
        atestar que o ângulo dele é comum).

        Retorna {"jogadores": n_distintos, "ocorrencias": total,
                 "demos_baseline": nº de demos que alimentaram este mapa}.
        """
        m = self._mapa(mapa)
        cx = math.floor(x / CELULA_XY)
        cy = math.floor(y / CELULA_XY)
        cz = math.floor(z / CELULA_Z)
        n_setores = int(360 / SETOR_YAW)
        setor = int((yaw % 360.0) // SETOR_YAW) % n_setores
        jogadores = set()
        ocorrencias = 0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for ds in (-1, 0, 1):
                        chave = (f"{cx + dx}:{cy + dy}:{cz + dz}:"
                                 f"{(setor + ds) % n_setores}")
                        b = m["buckets"].get(chave)
                        if not b:
                            continue
                        for pseudo, n in b.items():
                            if pseudo == excluir:
                                continue
                            jogadores.add(pseudo)
                            ocorrencias += n
        return {"jogadores": len(jogadores), "ocorrencias": ocorrencias,
                "demos_baseline": len(m["demos"])}

    def salvar(self):
        os.makedirs(os.path.dirname(self.caminho), exist_ok=True)
        with open(self.caminho, "w", encoding="utf-8") as f:
            json.dump(self.dados, f, ensure_ascii=False)
