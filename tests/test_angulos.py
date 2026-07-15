# -*- coding: utf-8 -*-
"""Testes do mapa de ângulos comuns (angulos.py, v6.16).

Fixam o contrato do baseline: o que conta como "ângulo segurado", o dedup por
demo, a exclusão do próprio jogador na consulta e a vizinhança (célula + setor
de yaw, incluindo o wrap 359°→0°).
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import angulos


def lk_de(amostras):
    """Monta o lookup (tick, sid) -> tupla do analisar.py a partir de uma
    lista (tick, sid, x, y, z, yaw, vivo, time)."""
    lk = {}
    for t, sid, x, y, z, yaw, vivo, time in amostras:
        lk[(t, sid)] = (x, y, z, yaw, 0.0, vivo, time)
    return lk


def segurando(sid, ticks, yaw=90.0, x=100.0, y=200.0, z=0.0):
    return [(t, sid, x, y, z, yaw, True, 2) for t in ticks]


class TestColetarRuns(unittest.TestCase):
    TICKS = list(range(0, 200, 8))  # varredura sintética (passo 8)

    def test_segurar_angulo_vira_uma_run(self):
        lk = lk_de(segurando("a", self.TICKS))
        runs = angulos.coletar_runs(lk, self.TICKS, {"a"})
        self.assertEqual(len(runs), 1)
        sid, x, y, z, yaw = runs[0]
        self.assertEqual(sid, "a")
        self.assertAlmostEqual(yaw, 90.0)

    def test_mira_girando_nao_e_run(self):
        # 12°/amostra > MAX_GIRO_AMOSTRA: nenhuma sequência estável
        lk = lk_de([(t, "a", 0, 0, 0, (i * 12.0) % 360, True, 2)
                    for i, t in enumerate(self.TICKS)])
        self.assertEqual(angulos.coletar_runs(lk, self.TICKS, {"a"}), [])

    def test_morto_ou_espectador_nao_conta(self):
        lk = lk_de([(t, "m", 0, 0, 0, 90.0, False, 2) for t in self.TICKS]
                   + [(t, "e", 0, 0, 0, 90.0, True, 1) for t in self.TICKS])
        self.assertEqual(angulos.coletar_runs(lk, self.TICKS, {"m", "e"}), [])

    def test_giro_no_meio_quebra_em_duas_runs(self):
        ticks = self.TICKS
        meio = len(ticks) // 2
        lk = lk_de(segurando("a", ticks[:meio], yaw=90.0)
                   + segurando("a", ticks[meio:], yaw=200.0))
        runs = angulos.coletar_runs(lk, ticks, {"a"})
        self.assertEqual(len(runs), 2)
        self.assertAlmostEqual(runs[0][4], 90.0)
        self.assertAlmostEqual(runs[1][4], 200.0)

    def test_run_curta_demais_nao_conta(self):
        ticks = self.TICKS[:angulos.MIN_AMOSTRAS - 1]
        lk = lk_de(segurando("a", ticks))
        self.assertEqual(angulos.coletar_runs(lk, ticks, {"a"}), [])

    def test_wrap_de_yaw_nao_quebra_run(self):
        # oscilar entre 359° e 1° é giro de 2°, não de 358°
        lk = lk_de([(t, "a", 0, 0, 0, 359.0 if i % 2 else 1.0, True, 2)
                    for i, t in enumerate(self.TICKS)])
        self.assertEqual(len(angulos.coletar_runs(lk, self.TICKS, {"a"})), 1)


class TestMapaAngulos(unittest.TestCase):
    def setUp(self):
        fd, self.arq = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.arq)
        self.m = angulos.MapaAngulos(caminho=self.arq)

    def tearDown(self):
        if os.path.exists(self.arq):
            os.unlink(self.arq)

    def test_ingerir_dedup_por_demo_hash(self):
        runs = [("a", 100, 200, 0, 90.0)]
        self.assertEqual(self.m.ingerir("de_dust2", "h1", runs, str), 1)
        self.assertEqual(self.m.ingerir("de_dust2", "h1", runs, str), 0)
        self.assertEqual(self.m.n_demos("de_dust2"), 1)

    def test_consultar_conta_jogadores_distintos_e_exclui_o_proprio(self):
        runs = [("a", 100, 200, 0, 90.0), ("a", 100, 200, 0, 90.0),
                ("b", 110, 210, 0, 92.0), ("c", 90, 190, 0, 88.0)]
        self.m.ingerir("de_dust2", "h1", runs, str)
        r = self.m.consultar("de_dust2", 100, 200, 0, 90.0, excluir="a")
        self.assertEqual(r["jogadores"], 2)       # b e c; as 2 runs de "a" fora
        self.assertEqual(r["ocorrencias"], 2)
        self.assertEqual(r["demos_baseline"], 1)

    def test_consultar_vizinhanca_de_setor_e_celula(self):
        # run a um setor de yaw e uma célula de distância: ainda conta
        self.m.ingerir("de_dust2", "h1",
                       [("b", 100 + angulos.CELULA_XY, 200, 0,
                         90.0 + angulos.SETOR_YAW)], str)
        r = self.m.consultar("de_dust2", 100, 200, 0, 90.0, excluir="a")
        self.assertEqual(r["jogadores"], 1)
        # a DUAS células/setores de distância: fora da vizinhança
        r2 = self.m.consultar(
            "de_dust2", 100 - 2 * angulos.CELULA_XY, 200, 0, 90.0,
            excluir="a")
        self.assertEqual(r2["jogadores"], 0)

    def test_consultar_wrap_de_yaw(self):
        # segurar a 358° e consultar a 2°: setores 23 e 0 são vizinhos
        self.m.ingerir("de_dust2", "h1", [("b", 100, 200, 0, 358.0)], str)
        r = self.m.consultar("de_dust2", 100, 200, 0, 2.0, excluir="a")
        self.assertEqual(r["jogadores"], 1)

    def test_andar_diferente_nao_conta(self):
        # mesmo x/y e yaw, mas 3 células de altura de distância (outro andar)
        self.m.ingerir("de_nuke", "h1",
                       [("b", 100, 200, 3 * angulos.CELULA_Z, 90.0)], str)
        r = self.m.consultar("de_nuke", 100, 200, 0, 90.0, excluir="a")
        self.assertEqual(r["jogadores"], 0)

    def test_persistencia_roundtrip(self):
        self.m.ingerir("de_dust2", "h1", [("b", 100, 200, 0, 90.0)], str)
        m2 = angulos.MapaAngulos(caminho=self.arq)
        r = m2.consultar("de_dust2", 100, 200, 0, 90.0, excluir="a")
        self.assertEqual(r["jogadores"], 1)
        self.assertEqual(m2.ingerir("de_dust2", "h1", [], str), 0)

    def test_mapas_sao_independentes(self):
        self.m.ingerir("de_dust2", "h1", [("b", 100, 200, 0, 90.0)], str)
        r = self.m.consultar("de_mirage", 100, 200, 0, 90.0, excluir="a")
        self.assertEqual(r["jogadores"], 0)
        self.assertEqual(r["demos_baseline"], 0)


if __name__ == "__main__":
    unittest.main()
