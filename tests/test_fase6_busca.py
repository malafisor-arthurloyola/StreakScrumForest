import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "fase6b.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import gitlab_sync  # noqa: E402

DB = str(appmod.DB_PATH)
TOKEN = "token-de-teste-123"       # valor FALSO, so para os testes
S1 = ("Sprint 01", "2026-10-12", "2026-10-23")
S2 = ("Sprint 02", "2026-10-26", "2026-11-06")


class _Hoje(date):
    @classmethod
    def today(cls):
        return date(2026, 10, 28)


class TestBuscarCardsPuro(unittest.TestCase):
    CARDS = [
        {"iid": 1, "coluna": "review", "usuario": "ana", "titulo": "Limpeza de dados", "url": ""},
        {"iid": 1, "coluna": "review", "usuario": "bia", "titulo": "Limpeza de dados", "url": ""},
        {"iid": 2, "coluna": "done", "usuario": "ana", "titulo": "Grafico de barras", "url": ""},
        {"iid": 3, "coluna": "backlog", "usuario": "", "titulo": "Limpeza do repositorio", "url": ""},
    ]

    def test_so_as_colunas_pedidas(self):
        r = gitlab_sync.buscar_cards(self.CARDS, ("review", "em_revisao", "done"), "limpeza")
        self.assertEqual([c["iid"] for c in r], [1])            # o 3 e backlog: fica de fora

    def test_por_numero_e_por_titulo_sem_acento_de_caixa(self):
        self.assertEqual([c["iid"] for c in gitlab_sync.buscar_cards(self.CARDS, ("done",), "#2")], [2])
        self.assertEqual([c["iid"] for c in gitlab_sync.buscar_cards(self.CARDS, ("done",), "GRAFICO")], [2])

    def test_nao_repete_o_card_com_dois_responsaveis(self):
        r = gitlab_sync.buscar_cards(self.CARDS, ("review",), "")
        self.assertEqual(len(r), 1)
        self.assertEqual(sorted(r[0]["responsaveis"]), ["ana", "bia"])

    def test_limite(self):
        cards = [{"iid": i, "coluna": "done", "usuario": "a", "titulo": "x", "url": ""} for i in range(10)]
        self.assertEqual(len(gitlab_sync.buscar_cards(cards, ("done",), "", limite=3)), 3)

    def test_busca_backlog_continua_igual(self):
        self.assertEqual([c["iid"] for c in gitlab_sync.busca_backlog(self.CARDS, "limpeza")], [3])


class TestRotaBuscar(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        os.environ["SYNC_TOKEN"] = TOKEN
        self.addCleanup(lambda: os.environ.pop("SYNC_TOKEN", None))
        p = mock.patch.object(appmod, "date", _Hoje)
        p.start()
        self.addCleanup(p.stop)
        self.client = appmod.app.test_client()
        cards = [
            self._c(1, "review", S2, "Limpeza de dados"), self._c(2, "em_revisao", S2, "Grafico de barras"),
            self._c(3, "done", S2, "Normalizacao"), self._c(4, "review", S1, "Card velho da sprint 1"),
            self._c(5, "done", S1, "Entrega antiga"), self._c(6, "backlog", ("", "", ""), "Pesquisa futura", usuario=""),
        ]
        r = self.client.post("/api/gitlab/snapshot", json={"cards": cards, "base_url": ""},
                             headers={"Authorization": "Bearer " + TOKEN})
        self.assertEqual(r.status_code, 200)

    def _c(self, iid, coluna, ms, titulo, usuario="ana"):
        return {"iid": iid, "coluna": coluna, "usuario": usuario, "titulo": titulo, "url": "", "labels": "",
                "milestone": ms[0], "milestone_inicio": ms[1], "milestone_fim": ms[2]}

    def _buscar(self, q=""):
        return self.client.get("/api/gitlab/buscar", query_string={"q": q}).get_json()

    def test_so_review_e_fechados_da_sprint_atual(self):
        j = self._buscar("")
        self.assertEqual(sorted(c["iid"] for c in j["cards"]), [1, 2, 3])
        self.assertEqual(j["milestone"], "Sprint 02")

    def test_por_titulo(self):
        self.assertEqual([c["iid"] for c in self._buscar("grafico")["cards"]], [2])

    def test_texto_nao_acha_card_de_outra_sprint(self):
        self.assertEqual(self._buscar("velho")["cards"], [])

    def test_numero_exato_acha_ate_de_outra_sprint(self):
        self.assertEqual([c["iid"] for c in self._buscar("#4")["cards"]], [4])
        self.assertEqual([c["iid"] for c in self._buscar("5")["cards"]], [5])

    def test_backlog_nao_aparece_aqui(self):
        self.assertEqual(self._buscar("pesquisa")["cards"], [])
        self.assertEqual(self._buscar("6")["cards"], [])

    def test_traz_a_citacao_pronta(self):
        self.assertEqual(self._buscar("1")["cards"][0]["citacao"], "#1 Limpeza de dados")

    def test_sem_retrato_devolve_vazio(self):
        con = sqlite3.connect(DB)
        con.execute("DELETE FROM gitlab_cards")
        con.commit()
        con.close()
        j = self._buscar("x")
        self.assertTrue(j["ok"])
        self.assertEqual(j["cards"], [])


class TestCaixasDeBuscaNasTelas(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        self.client = appmod.app.test_client()                  # localhost = administrador
        con = sqlite3.connect(DB)
        self.mid = con.execute("SELECT MIN(id) FROM members").fetchone()[0]
        con.close()

    def test_ata_tem_busca_em_o_que_fiz_e_em_vou_revisar(self):
        h = self.client.get("/ata/2026-10-28/daily").get_data(as_text=True)
        self.assertIn('data-para="feito"', h)
        self.assertIn('data-para="review"', h)
        self.assertIn("gl-busca-sprint.js", h)

    def test_day_closing_tem_chips_e_buscas_menos_o_vou_revisar(self):
        h = self.client.get("/ata/2026-10-28/fechamento").get_data(as_text=True)
        self.assertIn('data-chips-para="feito"', h)
        self.assertIn('data-chips-para="planejado"', h)
        self.assertIn('class="gl-sprint-busca" data-para="feito"', h)
        self.assertIn("gl-backlog-busca", h)                   # busca no Backlog em "Ficou para depois"
        self.assertNotIn('class="gl-sprint-busca" data-para="review"', h)   # "Vou revisar" e so da daily
        self.assertNotIn('<div class="gl-chips" data-chips-para="review"', h)

    def test_day_closing_do_meu_jardim_tambem(self):
        hoje = date.today().isoformat()
        con = sqlite3.connect(DB)
        con.execute("INSERT OR REPLACE INTO attendance (member_id, event_date, event_type, status) VALUES (?,?,?, 'presente')",
                    (self.mid, hoje, "encerramento"))
        con.commit()
        con.close()
        with self.client.session_transaction() as sess:
            sess["eu"] = self.mid
        h = self.client.get("/eu").get_data(as_text=True)
        bloco = h[h.index('data-tipo="fechamento"'):]
        self.assertIn('data-chips-para="feito"', bloco)
        self.assertIn('data-chips-para="planejado"', bloco)
        self.assertIn("gl-backlog-busca", bloco)

    def test_meu_jardim_e_presenca_tem_a_busca(self):
        con = sqlite3.connect(DB)
        con.execute("INSERT OR REPLACE INTO attendance (member_id, event_date, event_type, status) VALUES (?,?,?, 'presente')",
                    (self.mid, date.today().isoformat(), "daily"))
        con.commit()
        con.close()
        with self.client.session_transaction() as sess:
            sess["eu"] = self.mid
        h = self.client.get("/eu").get_data(as_text=True)
        self.assertIn('data-para="feito"', h)
        self.assertIn('data-para="review"', h)
        cod = appmod.codigo_do_evento(date.today().isoformat(), "daily")
        h2 = self.client.get(f"/presenca/daily/{cod}").get_data(as_text=True)
        self.assertIn('data-para="feito"', h2)


if __name__ == "__main__":
    unittest.main()
