# -*- coding: utf-8 -*-
"""Testes da rotulagem humana (rotular.py — Fase D0.3).

Invariante central do protocolo: revisões são APPEND-ONLY — uma nova revisão
nunca apaga a anterior (o histórico é preservado para adjudicação).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rotular


def _ep(eid="abc123"):
    return {"episode_id": eid, "rotulo_humano": None}


class TestRotular(unittest.TestCase):
    def test_grava_revisao(self):
        eps = [_ep()]
        rotular.rotular(eps, "abc123", "evidencia_forte",
                        tipo_evidencia="pré-mira informada",
                        confianca="media", nota="teste", revisor="autor",
                        data="2026-07-15")
        revs = eps[0]["rotulo_humano"]["revisoes"]
        self.assertEqual(len(revs), 1)
        self.assertEqual(revs[0]["conclusao"], "evidencia_forte")
        self.assertEqual(revs[0]["revisor"], "autor")

    def test_append_only(self):
        eps = [_ep()]
        rotular.rotular(eps, "abc123", "evidencia_forte", data="2026-07-15")
        rotular.rotular(eps, "abc123", "legitimo_explicado", data="2026-07-16")
        revs = eps[0]["rotulo_humano"]["revisoes"]
        # a segunda revisão NÃO sobrescreve a primeira
        self.assertEqual([r["conclusao"] for r in revs],
                         ["evidencia_forte", "legitimo_explicado"])

    def test_conclusao_invalida(self):
        with self.assertRaises(ValueError):
            rotular.rotular([_ep()], "abc123", "cheater_confirmado")

    def test_episodio_inexistente(self):
        with self.assertRaises(KeyError):
            rotular.rotular([_ep()], "nao_existe", "evidencia_forte")


if __name__ == "__main__":
    unittest.main()
