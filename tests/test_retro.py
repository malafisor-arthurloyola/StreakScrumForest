"""Retro da sprint (Defesa do Canteiro) ao vivo.
Regras que os testes guardam: a retro e no ultimo dia letivo de cada sprint (06/11 e 19/11, porque 20/11 e
feriado); so quem conduz (administrador ou Scrum do dia) comeca, fica com o telao e avanca as etapas;
so o telao grava o estado; as pessoas mandam acoes validadas e recusadas se a etapa ja passou;
participante nenhum assume o telao, nem com ele parado."""
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

    def pessoa(self, mid, admin=False):
        c = appmod.app.test_client()
        with c.session_transaction(**REMOTO) as s:
            s["eu"] = mid
            if admin:
                s["admin"] = True
        return c

    def conduz(self, mid=None):
        """Quem conduz: administrador (com ou sem jardim)."""
        return self.pessoa(self.mids[0] if mid is None else mid, admin=True)

    def post(self, c, url, corpo=None):
        return c.post(url, json=corpo or {}, headers=FETCH, **REMOTO)


class TestFluxo(RetroBase):
    def test_pagina_antes_de_comecar_mostra_o_botao_so_para_quem_conduz(self):
        html = self.conduz().get("/retro", **REMOTO).get_data(as_text=True)
        self.assertIn('id="retro-iniciar"', html)
        self.assertNotIn("retro-canvas", html)
        html = self.pessoa(self.mids[1]).get("/retro", **REMOTO).get_data(as_text=True)
        self.assertNotIn('id="retro-iniciar"', html)
        self.assertIn("Quem conduz", html)

    def test_participante_nao_comeca_a_retro(self):
        r = self.post(self.pessoa(self.mids[1]), "/api/retro/iniciar")
        self.assertEqual(r.status_code, 403)
        self.assertIn("Scrum do dia", r.get_json()["erro"])
        con = sqlite3.connect(DB)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM retro").fetchone()[0], 0)
        con.close()

    def test_scrum_do_dia_conduz(self):
        con = sqlite3.connect(DB)
        con.execute("INSERT INTO atas (data, tipo, relator_id) VALUES ('2026-11-06', 'daily', ?)", (self.mids[2],))
        con.commit()
        con.close()
        r = self.post(self.pessoa(self.mids[2]), "/api/retro/iniciar")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["telao"])

    def test_fora_do_dia_participante_nao_comeca_e_admin_ensaia(self):
        self.p.stop()
        self.p = mock.patch.object(appmod, "date", _DiaComum)
        self.p.start()
        c = self.pessoa(self.mids[1])
        self.assertNotIn('id="retro-iniciar"', c.get("/retro", **REMOTO).get_data(as_text=True))
        self.assertEqual(self.post(c, "/api/retro/iniciar").status_code, 403)
        self.assertTrue(self.post(self.conduz(), "/api/retro/iniciar").get_json()["telao"])

    def test_sem_login_nao_comeca(self):
        c = appmod.app.test_client()
        self.assertEqual(self.post(c, "/api/retro/iniciar").status_code, 403)

    def test_telao_e_jogadores(self):
        host, ana, bia = self.conduz(), self.pessoa(self.mids[1]), self.pessoa(self.mids[2])
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

    def test_participante_nunca_assume_o_telao(self):
        host, ana = self.conduz(), self.pessoa(self.mids[1])
        self.post(host, "/api/retro/iniciar")
        self.assertEqual(self.post(ana, "/api/retro/assumir").status_code, 403)
        con = sqlite3.connect(DB)
        con.execute("UPDATE retro SET host_visto = datetime('now', '-1 minute')")
        con.commit()
        con.close()
        # nem com o telao parado
        self.assertEqual(self.post(ana, "/api/retro/assumir").status_code, 403)
        self.assertNotIn('id="retro-assumir"', ana.get("/retro", **REMOTO).get_data(as_text=True))
        # quem entra depois, mesmo tocando em "comecar", vira jogador
        r = self.post(ana, "/api/retro/iniciar").get_json()
        self.assertFalse(r["telao"])
        self.assertEqual(self.post(host, "/api/retro/host", {"estado": {"v": 1}}).status_code, 200)

    def test_quem_conduz_leva_o_telao_para_outro_aparelho(self):
        pc, celular = self.conduz(), self.conduz(self.mids[1])
        self.post(pc, "/api/retro/iniciar")
        self.assertIn('id="retro-assumir"', celular.get("/retro", **REMOTO).get_data(as_text=True))
        self.assertEqual(self.post(celular, "/api/retro/assumir").status_code, 200)
        self.assertEqual(self.post(pc, "/api/retro/host", {"estado": {"v": 1}}).status_code, 409)
        self.assertEqual(self.post(celular, "/api/retro/host", {"estado": {"v": 1}}).status_code, 200)

    def test_acao_fora_da_etapa_e_recusada_em_vez_de_sumir(self):
        host, ana = self.conduz(), self.pessoa(self.mids[1])
        self.post(host, "/api/retro/iniciar")
        acao = lambda tipo, dados: self.post(ana, "/api/retro/acao", {"tipo": tipo, "dados": dados})
        prob = {"txt": "Daily longa", "area": "daily"}
        # antes do telao gravar qualquer coisa, entra
        self.assertEqual(acao("problema", prob).status_code, 200)
        # problema e coisa boa valem em todas as etapas antes das conversas
        for fase in ("abertura", "problemas", "bons", "eu", "euRes"):
            self.post(host, "/api/retro/host", {"estado": {"v": 1, "fase": fase}})
            self.assertEqual(acao("problema", prob).status_code, 200, fase)
            self.assertEqual(acao("bom", prob).status_code, 200, fase)
        self.assertEqual(acao("eu", {"ids": [1]}).status_code, 200)
        # nas rodadas, nao: a pessoa recebe o aviso em vez de um "ok" que o telao descartaria
        rodada = {"v": 1, "fase": "rodada", "rodadas": 2, "atual": {"fase": "conversa", "pid": 3}}
        self.post(host, "/api/retro/host", {"estado": rodada})
        r = acao("problema", prob)
        self.assertEqual(r.status_code, 409)
        self.assertIn("etapa já passou", r.get_json()["erro"])
        self.assertEqual(acao("eu", {"ids": [1]}).status_code, 409)
        self.assertEqual(acao("porque", {"txt": "pressa", "rodada": 2}).status_code, 200)
        # porque de uma rodada que ja acabou nao cai na praga seguinte
        self.assertEqual(acao("porque", {"txt": "pressa", "rodada": 1}).status_code, 409)
        self.assertEqual(acao("topo", {"rodada": 2}).status_code, 409)
        rodada["atual"]["fase"] = "topo"
        self.post(host, "/api/retro/host", {"estado": rodada})
        self.assertEqual(acao("topo", {"rodada": 2}).status_code, 200)
        self.assertEqual(acao("obrigado", {"para": self.mids[0]}).status_code, 409)
        self.post(host, "/api/retro/host", {"estado": {"v": 1, "fase": "fecho"}})
        self.assertEqual(acao("obrigado", {"para": self.mids[0]}).status_code, 200)

    def test_reiniciar_apaga_a_retro_de_hoje_so_para_quem_conduz(self):
        host, ana = self.conduz(), self.pessoa(self.mids[1])
        self.post(host, "/api/retro/iniciar")
        self.post(ana, "/api/retro/acao", {"tipo": "problema", "dados": {"txt": "Daily longa", "area": "daily"}})
        self.assertNotIn('id="retro-reiniciar"', ana.get("/retro", **REMOTO).get_data(as_text=True))
        self.assertIn('id="retro-reiniciar"', host.get("/retro", **REMOTO).get_data(as_text=True))
        self.assertEqual(self.post(ana, "/api/retro/reiniciar").status_code, 403)
        self.assertTrue(ana.get("/api/retro/estado", **REMOTO).get_json()["ativa"])
        self.assertEqual(self.post(host, "/api/retro/reiniciar").status_code, 200)
        self.assertFalse(ana.get("/api/retro/estado", **REMOTO).get_json()["ativa"])
        con = sqlite3.connect(DB)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM retro_acoes").fetchone()[0], 0)
        con.close()
        # o telao antigo e avisado (404) e da para comecar de novo
        self.assertEqual(self.post(host, "/api/retro/host", {"estado": {"v": 1}}).status_code, 404)
        self.assertTrue(self.post(host, "/api/retro/iniciar").get_json()["telao"])

    def test_estado_grande_demais_e_recusado(self):
        host = self.conduz()
        self.post(host, "/api/retro/iniciar")
        r = self.post(host, "/api/retro/host", {"estado": {"x": "a" * (appmod.RETRO_ESTADO_MAX + 10)}})
        self.assertEqual(r.status_code, 413)

    def test_card_na_tela_hoje(self):
        c = self.pessoa(self.mids[0])
        html = c.get("/dia/2026-11-06", **REMOTO).get_data(as_text=True)
        self.assertIn("Hoje é dia de retro da sprint", html)
        self.assertIn("Abrir a retro", html)
        self.assertNotIn("Começar a retro", html)
        self.assertIn("Começar a retro", self.conduz().get("/dia/2026-11-06", **REMOTO).get_data(as_text=True))
        self.assertNotIn("dia de retro", c.get("/dia/2026-11-05", **REMOTO).get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
