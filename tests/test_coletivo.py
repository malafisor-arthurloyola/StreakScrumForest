import os
import sqlite3
import sys
import tempfile
import unittest

# O banco de teste e sempre um arquivo temporario; nunca o banco real.
_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "coletivo.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402

DB = str(appmod.DB_PATH)


def _dias():
    return game.dias_letivos("2026-10-15", "2026-10-12", 10,
                             {"2026-10-12", "2026-11-02", "2026-11-20"})


class ColetivoBase(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        self.client = appmod.app.test_client()
        self.dias = _dias()

    def presencas(self, member_ids, n, status="presente"):
        con = sqlite3.connect(DB)
        for mid in member_ids:
            for d in self.dias[:n]:
                con.execute(
                    "INSERT OR REPLACE INTO attendance (member_id, event_date, event_type, status) "
                    "VALUES (?,?,?,?)", (mid, d, "daily", status),
                )
        con.commit()
        con.close()

    def todos(self):
        con = sqlite3.connect(DB)
        ids = [r[0] for r in con.execute("SELECT id FROM members WHERE active = 1")]
        con.close()
        return ids

    def get(self, url):
        return self.client.get(url)

    def meta(self, **dados):
        return self.client.post("/api/metas", json=dados)


class TestMetas(ColetivoBase):
    def test_adicionar_e_remover(self):
        r = self.meta(acao="adicionar", sprint=1, tipo="presenca_pct", alvo=90)
        self.assertEqual(r.status_code, 200)
        html = self.get("/dashboard").get_data(as_text=True)
        self.assertIn("90%", html)
        mid = r.get_json()["id"]
        self.assertEqual(self.meta(acao="remover", id=mid).status_code, 200)

    def test_tipo_invalido(self):
        self.assertEqual(self.meta(acao="adicionar", sprint=1, tipo="xyz", alvo=5).status_code, 400)

    def test_alvo_invalido(self):
        self.assertEqual(self.meta(acao="adicionar", sprint=1, tipo="dias_cheios", alvo=0).status_code, 400)
        self.assertEqual(self.meta(acao="adicionar", sprint=1, tipo="presenca_pct", alvo=150).status_code, 400)

    def test_meta_cumprida_pelos_dias_cheios(self):
        self.presencas(self.todos(), 2)
        r = self.meta(acao="adicionar", sprint=1, tipo="dias_cheios", alvo=2)
        self.assertEqual(r.status_code, 200)
        html = self.get("/dashboard").get_data(as_text=True)
        self.assertIn("meta-cumprida", html)

    def test_metas_sugeridas(self):
        r = self.meta(acao="sugerir", sprint=1)
        self.assertEqual(r.status_code, 200)
        con = sqlite3.connect(DB)
        n = con.execute("SELECT COUNT(*) FROM metas_sprint WHERE sprint = 1").fetchone()[0]
        con.close()
        self.assertGreaterEqual(n, 2)
        # sugerir de novo nao duplica
        self.meta(acao="sugerir", sprint=1)
        con = sqlite3.connect(DB)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM metas_sprint WHERE sprint = 1").fetchone()[0], n)
        con.close()


class TestPaginas(ColetivoBase):
    def test_painel_tem_as_secoes_novas(self):
        html = self.get("/dashboard").get_data(as_text=True)
        for trecho in ("Metas da Sprint", "Bosque da equipe", "Trilha das semanas", "Marcos do jardim"):
            self.assertIn(trecho, html)

    def test_resumo_da_sprint(self):
        self.presencas(self.todos(), 3)
        r = self.get("/sprint/1")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Sprint 1", html)
        self.assertIn("Presença por evento", html)

    def test_sprint_inexistente(self):
        self.assertEqual(self.get("/sprint/99").status_code, 404)
        self.assertEqual(self.get("/sprint/0").status_code, 404)

    def test_perfil_do_membro(self):
        self.presencas([1], 6)
        r = self.get("/membro/1")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Trilha das 10 semanas", html)
        self.assertIn("Calendário de presença", html)

    def test_perfil_inexistente(self):
        self.assertEqual(self.get("/membro/999").status_code, 404)

    def test_hoje_abre(self):
        self.assertEqual(self.get("/dia/2026-10-19").status_code, 200)


class TestBosqueEMarcos(ColetivoBase):
    def test_quem_floresceu_entra_no_bosque(self):
        self.presencas([1], len(self.dias))
        html = self.get("/dashboard").get_data(as_text=True)
        self.assertIn('class="arvore-bosque"', html)

    def test_sem_floresceu_bosque_vazio(self):
        html = self.get("/dashboard").get_data(as_text=True)
        self.assertNotIn('class="arvore-bosque"', html)
        self.assertIn("Ninguém floresceu ainda", html)

    def test_fonte_aparece_com_25_por_cento(self):
        self.presencas(self.todos(), 10)  # 10/36 = 28% de cada planta
        html = self.get("/dia/2026-10-19").get_data(as_text=True)
        self.assertIn('class="fonte"', html)

    def test_fonte_nao_aparece_no_comeco(self):
        html = self.get("/dia/2026-10-19").get_data(as_text=True)
        self.assertNotIn('class="fonte"', html)

    def test_arvore_do_time_com_100_por_cento(self):
        self.presencas(self.todos(), len(self.dias))
        html = self.get("/dia/2026-10-19").get_data(as_text=True)
        self.assertIn('class="arvore-time"', html)


if __name__ == "__main__":
    unittest.main()
