# -*- coding: utf-8 -*-
"""Testes das funções puras de mira/pontuação do analisar.py.

Rode da raiz do projeto:  python -m unittest discover -s tests
(A primeira lição do detector — L3 — nasceu de um erro de medição de mira;
estes testes fixam a matemática que sustenta os vereditos.)
"""

import os
import sys
import math
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analisar import (norm180, giro_mira, desvio_mira, escada,
                      teammate_spotou, premira_informada, segundos_no_round)


class TestNorm180(unittest.TestCase):
    def test_zero(self):
        self.assertAlmostEqual(norm180(0.0), 0.0)

    def test_wrap_positivo(self):
        self.assertAlmostEqual(norm180(190.0), -170.0)

    def test_wrap_negativo(self):
        self.assertAlmostEqual(norm180(-190.0), 170.0)

    def test_volta_completa(self):
        self.assertAlmostEqual(norm180(360.0), 0.0)

    def test_meia_volta(self):
        # 180 e -180 são o mesmo ponto; a convenção aqui devolve -180
        self.assertAlmostEqual(abs(norm180(180.0)), 180.0)


class TestGiroMira(unittest.TestCase):
    def test_sem_giro(self):
        self.assertAlmostEqual(giro_mira(10.0, 5.0, 10.0, 5.0), 0.0)

    def test_giro_yaw_puro(self):
        # 90° de yaw com pitch 0 → giro de ~90°
        self.assertAlmostEqual(giro_mira(0.0, 0.0, 90.0, 0.0), 90.0, places=4)

    def test_giro_pitch_puro(self):
        self.assertAlmostEqual(giro_mira(0.0, 0.0, 0.0, 30.0), 30.0, places=4)

    def test_yaw_reto_vale_o_delta(self):
        # olhando reto (pitch 0), 40° de yaw dão ~40° de giro
        self.assertAlmostEqual(giro_mira(0.0, 0.0, 40.0, 0.0), 40.0, places=4)

    def test_yaw_encurta_com_pitch_alto(self):
        # giro_mira é uma APROXIMAÇÃO: escala o yaw por cos(pitch de destino),
        # então NÃO é simétrica. Com pitch constante 30°, o mesmo delta-yaw
        # pesa menos no eixo horizontal (cos 30° ≈ 0,866).
        g = giro_mira(0.0, 30.0, 40.0, 30.0)
        self.assertAlmostEqual(g, 40.0 * math.cos(math.radians(30.0)), places=3)


class TestDesvioMira(unittest.TestCase):
    def test_alinhado_de_frente(self):
        # atacante na origem olhando para +X (yaw=0), vítima 100u à frente
        desvio, dist = desvio_mira(0, 0, 0, 0.0, 0.0, 100, 0, 0)
        self.assertIsNotNone(desvio)
        self.assertLess(desvio, 1.0)
        self.assertGreater(dist, 90.0)

    def test_alvo_atras(self):
        # vítima atrás (mira 180° errada) → desvio grande
        desvio, _ = desvio_mira(0, 0, 0, 0.0, 0.0, -100, 0, 0)
        self.assertIsNotNone(desvio)
        self.assertGreater(desvio, 90.0)

    def test_vitima_em_cima_do_atacante(self):
        # dxy < 1 em todos os alvos → sem ângulo definido
        desvio, _ = desvio_mira(0, 0, 0, 0.0, 0.0, 0, 0, 0)
        self.assertIsNone(desvio)


class TestEscada(unittest.TestCase):
    def test_abaixo_do_primeiro_degrau(self):
        self.assertEqual(escada(0, [(1, 10), (2, 22)]), 0)

    def test_primeiro_degrau(self):
        self.assertEqual(escada(1, [(1, 10), (2, 22)]), 10)

    def test_degrau_intermediario(self):
        self.assertEqual(escada(2, [(1, 10), (2, 22), (3, 30)]), 22)

    def test_acima_do_ultimo_pega_o_maior(self):
        self.assertEqual(escada(9, [(1, 10), (2, 22)]), 22)

    def test_lista_vazia(self):
        self.assertEqual(escada(5, []), 0)


class TestTeammateSpotou(unittest.TestCase):
    """D1.1: exclusão de tracking quando a vítima estava no radar do time."""

    def setUp(self):
        # A=atacante (time 2), V=vítima (time 3),
        # B=teammate de A (time 2), C=teammate de V (time 3)
        self.team = {}
        for t in (100, 116, 132):
            self.team[(t, "A")] = 2
            self.team[(t, "B")] = 2
            self.team[(t, "V")] = 3
            self.team[(t, "C")] = 3

    def test_teammate_do_atacante_ve(self):
        spot = {(100, "V"): ["B"]}
        self.assertTrue(teammate_spotou(spot, self.team, "A", "V", 100, 132))

    def test_so_o_proprio_atacante_ve_nao_conta(self):
        # o atacante enxergar não é "info de radar do teammate"
        spot = {(100, "V"): ["A"]}
        self.assertFalse(teammate_spotou(spot, self.team, "A", "V", 100, 132))

    def test_alguem_do_time_da_vitima_ve_nao_conta(self):
        spot = {(100, "V"): ["C"]}
        self.assertFalse(teammate_spotou(spot, self.team, "A", "V", 100, 132))

    def test_ninguem_ve(self):
        spot = {(100, "V"): []}
        self.assertFalse(teammate_spotou(spot, self.team, "A", "V", 100, 132))

    def test_ve_em_qualquer_tick_da_janela(self):
        spot = {(132, "V"): ["B"]}  # só no último tick amostrado
        self.assertTrue(teammate_spotou(spot, self.team, "A", "V", 100, 132))

    def test_sem_dados_de_time_nao_afirma(self):
        spot = {(100, "V"): ["B"]}
        self.assertFalse(teammate_spotou(spot, {}, "A", "V", 100, 132))


class TestPremiraInformada(unittest.TestCase):
    """D4.5: promover mira parada a PRE-MIRA exige alvo oculto E zero fonte
    legítima de informação — e dado ausente nunca conta como 'não havia'."""

    def test_caso_mitocondria(self):
        # oclusão alta, sem visão prévia, sem barulho, sem spotted → promove
        self.assertTrue(premira_informada(0.9, False, False, False))

    def test_alvo_visivel_nao_promove(self):
        # mirar em alvo visível é jogo normal
        self.assertFalse(premira_informada(0.3, False, False, False))

    def test_sem_geometria_nao_promove(self):
        # oclusão desconhecida → não dá para afirmar que o alvo estava oculto
        self.assertFalse(premira_informada(None, False, False, False))

    def test_viu_antes_exclui(self):
        self.assertFalse(premira_informada(0.9, True, False, False))

    def test_barulho_exclui(self):
        self.assertFalse(premira_informada(0.9, False, True, False))

    def test_spotted_exclui(self):
        self.assertFalse(premira_informada(0.9, False, False, True))

    def test_visao_desconhecida_nao_promove(self):
        # 'desconhecido' nunca vira 'não' (contrato D0)
        self.assertFalse(premira_informada(0.9, None, False, False))

    def test_barulho_desconhecido_nao_promove(self):
        self.assertFalse(premira_informada(0.9, False, None, False))

    def test_limiar_de_oclusao(self):
        self.assertTrue(premira_informada(0.7, False, False, False))
        self.assertFalse(premira_informada(0.69, False, False, False))


class TestSegundosNoRound(unittest.TestCase):
    """Contexto de timing por episódio (não é regra — exclusão foi refutada
    pela 1ª revisão humana: confirmado aos 9,2 s, refutado aos 4,8 s)."""

    def test_sem_freeze_ends(self):
        self.assertIsNone(segundos_no_round([], 1000))

    def test_antes_do_primeiro_round(self):
        self.assertIsNone(segundos_no_round([5000], 4000))

    def test_meio_do_round(self):
        # 640 ticks após o freeze a 64 t/s = 10 s
        self.assertAlmostEqual(segundos_no_round([5000], 5640), 10.0)

    def test_usa_o_round_mais_recente(self):
        self.assertAlmostEqual(segundos_no_round([1000, 5000], 5064), 1.0)

    def test_tickrate_diferente(self):
        self.assertAlmostEqual(segundos_no_round([0], 128, tickrate=128), 1.0)


if __name__ == "__main__":
    unittest.main()
