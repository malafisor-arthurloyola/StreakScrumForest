"""Retro da sprint (Defesa do Canteiro) ao vivo.
Regras que os testes guardam: a retro e no ultimo dia letivo de cada sprint (06/11 e 19/11, porque 20/11 e
feriado); quem comeca fica com o telao; so o telao grava o estado; as pessoas mandam acoes validadas;
outro aparelho so assume o telao quando ele parou (ou se for o administrador)."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "retro.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402

DB = str(appmod.DB_PATH)
REMOTO = {"environ_overrides": {"REMOTE_ADDR": "192.168.0.23"}, "base_url": "http://192.168.0.10:5000"}
FETCH = {"X-Requested-With": "fetch"}


class _DiaDeRetro(date):
    @classmethod
    def today(cls):
        return date(2026, 11, 6)


class _DiaComum(date):
    @classmethod
    def today(cls):
        return date(2026, 11, 4)


class TestDiasDeRetro(unittest.TestCase):
    def test_ultimo_dia_letivo_de_cada_sprint(self):
        sprints = [{"n": 1, "inicio": "2026-10-12", "fim": "2026-10-23"},
                   {"n": 2, "inicio": "2026-10-26", "fim": "2026-11-06"},
                   {"n": 3, "inicio": "2026-11-09", "fim": "2026-11-20"}]
        letivos = ["2026-10-22", "2026-10-23", "2026-11-05", "2026-11-06", "2026-11-18", "2026-11-19"]
        self.assertEqual(game.dias_de_retro(sprints, letivos),
                         {"2026-10-23": 1, "2026-11-06": 2, "2026-11-19": 3})

    def test_sprint_sem_dia_letivo_nao_tem_retro(self):
        self.assertEqual(game.dias_de_retro([{"n": 1, "inicio": "2026-12-21", "fim": "2026-12-31"}], ["2026-12-18"]), {})

    def test_calendario_padrao_tem_06_e_19_de_novembro(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        with appmod.app.app_context():
            dias = appmod._dias_de_retro(appmod.get_db())
        self.assertIn("2026-11-06", dias)
        self.assertIn("2026-11-19", dias)
        self.assertNotIn("2026-11-20", dias)


class TestAcaoValida(unittest.TestCase):
    def test_normaliza_e_recusa(self):
        v = appmod._acao_retro_valida
        self.assertEqual(v("problema", {"txt": "  muita   reunião ", "area": "dev"}), {"txt": "muita reunião", "area": "dev"})
        self.assertIsNone(v("problema", {"txt": "x", "area": "outra"}))
        self.assertIsNone(v("problema", {"txt": "   ", "area": "dev"}))
        self.assertEqual(len(v("bom", {"txt": "a" * 500, "area": "daily"})["txt"]), appmod.RETRO_TEXTO_MAX)
        self.assertIsNone(v("eu", {"ids": [1, 2, 3, 4]}))
        self.assertIsNone(v("eu", {"ids": [1, 1]}))
        self.assertIsNone(v("ideia", {"txt": "timer", "t": "rosa"}))
        self.assertEqual(v("ideia", {"txt": "timer", "t": "cacto"})["raiz"], -1)
        self.assertIsNone(v("toque", {"lote": 99}))
        self.assertIsNone(v("apagar_tudo", {}))
        self.assertIsNone(v("clima", "sol"))


class RetroBase(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        self.p = mock.patch.object(appmod, "date", _DiaDeRetro)
        self.p.start()
        con = sqlite3.connect(DB)
        self.mids = [r[0] for r in con.execute("SELECT id FROM members WHERE active = 1 ORDER BY id LIMIT 3")]
        con.close()

    def tearDown(self):
        self.p.stop()

    def pessoa(self, mid):
        c = appmod.app.test_client()
        with c.session_transaction(**REMOTO) as s:
            s["eu"] = mid
        return c

    def post(self, c, url, corpo=None):
        return c.post(url, json=corpo or {}, headers=FETCH, **REMOTO)


class TestFluxo(RetroBase):
    def test_pagina_antes_de_comecar_mostra_o_botao_no_dia(self):
        c = self.pessoa(self.mids[0])
        html = c.get("/retro", **REMOTO).get_data(as_text=True)
        self.assertIn('id="retro-iniciar"', html)
        self.assertNotIn("retro-canvas", html)

    def test_fora_do_dia_ninguem_comeca(self):
        self.p.stop()
        self.p = mock.patch.object(appmod, "date", _DiaComum)
        self.p.start()
        c = self.pessoa(self.mids[0])
        self.assertNotIn('id="retro-iniciar"', c.get("/retro", **REMOTO).get_data(as_text=True))
        self.assertEqual(self.post(c, "/api/retro/iniciar").status_code, 403)

    def test_sem_login_nao_comeca(self):
        c = appmod.app.test_client()
        self.assertEqual(self.post(c, "/api/retro/iniciar").status_code, 403)

    def test_telao_e_jogadores(self):
        host, ana, bia = (self.pessoa(m) for m in self.mids)
        r = self.post(host, "/api/retro/iniciar")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["telao"])
        # quem chega depois entra como jogador
        self.assertFalse(self.post(ana, "/api/retro/iniciar").get_json()["telao"])
        html = ana.get("/retro", **REMOTO).get_data(as_text=True)
        self.assertIn("retro-canvas", html)
        self.assertIn('"jogador"', html)
        self.assertIn('"telao"', host.get("/retro?telao=1", **REMOTO).get_data(as_text=True))

        # acao valida entra na fila; invalida e recusada
        self.assertEqual(self.post(ana, "/api/retro/acao", {"tipo": "problema", "dados": {"txt": "Ninguém controla o tempo", "area": "daily"}}).status_code, 200)
        self.assertEqual(self.post(bia, "/api/retro/acao", {"tipo": "problema", "dados": {"txt": "", "area": "daily"}}).status_code, 400)
        self.assertEqual(self.post(appmod.app.test_client(), "/api/retro/acao", {"tipo": "clima", "dados": {"v": "sol"}}).status_code, 403)

        # so o telao grava estado, e recebe as acoes desde a ultima vista
        self.assertEqual(self.post(ana, "/api/retro/host", {"estado": {"v": 1}}).status_code, 409)
        j = self.post(host, "/api/retro/host", {"estado": {"v": 1, "fase": "problemas"}, "desde": 0}).get_json()
        self.assertEqual(j["rev"], 1)
        self.assertEqual([(a["m"], a["tipo"]) for a in j["acoes"]], [(self.mids[1], "problema")])
        ult = j["acoes"][-1]["id"]
        self.assertEqual(self.post(host, "/api/retro/host", {"desde": ult}).get_json()["acoes"], [])

        # todo mundo ve o mesmo estado; com a rev igual, a resposta vem curta
        e = bia.get("/api/retro/estado", **REMOTO).get_json()
        self.assertEqual(e["estado"]["fase"], "problemas")
        self.assertNotIn("estado", bia.get("/api/retro/estado?rev=1", **REMOTO).get_json())

    def test_assumir_o_telao_so_quando_parou(self):
        host, ana = self.pessoa(self.mids[0]), self.pessoa(self.mids[1])
        self.post(host, "/api/retro/iniciar")
        self.assertEqual(self.post(ana, "/api/retro/assumir").status_code, 409)
        con = sqlite3.connect(DB)
        con.execute("UPDATE retro SET host_visto = datetime('now', '-1 minute')")
        con.commit()
        con.close()
        self.assertEqual(self.post(ana, "/api/retro/assumir").status_code, 200)
        self.assertEqual(self.post(host, "/api/retro/host", {"estado": {"v": 1}}).status_code, 409)
        self.assertEqual(self.post(ana, "/api/retro/host", {"estado": {"v": 1}}).status_code, 200)

    def test_estado_grande_demais_e_recusado(self):
        host = self.pessoa(self.mids[0])
        self.post(host, "/api/retro/iniciar")
        r = self.post(host, "/api/retro/host", {"estado": {"x": "a" * (appmod.RETRO_ESTADO_MAX + 10)}})
        self.assertEqual(r.status_code, 413)

    def test_card_na_tela_hoje(self):
        c = self.pessoa(self.mids[0])
        html = c.get("/dia/2026-11-06", **REMOTO).get_data(as_text=True)
        self.assertIn("Hoje é dia de retro da sprint", html)
        self.assertIn("Começar a retro", html)
        self.assertNotIn("dia de retro", c.get("/dia/2026-11-05", **REMOTO).get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
