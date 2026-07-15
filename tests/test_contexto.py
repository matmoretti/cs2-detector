# -*- coding: utf-8 -*-
"""Testes do contrato de episódio forense (contexto.py — Fase D0).

Garantem as invariantes que o ROADMAP/ARQUITETURA-ML exigem:
  * episode_id determinístico (permite dedup no dataset);
  * fonte indisponível vira 'desconhecido' COM razão — nunca 'nao';
  * o registro é auto-explicável (todas as seções presentes).
"""

import os
import sys
import json
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import contexto


def _mom(tipo="TRACK", **ctx_extra):
    ctx = {
        "mudanca_angular_alvo_deg": 40.0, "duracao_s": 1.6,
        "velocidade_alvo_us": 210.0, "viu_antes": False,
        "barulho_recente": False, "oclusao_frac": 0.85,
        "distancia_m": 20.0, "distancia_us": 1500.0, "classe": "candidato",
    }
    ctx.update(ctx_extra)
    return {
        "tipo": tipo, "desc": "mira acompanhou o alvo...", "round": 5,
        "tick": 10000, "vitima": "Vitima", "arma": "ak47", "peso": 4,
        "a_sid": "76561190000000001", "v_sid": "76561190000000002", "ctx": ctx,
    }


_META = {
    "demo_hash": "abc123", "arquivo": "partida.dem", "mapa": "de_mirage",
    "tickrate": 64, "versao_parser": "demoparser2 0.34", "tem_geometria": True,
}


class TestHelpersValorRazao(unittest.TestCase):
    def test_conhecido(self):
        self.assertEqual(contexto.conhecido(3.2), {"valor": 3.2, "razao": None})

    def test_desconhecido_tem_razao(self):
        d = contexto.desconhecido("sem geometria")
        self.assertEqual(d["valor"], "desconhecido")
        self.assertTrue(d["razao"])

    def test_tri_estado(self):
        self.assertEqual(contexto.tri_estado(True, "r")["valor"], "sim")
        self.assertEqual(contexto.tri_estado(False, "r")["valor"], "nao")
        self.assertEqual(contexto.tri_estado(None, "r")["valor"], "desconhecido")


class TestEpisodeId(unittest.TestCase):
    def test_deterministico(self):
        a = contexto.episode_id("h", 100, "1", "2", "TRACK")
        b = contexto.episode_id("h", 100, "1", "2", "TRACK")
        self.assertEqual(a, b)

    def test_muda_com_o_tick(self):
        a = contexto.episode_id("h", 100, "1", "2", "TRACK")
        b = contexto.episode_id("h", 101, "1", "2", "TRACK")
        self.assertNotEqual(a, b)

    def test_tamanho_fixo(self):
        self.assertEqual(len(contexto.episode_id("h", 1, "1", "2", "X")), 16)


class TestPseudonimizar(unittest.TestCase):
    def setUp(self):
        self._orig = contexto._SALT
        contexto._SALT = b"salt-de-teste-fixo"

    def tearDown(self):
        contexto._SALT = self._orig

    def test_estavel(self):
        self.assertEqual(contexto.pseudonimizar("777"),
                         contexto.pseudonimizar("777"))

    def test_distingue_jogadores(self):
        self.assertNotEqual(contexto.pseudonimizar("777"),
                            contexto.pseudonimizar("888"))

    def test_nao_vaza_sid(self):
        p = contexto.pseudonimizar("76561190000000001")
        self.assertNotIn("76561190000000001", p)
        self.assertEqual(len(p), 16)


class TestMontarEpisodio(unittest.TestCase):
    def setUp(self):
        self._orig = contexto._SALT
        contexto._SALT = b"salt-de-teste-fixo"

    def tearDown(self):
        contexto._SALT = self._orig

    def test_secoes_presentes(self):
        ep = contexto.montar_episodio(_mom(), _META)
        for secao in ("identidade", "tempo", "versoes", "contexto",
                      "geometria", "mira", "contraprovas", "saida_regra"):
            self.assertIn(secao, ep)
        self.assertEqual(ep["schema_versao"], contexto.SCHEMA_VERSAO)
        self.assertIsNone(ep["rotulo_humano"])

    def test_contraprovas_nao_extraiveis_sao_desconhecidas_com_razao(self):
        ep = contexto.montar_episodio(_mom(), _META)
        for chave in ("radar_spotted", "call_teammate"):
            cp = ep["contraprovas"][chave]
            self.assertEqual(cp["valor"], "desconhecido")
            self.assertTrue(cp["razao"], f"{chave} sem razão de indisponibilidade")

    def test_viu_antes_falso_vira_nao(self):
        ep = contexto.montar_episodio(_mom(viu_antes=False), _META)
        self.assertEqual(ep["contraprovas"]["visao_recente"]["valor"], "nao")

    def test_sem_geometria_visao_recente_desconhecida(self):
        meta = {**_META, "tem_geometria": False}
        # sem viu_antes no ctx e sem geometria: não pode afirmar 'nao'
        mom = _mom()
        mom["ctx"].pop("viu_antes")
        ep = contexto.montar_episodio(mom, meta)
        self.assertEqual(ep["contraprovas"]["visao_recente"]["valor"],
                         "desconhecido")
        self.assertEqual(ep["versoes"]["geometria"], "indisponivel")

    def test_identidade_pseudonimizada(self):
        ep = contexto.montar_episodio(_mom(), _META)
        self.assertNotEqual(ep["identidade"]["atacante_id"], "76561190000000001")
        self.assertEqual(ep["identidade"]["candidate_source"], "TRACK")

    def test_geometria_oclusao_preservada(self):
        ep = contexto.montar_episodio(_mom(oclusao_frac=0.9), _META)
        self.assertAlmostEqual(ep["geometria"]["oclusao_frac"]["valor"], 0.9)


class TestSalvarEpisodios(unittest.TestCase):
    def setUp(self):
        self._orig = contexto._SALT
        contexto._SALT = b"salt-de-teste-fixo"

    def tearDown(self):
        contexto._SALT = self._orig

    def test_append_e_dedup(self):
        ep = contexto.montar_episodio(_mom(), _META)
        with tempfile.TemporaryDirectory() as d:
            caminho = os.path.join(d, "episodios.jsonl")
            n1, i1 = contexto.salvar_episodios([ep], caminho)
            n2, i2 = contexto.salvar_episodios([ep], caminho)
            self.assertEqual((n1, i1), (1, 0))
            self.assertEqual((n2, i2), (0, 1))  # reanálise não duplica
            with open(caminho, encoding="utf-8") as f:
                linhas = [l for l in f if l.strip()]
            self.assertEqual(len(linhas), 1)
            json.loads(linhas[0])  # continua sendo JSON válido

    def test_dois_episodios_distintos(self):
        e1 = contexto.montar_episodio(_mom(tipo="TRACK"), _META)
        e2 = contexto.montar_episodio(_mom(tipo="SMOKE"), _META)
        with tempfile.TemporaryDirectory() as d:
            caminho = os.path.join(d, "episodios.jsonl")
            n, i = contexto.salvar_episodios([e1, e2], caminho)
            self.assertEqual((n, i), (2, 0))


if __name__ == "__main__":
    unittest.main()
