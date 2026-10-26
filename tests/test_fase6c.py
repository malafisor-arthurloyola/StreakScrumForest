import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "fase6c.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import ata_fmt  # noqa: E402
import gitlab_sync  # noqa: E402

DB = str(appmod.DB_PATH)
HOJE = date.today().isoformat()
TOKEN = "token-de-teste-6c"       # valor FALSO, so para os testes


def _primeiro_id():
    con = sqlite3.connect(DB)
    try:
        return con.execute("SELECT id FROM members LIMIT 1").fetchone()[0]
    finally:
        con.close()


class Base(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        for k in ("ADMIN_CODE", "ADMIN_LOCAL", "SYNC_TOKEN"):
            os.environ.pop(k, None)
        try:
            appmod.GITLAB_SYNC_ERROS.clear()
        except Exception:
            pass
        self.client = appmod.app.test_client()

    def ids(self):
        con = sqlite3.connect(DB)
        v = {r[1]: r[0] for r in con.execute("SELECT id, name FROM members")}
        con.close()
        return v

    def enviar(self, cards):
        os.environ["SYNC_TOKEN"] = TOKEN
        r = self.client.post("/api/gitlab/snapshot", json={"cards": cards, "base_url": ""},
                             headers={"Authorization": "Bearer " + TOKEN})
        os.environ.pop("SYNC_TOKEN", None)
        return r


# ------------------------------------------------------------ montagem do retrato (puro)
class TestMontagemRica(unittest.TestCase):
    def _issues(self):
        return [
            {"iid": 1, "title": "Doing meu", "labels": ["Doing"], "assignees": [{"username": "arthur"}]},
            {"iid": 2, "title": "Em waiting", "labels": ["Waiting review"], "assignees": [{"username": "arthur"}]},
            {"iid": 3, "title": "Em review (board)", "labels": ["Review"], "assignees": [{"username": "bento"}]},
            {"iid": 4, "title": "Backlog sem dono", "labels": ["Backlog"], "assignees": []},
            {"iid": 5, "title": "Backlog do vitor", "labels": ["backlog"], "assignees": [{"username": "vitor"}]},
            {"iid": 6, "title": "Doing sem dono", "labels": ["Doing"], "assignees": []},
        ]

    def test_backlog_mantem_sem_dono_doing_nao(self):
        cards = gitlab_sync.montar_retrato(self._issues())
        # backlog sem dono entra com usuario=''
        self.assertTrue(any(c["iid"] == 4 and c["coluna"] == "backlog" and c["usuario"] == "" for c in cards))
        # doing sem dono NAO entra
        self.assertFalse(any(c["iid"] == 6 for c in cards))

    def test_colunas_por_label(self):
        cards = gitlab_sync.montar_retrato(self._issues())
        por_iid = {c["iid"]: c["coluna"] for c in cards}
        self.assertEqual(por_iid[1], "doing")
        self.assertEqual(por_iid[2], "review")
        self.assertEqual(por_iid[3], "em_revisao")

    def test_fechadas_viram_done(self):
        fechadas = [{"iid": 9, "title": "Fechado", "labels": ["Closed"], "assignees": [{"username": "arthur"}]}]
        cards = gitlab_sync.montar_retrato([], fechadas=fechadas)
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["coluna"], "done")

    def test_busca_backlog(self):
        cards = gitlab_sync.montar_retrato(self._issues())
        self.assertEqual([c["iid"] for c in gitlab_sync.busca_backlog(cards, "vitor")], [5])
        self.assertEqual([c["iid"] for c in gitlab_sync.busca_backlog(cards, "#4")], [4])
        self.assertEqual(sorted(c["iid"] for c in gitlab_sync.busca_backlog(cards, "")), [4, 5])
        self.assertEqual(gitlab_sync.busca_backlog(cards, "nada que exista"), [])


# ------------------------------------------------------------ migracao idempotente da tabela
class TestMigracao(unittest.TestCase):
    def test_banco_antigo_vira_novo_sem_perder(self):
        caminho = os.path.join(_TMP, "antigo.db")
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(caminho + ext):
                os.remove(caminho + ext)
        con = sqlite3.connect(caminho)
        con.row_factory = sqlite3.Row
        con.executescript(
            "CREATE TABLE gitlab_cards (iid INTEGER NOT NULL, "
            "coluna TEXT NOT NULL CHECK (coluna IN ('doing','review')), usuario TEXT NOT NULL, "
            "titulo TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '', labels TEXT NOT NULL DEFAULT '', "
            "atualizado_em TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY (iid,coluna,usuario));"
            "INSERT INTO gitlab_cards (iid,coluna,usuario,titulo) VALUES (1,'doing','arthur','velho');"
        )
        con.commit()
        # antes: nao aceita as colunas novas
        self.assertFalse(appmod._gitlab_cards_aceita_novas_colunas(con))
        appmod._migrar_gitlab_cards_colunas(con)       # migra
        appmod._migrar_gitlab_cards_colunas(con)       # 2x nao quebra
        con.commit()
        self.assertTrue(appmod._gitlab_cards_aceita_novas_colunas(con))
        n = con.execute("SELECT COUNT(*) FROM gitlab_cards WHERE titulo='velho'").fetchone()[0]
        self.assertEqual(n, 1)                          # nao perdeu dados
        con.execute("INSERT INTO gitlab_cards (iid,coluna,usuario) VALUES (2,'backlog','')")
        con.commit()
        con.close()


# ------------------------------------------------------------ rotas cards/backlog
class TestRotas(Base):
    def _cards_exemplo(self):
        return [
            {"iid": 10, "coluna": "doing", "usuario": "arthur", "titulo": "Fazer", "url": "", "labels": ""},
            {"iid": 11, "coluna": "review", "usuario": "arthur", "titulo": "Waiting meu", "url": "", "labels": ""},
            {"iid": 12, "coluna": "em_revisao", "usuario": "bento", "titulo": "Review do bento", "url": "", "labels": ""},
            {"iid": 13, "coluna": "done", "usuario": "arthur", "titulo": "Fechei", "url": "", "labels": ""},
            {"iid": 14, "coluna": "backlog", "usuario": "", "titulo": "Backlog livre login", "url": "", "labels": ""},
        ]

    def test_cards_fiz_fazer_revisar(self):
        con = sqlite3.connect(DB); con.execute("UPDATE members SET gitlab_user='arthur' WHERE name='Arthur'"); con.commit(); con.close()
        self.assertEqual(self.enviar(self._cards_exemplo()).status_code, 200)
        mid = self.ids()["Arthur"]
        j = self.client.get("/api/gitlab/cards?member_id=%d" % mid).get_json()
        self.assertEqual({c["iid"] for c in j["fazer"]}, {10})
        self.assertEqual({c["iid"] for c in j["fiz"]}, {11, 13})       # waiting + done do arthur
        # "revisar" e do quadro inteiro: inclui o card do bento (#12) e o waiting (#11)
        self.assertEqual({c["iid"] for c in j["revisar"]}, {11, 12})

    def test_backlog_rota(self):
        self.enviar(self._cards_exemplo())
        j = self.client.get("/api/gitlab/backlog?q=login").get_json()
        self.assertEqual([c["iid"] for c in j["cards"]], [14])
        j = self.client.get("/api/gitlab/backlog?q=%2314").get_json()
        self.assertEqual([c["iid"] for c in j["cards"]], [14])
        j = self.client.get("/api/gitlab/backlog").get_json()
        self.assertEqual([c["iid"] for c in j["cards"]], [14])

    def test_backlog_vazio_sem_retrato(self):
        j = self.client.get("/api/gitlab/backlog?q=x").get_json()
        self.assertTrue(j["ok"])
        self.assertEqual(j["cards"], [])


# ------------------------------------------------------------ UI pt-BR
class TestUIptBR(Base):
    def test_ata_tem_tres_campos_ptbr_e_ajuda(self):
        con = sqlite3.connect(DB)
        ids = [r[0] for r in con.execute("SELECT id FROM members WHERE COALESCE(tipo,'equipe')='equipe' AND active=1")]
        con.execute("INSERT OR IGNORE INTO atas(data,tipo,relator_id) VALUES(?,?,?)", (HOJE, "daily", ids[0]))
        con.execute("INSERT OR IGNORE INTO attendance(member_id,event_date,event_type,status) VALUES(?,?,?,'presente')", (ids[0], HOJE, "daily"))
        con.commit(); con.close()
        html = self.client.get("/ata/%s/daily" % HOJE).get_data(as_text=True)
        self.assertIn("O que fiz", html)
        self.assertIn("O que vou fazer hoje", html)
        self.assertIn("Vou revisar", html)
        self.assertIn("gl-ajuda", html)                 # bolinha de ajuda
        self.assertIn("gl-backlog-busca", html)         # busca no backlog
        self.assertIn('data-chips-para="feito"', html)


# ------------------------------------------------------------ export pt-BR primeiro + review nao rende
class TestExportERende(Base):
    def test_default_idioma_e_pt(self):
        con = sqlite3.connect(DB)
        idioma = con.execute("SELECT valor FROM config WHERE chave='idioma_ata'").fetchone()[0]
        con.close()
        self.assertEqual(idioma, "pt")

    def test_imprimir_sem_idioma_sai_pt(self):
        a = _primeiro_id()
        # garante uma fala
        with appmod.app.test_request_context():
            db = appmod.get_db()
            appmod._salvar_fala(db, HOJE, "daily", a, feito="fiz algo")
            db.commit()
        h = self.client.get("/ata/%s/daily/imprimir" % HOJE).get_data(as_text=True)
        self.assertIn("Presentes", h)            # rotulo pt
        self.assertNotIn("Present:", h)          # nao o modelo en

    def test_review_nao_rende(self):
        mid = _primeiro_id()
        with appmod.app.test_request_context():
            db = appmod.get_db()
            appmod._salvar_fala(db, HOJE, "daily", mid, review="#5 vou revisar")
            db.commit()
            com_fala, _ = appmod._contagem_atas(db, [HOJE])
        self.assertEqual(com_fala.get(mid, 0), 0)


if __name__ == "__main__":
    unittest.main()
