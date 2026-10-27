import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "fase6m.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import gitlab_sync  # noqa: E402

DB = str(appmod.DB_PATH)
TOKEN = "token-de-teste-123"       # valor FALSO, so para os testes

S1 = ("Sprint 01", "2026-10-12", "2026-10-23")
S2 = ("Sprint 02", "2026-10-26", "2026-11-06")
S3 = ("Sprint 03", "2026-11-09", "2026-11-20")


class _Hoje(date):
    alvo = date(2026, 10, 28)

    @classmethod
    def today(cls):
        return cls.alvo


# ------------------------------------------------------------ regra pura
class TestMilestoneAtual(unittest.TestCase):
    def test_a_que_contem_hoje(self):
        self.assertEqual(gitlab_sync.milestone_atual([S1, S2, S3], "2026-10-28"), "Sprint 02")

    def test_muda_sozinha_com_as_sprints(self):
        self.assertEqual(gitlab_sync.milestone_atual([S1, S2, S3], "2026-10-15"), "Sprint 01")
        self.assertEqual(gitlab_sync.milestone_atual([S1, S2, S3], "2026-11-10"), "Sprint 03")

    def test_fim_de_semana_entre_sprints_fica_com_a_ultima_que_comecou(self):
        self.assertEqual(gitlab_sync.milestone_atual([S1, S2, S3], "2026-10-24"), "Sprint 01")

    def test_antes_de_comecar_pega_a_primeira(self):
        self.assertEqual(gitlab_sync.milestone_atual([S2, S3], "2026-10-01"), "Sprint 02")

    def test_depois_de_todas_pega_a_ultima(self):
        self.assertEqual(gitlab_sync.milestone_atual([S1, S2], "2027-01-01"), "Sprint 02")

    def test_sem_datas_usa_o_numero_da_sprint_do_calendario(self):
        sem = [("Sprint 01", "", ""), ("Sprint 02", "", "")]
        self.assertEqual(gitlab_sync.milestone_atual(sem, "2026-10-28", sprint_n=2), "Sprint 02")
        self.assertIsNone(gitlab_sync.milestone_atual(sem, "2026-10-28"))

    def test_sem_milestone_nenhuma(self):
        self.assertIsNone(gitlab_sync.milestone_atual([], "2026-10-28"))
        self.assertIsNone(gitlab_sync.milestone_atual([("", "", "")], "2026-10-28"))


class TestRetratoTrazAMilestone(unittest.TestCase):
    def test_montar_e_validar(self):
        issues = [{"iid": 7, "title": "Algo", "web_url": "https://gl/-/issues/7", "labels": ["Waiting review"],
                   "assignees": [{"username": "ana"}],
                   "milestone": {"title": "Sprint 02", "start_date": "2026-10-26", "due_date": "2026-11-06"}}]
        cards = gitlab_sync.montar_retrato(issues)
        self.assertEqual(cards[0]["milestone"], "Sprint 02")
        self.assertEqual(cards[0]["milestone_inicio"], "2026-10-26")
        self.assertEqual(cards[0]["milestone_fim"], "2026-11-06")
        limpos = gitlab_sync.validar_cards(cards)
        self.assertEqual(limpos[0]["milestone"], "Sprint 02")

    def test_issue_sem_milestone_fica_vazia(self):
        cards = gitlab_sync.montar_retrato([{"iid": 1, "title": "x", "labels": ["Doing"],
                                              "assignees": [{"username": "ana"}]}])
        self.assertEqual((cards[0]["milestone"], cards[0]["milestone_inicio"]), ("", ""))

    def test_retrato_antigo_sem_campos_ainda_e_aceito(self):
        limpos = gitlab_sync.validar_cards([{"iid": 1, "coluna": "doing", "usuario": "ana", "titulo": "x"}])
        self.assertEqual(limpos[0]["milestone"], "")


# ------------------------------------------------------------ rotas
class TestCardsSoDaSprintAtual(unittest.TestCase):
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
        _Hoje.alvo = date(2026, 10, 28)
        self.client = appmod.app.test_client()
        con = sqlite3.connect(DB)
        con.execute("UPDATE members SET gitlab_user = 'ana' WHERE id = (SELECT MIN(id) FROM members)")
        self.mid = con.execute("SELECT MIN(id) FROM members").fetchone()[0]
        con.commit()
        con.close()

    def _card(self, iid, coluna, ms, usuario="ana"):
        return {"iid": iid, "coluna": coluna, "usuario": usuario, "titulo": f"card {iid}", "url": "",
                "labels": "", "milestone": ms[0], "milestone_inicio": ms[1], "milestone_fim": ms[2]}

    def _enviar(self, cards):
        r = self.client.post("/api/gitlab/snapshot", json={"cards": cards, "base_url": ""},
                             headers={"Authorization": "Bearer " + TOKEN})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))

    def _cards(self):
        return self.client.get(f"/api/gitlab/cards?member_id={self.mid}").get_json()

    def test_so_aparecem_review_e_fechados_da_milestone_atual(self):
        self._enviar([
            self._card(1, "review", S2), self._card(2, "review", S1),
            self._card(3, "em_revisao", S2), self._card(4, "done", S2), self._card(5, "done", S1),
        ])
        r = self._cards()
        self.assertEqual(r["milestone"], "Sprint 02")
        self.assertEqual(sorted(c["iid"] for c in r["fiz"]), [1, 3, 4])
        self.assertEqual(sorted(c["iid"] for c in r["revisar"]), [1, 3])

    def test_muda_automaticamente_quando_a_sprint_passa(self):
        self._enviar([self._card(1, "review", S1), self._card(2, "review", S2)])
        self.assertEqual([c["iid"] for c in self._cards()["fiz"]], [2])
        _Hoje.alvo = date(2026, 10, 15)               # volta para a Sprint 1: sem novo envio
        self.assertEqual([c["iid"] for c in self._cards()["fiz"]], [1])

    def test_doing_e_backlog_nao_dependem_da_milestone(self):
        self._enviar([self._card(1, "doing", S1), self._card(2, "backlog", S1, usuario=""),
                      self._card(3, "review", S2)])
        r = self._cards()
        self.assertEqual([c["iid"] for c in r["fazer"]], [1])           # doing da sprint antiga continua
        b = self.client.get("/api/gitlab/backlog?q=card").get_json()
        self.assertEqual([c["iid"] for c in b["cards"]], [2])           # backlog da sprint antiga continua

    def test_card_sem_milestone_fica_de_fora_quando_ha_milestones(self):
        self._enviar([self._card(1, "review", ("", "", "")), self._card(2, "review", S2)])
        self.assertEqual([c["iid"] for c in self._cards()["fiz"]], [2])

    def test_sem_nenhuma_milestone_no_quadro_mostra_tudo(self):
        self._enviar([self._card(1, "review", ("", "", "")), self._card(2, "done", ("", "", ""))])
        r = self._cards()
        self.assertEqual(r["milestone"], "")
        self.assertEqual(sorted(c["iid"] for c in r["fiz"]), [1, 2])

    def test_migracao_adiciona_as_colunas_em_banco_antigo(self):
        con = sqlite3.connect(DB)
        con.executescript("DROP TABLE gitlab_cards;"
                          "CREATE TABLE gitlab_cards (iid INTEGER NOT NULL, coluna TEXT NOT NULL "
                          "CHECK (coluna IN ('doing','review','em_revisao','backlog','done')), usuario TEXT NOT NULL, "
                          "titulo TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '', labels TEXT NOT NULL DEFAULT '', "
                          "atualizado_em TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY (iid, coluna, usuario));"
                          "INSERT INTO gitlab_cards (iid, coluna, usuario, titulo) VALUES (9, 'doing', 'ana', 'velho');")
        con.commit()
        con.close()
        appmod.init_db()
        appmod.init_db()                              # 2x nao quebra
        con = sqlite3.connect(DB)
        cols = {r[1] for r in con.execute("PRAGMA table_info(gitlab_cards)")}
        n = con.execute("SELECT COUNT(*) FROM gitlab_cards").fetchone()[0]
        con.close()
        self.assertTrue({"milestone", "milestone_inicio", "milestone_fim"} <= cols)
        self.assertEqual(n, 1)                         # nao perdeu a linha antiga

    def test_cabecalho_das_telas_mostra_a_milestone(self):
        h = self.client.get("/ata/2026-10-28/daily").get_data(as_text=True)
        self.assertIn("revisão e fechados da", h)


if __name__ == "__main__":
    unittest.main()
