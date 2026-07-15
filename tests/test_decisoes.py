# -*- coding: utf-8 -*-
"""Testes da linha do tempo de decisões (decisoes.py, D4.1 / v6.18).

Fixam o contrato da segmentação: o que conta como reversão de rota e como
avanço após parada — e o que NÃO conta (jiggle, curva suave, ajuste curto).
"""

import os
import sys
import json
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import decisoes

PASSO = 0.125          # s por amostra (varredura padrão)
V = 250.0 * PASSO      # deslocamento por amostra correndo (250 u/s)


def caminho(*trechos):
    """Monta um segmento [(tick, x, y, z)] a partir de trechos (dx, dy, n)."""
    seg = [(0, 0.0, 0.0, 0.0)]
    t = 0
    for dx, dy, n in trechos:
        for _ in range(n):
            t += 8
            ult = seg[-1]
            seg.append((t, ult[1] + dx, ult[2] + dy, 0.0))
    return seg


class TestReversoes(unittest.TestCase):
    def test_linha_reta_nao_tem_reversao(self):
        seg = caminho((V, 0, 40))
        self.assertEqual(decisoes.detectar_reversoes(seg, PASSO), [])

    def test_meia_volta_e_reversao(self):
        seg = caminho((V, 0, 16), (-V, 0, 16))
        revs = decisoes.detectar_reversoes(seg, PASSO)
        self.assertEqual(len(revs), 1)
        self.assertGreaterEqual(revs[0][1], 170.0)  # giro ~180°

    def test_curva_de_90_nao_e_reversao(self):
        seg = caminho((V, 0, 16), (0, V, 16))
        self.assertEqual(decisoes.detectar_reversoes(seg, PASSO), [])

    def test_parado_nao_tem_reversao(self):
        seg = caminho((1.0, 0, 40))  # 8 u/s: abaixo de VEL_MOVENDO
        self.assertEqual(decisoes.detectar_reversoes(seg, PASSO), [])

    def test_zigzag_rapido_deduplica(self):
        # vai-e-volta a cada ~1,25 s: reversões atrás da janela de dedup
        seg = caminho((V, 0, 10), (-V, 0, 10), (V, 0, 10), (-V, 0, 10))
        revs = decisoes.detectar_reversoes(seg, PASSO)
        self.assertLessEqual(len(revs), 2)
        self.assertGreaterEqual(len(revs), 1)


class TestAvancos(unittest.TestCase):
    def test_parada_longa_e_saida(self):
        seg = caminho((0, 0, 30), (V, 0, 10))  # ~3,75 s parado, depois corre
        avs = decisoes.detectar_avancos(seg, PASSO)
        self.assertEqual(len(avs), 1)
        self.assertGreaterEqual(avs[0][1], 3.0)   # parado_s
        self.assertAlmostEqual(avs[0][2] % 360, 0.0, delta=1.0)  # heading +x

    def test_parada_curta_nao_conta(self):
        seg = caminho((V, 0, 8), (0, 0, 10), (V, 0, 10))  # ~1,25 s parado
        self.assertEqual(decisoes.detectar_avancos(seg, PASSO), [])

    def test_ajuste_de_um_passo_nao_conta(self):
        # parado 4 s, um único passo, parado de novo: não é avanço
        seg = caminho((0, 0, 32), (V, 0, 1), (0, 0, 16))
        self.assertEqual(decisoes.detectar_avancos(seg, PASSO), [])

    def test_andando_direto_nao_conta(self):
        seg = caminho((V, 0, 40))
        self.assertEqual(decisoes.detectar_avancos(seg, PASSO), [])


class TestPersistencia(unittest.TestCase):
    def setUp(self):
        fd, self.arq = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        os.unlink(self.arq)

    def tearDown(self):
        if os.path.exists(self.arq):
            os.unlink(self.arq)

    def test_salvar_e_dedup_por_demo(self):
        regs = [{"demo_hash": "h1", "tipo": "reversao"},
                {"demo_hash": "h1", "tipo": "utility"}]
        self.assertEqual(decisoes.salvar_decisoes(regs, self.arq), 2)
        self.assertEqual(decisoes.demos_registradas(self.arq), {"h1"})
        with open(self.arq, encoding="utf-8") as f:
            self.assertEqual(len([l for l in f if l.strip()]), 2)

    def test_arquivo_inexistente_e_vazio(self):
        self.assertEqual(decisoes.demos_registradas(self.arq), set())
        self.assertEqual(decisoes.salvar_decisoes([], self.arq), 0)
        self.assertFalse(os.path.exists(self.arq))

    def test_linha_corrompida_nao_quebra(self):
        with open(self.arq, "w", encoding="utf-8") as f:
            f.write("{nao é json}\n")
            f.write(json.dumps({"demo_hash": "h2"}) + "\n")
        self.assertEqual(decisoes.demos_registradas(self.arq), {"h2"})


if __name__ == "__main__":
    unittest.main()
