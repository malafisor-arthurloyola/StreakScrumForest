import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "fase6.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import ata_fmt  # noqa: E402
import gitlab_sync  # noqa: E402

DB = str(appmod.DB_PATH)
HOJE = date.today().isoformat()
TOKEN = "token-de-teste-123"       # valor FALSO, so para os testes; nunca um token real


class Base(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        os.environ.pop("ADMIN_CODE", None)
        os.environ.pop("ADMIN_LOCAL", None)
        os.environ.pop("SYNC_TOKEN", None)
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

    def mapear(self, nome, usuario):
        con = sqlite3.connect(DB)
        con.execute("UPDATE members SET gitlab_user = ? WHERE name = ?", (usuario, nome))
        con.commit()
        con.close()

    def enviar(self, cards, token=TOKEN, base_url="https://gl/eq/-/issues"):
        return self.client.post(
            "/api/gitlab/snapshot",
            json={"cards": cards, "base_url": base_url},
            headers={"Authorization": "Bearer " + token} if token is not None else {},
        )


# ------------------------------------------------------------ modulo puro
class TestMontagem(unittest.TestCase):
    def _issues(self):
        return [
            {"iid": 101, "title": "Login", "web_url": "https://gl/-/issues/101",
             "labels": ["Doing", "frontend"], "assignees": [{"username": "arthur"}, {"username": "bento"}]},
            {"iid": 102, "title": "API", "web_url": "https://gl/-/issues/102",
             "labels": ["waiting review"], "assignee": {"username": "arthur"}},
            {"iid": 103, "title": "Dois", "labels": ["DOING", "Waiting Review"],
             "assignees": [{"username": "vitor"}]},
            {"iid": 104, "title": "Sem dono", "labels": ["Doing"], "assignees": []},
            {"iid": 105, "title": "Backlog", "labels": ["To do"], "assignees": [{"username": "x"}]},
        ]

    def test_uma_linha_por_responsavel(self):
        cards = gitlab_sync.montar_retrato(self._issues())
        # 101 doing (arthur, bento) + 102 review (arthur) + 103 doing/review (vitor)
        self.assertEqual(len(cards), 5)
        doing_101 = [c for c in cards if c["iid"] == 101]
        self.assertEqual({c["usuario"] for c in doing_101}, {"arthur", "bento"})
        self.assertTrue(all(c["coluna"] == "doing" for c in doing_101))

    def test_label_sem_diferenciar_maiuscula(self):
        cards = gitlab_sync.montar_retrato(self._issues())
        self.assertIn(("102", "review"), {(str(c["iid"]), c["coluna"]) for c in cards})

    def test_card_em_doing_e_review(self):
        cards = gitlab_sync.montar_retrato(self._issues())
        cols_103 = {c["coluna"] for c in cards if c["iid"] == 103}
        self.assertEqual(cols_103, {"doing", "review"})

    def test_sem_responsavel_e_sem_label_ignorados(self):
        cards = gitlab_sync.montar_retrato(self._issues())
        iids = {c["iid"] for c in cards}
        self.assertNotIn(104, iids)   # sem responsavel
        self.assertNotIn(105, iids)   # sem label de coluna

    def test_labels_configuraveis(self):
        issues = [{"iid": 1, "title": "x", "labels": ["Em andamento"], "assignees": [{"username": "a"}]}]
        cards = gitlab_sync.montar_retrato(issues, label_doing="em andamento")
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["coluna"], "doing")

    def test_validar_recusa_coluna_e_iid(self):
        with self.assertRaises(ValueError):
            gitlab_sync.validar_cards([{"iid": 1, "coluna": "qa", "usuario": "a"}])
        with self.assertRaises(ValueError):
            gitlab_sync.validar_cards([{"iid": "abc", "coluna": "doing", "usuario": "a"}])
        with self.assertRaises(ValueError):
            gitlab_sync.validar_cards([{"iid": 1, "coluna": "doing", "usuario": ""}])

    def test_citacao(self):
        c = {"iid": 7, "titulo": "Fazer algo"}
        self.assertEqual(gitlab_sync.citacao(c), "#7 Fazer algo")


# ------------------------------------------------------------ snapshot (Bearer)
class TestSnapshot(Base):
    def setUp(self):
        super().setUp()
        os.environ["SYNC_TOKEN"] = TOKEN

    def tearDown(self):
        os.environ.pop("SYNC_TOKEN", None)

    def _cards(self, n=2):
        base = [
            {"iid": 201, "coluna": "doing", "usuario": "arthur", "titulo": "A", "url": "", "labels": "Doing"},
            {"iid": 202, "coluna": "review", "usuario": "arthur", "titulo": "B", "url": "", "labels": "Waiting review"},
        ]
        return base[:n]

    def test_bearer_certo_grava(self):
        r = self.enviar(self._cards())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["cards"], 2)
        con = sqlite3.connect(DB)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM gitlab_cards").fetchone()[0], 2)
        con.close()

    def test_bearer_errado_e_ausente_403(self):
        self.assertEqual(self.enviar(self._cards(), token="errado").status_code, 403)
        self.assertEqual(self.enviar(self._cards(), token=None).status_code, 403)
        con = sqlite3.connect(DB)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM gitlab_cards").fetchone()[0], 0)
        con.close()

    def test_sem_sync_token_no_servidor_404(self):
        os.environ.pop("SYNC_TOKEN", None)
        self.assertEqual(self.enviar(self._cards()).status_code, 404)

    def test_formato_invalido_400(self):
        r = self.client.post("/api/gitlab/snapshot",
                             json={"cards": [{"iid": 1, "coluna": "x", "usuario": "a"}]},
                             headers={"Authorization": "Bearer " + TOKEN})
        self.assertEqual(r.status_code, 400)

    def test_substitui_nao_acumula(self):
        self.enviar(self._cards(2))
        self.enviar(self._cards(1))   # manda so 1
        con = sqlite3.connect(DB)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM gitlab_cards").fetchone()[0], 1)
        con.close()

    def test_base_url_nao_sobrescreve_dono(self):
        con = sqlite3.connect(DB)
        con.execute("UPDATE config SET valor = 'https://escolha-do-dono' WHERE chave = 'gitlab_base_url'")
        con.commit(); con.close()
        self.enviar(self._cards(), base_url="https://empurrada")
        con = sqlite3.connect(DB)
        v = con.execute("SELECT valor FROM config WHERE chave = 'gitlab_base_url'").fetchone()[0]
        con.close()
        self.assertEqual(v, "https://escolha-do-dono")

    def test_atualiza_ultima_sync(self):
        self.enviar(self._cards())
        con = sqlite3.connect(DB)
        v = con.execute("SELECT valor FROM config WHERE chave = 'gitlab_ultima_sync'").fetchone()[0]
        con.close()
        self.assertTrue(v)


# ------------------------------------------------------------ GET cards
class TestCards(Base):
    def test_mapeado_devolve_cards(self):
        os.environ["SYNC_TOKEN"] = TOKEN
        self.mapear("Arthur", "arthur")
        self.enviar([
            {"iid": 1, "coluna": "doing", "usuario": "arthur", "titulo": "X", "url": "", "labels": ""},
            {"iid": 2, "coluna": "review", "usuario": "arthur", "titulo": "Y", "url": "", "labels": ""},
        ])
        os.environ.pop("SYNC_TOKEN", None)
        mid = self.ids()["Arthur"]
        j = self.client.get("/api/gitlab/cards?member_id=%d" % mid).get_json()
        self.assertTrue(j["configurado"])
        self.assertEqual(len(j["fazer"]), 1)            # Doing -> "O que vou fazer"
        self.assertEqual(j["fazer"][0]["citacao"], "#1 X")
        self.assertEqual(len(j["fiz"]), 1)              # Waiting review -> "O que fiz"
        self.assertEqual(len(j["revisar"]), 1)          # Waiting review tambem entra em "Vou revisar"

    def test_nao_mapeado_nao_bloqueia(self):
        mid = self.ids()["Bento"]
        j = self.client.get("/api/gitlab/cards?member_id=%d" % mid).get_json()
        self.assertTrue(j["ok"])
        self.assertFalse(j["configurado"])
        self.assertEqual(j["fiz"], [])
        self.assertEqual(j["fazer"], [])
        self.assertEqual(j["revisar"], [])


# ------------------------------------------------------------ UI (chips / review / sync)
class TestUI(Base):
    def _presenca_hoje(self, mid, tipo="daily"):
        con = sqlite3.connect(DB)
        con.execute("INSERT OR IGNORE INTO attendance(member_id,event_date,event_type,status) "
                    "VALUES(?,?,?,'presente')", (mid, HOJE, tipo))
        con.commit(); con.close()

    def test_ata_tem_chips_e_review_e_sync(self):
        html = self.client.get("/ata/%s/daily" % HOJE).get_data(as_text=True)
        self.assertIn("gl-sync", html)
        self.assertIn("ata-campo-review", html)
        self.assertIn('data-chips-para="review"', html)
        self.assertIn('data-chips-para="planejado"', html)

    def test_eu_tem_campo_review_e_chips(self):
        mid = self.ids()["Arthur"]
        self._presenca_hoje(mid)
        with self.client.session_transaction() as sess:
            sess["eu"] = mid
        html = self.client.get("/eu").get_data(as_text=True)
        self.assertIn("Vou revisar", html)
        self.assertIn('data-chips-para="review"', html)
        self.assertIn("gl-sync", html)

    def test_membros_tem_campo_gitlab(self):
        html = self.client.get("/membros").get_data(as_text=True)
        self.assertIn("input-gitlab", html)
        self.assertIn("Usuário no GitLab", html)

    def test_editar_membro_salva_gitlab_user(self):
        mid = self.ids()["Arthur"]
        r = self.client.post("/api/membros/%d" % mid, json={"gitlab_user": "@arthur.silva "},
                             headers={"X-Requested-With": "fetch"})
        self.assertEqual(r.status_code, 200)
        con = sqlite3.connect(DB)
        gu = con.execute("SELECT gitlab_user FROM members WHERE id = ?", (mid,)).fetchone()[0]
        con.close()
        self.assertEqual(gu, "arthur.silva")   # @ removido, espacos tirados


# ------------------------------------------------------------ export + review nao rende
class TestExportEReview(Base):
    def _ata(self, review=""):
        return {
            "tipo": "daily", "data": HOJE, "relator": "Arthur",
            "present": ["Arthur"], "excused": [],
            "falas": [{"nome": "Arthur", "feito": "#1 feito", "planejado": "#2 fazendo", "review": review}],
            "bloqueios": "", "quadro_atualizado": False,
        }

    def test_export_sem_review_nao_mostra_secao(self):
        for idioma in ("en", "pt"):
            t = ata_fmt.montar_texto(self._ata(), idioma)
            self.assertNotIn("Waiting review", t)
            self.assertNotIn("Em revisão", t)
            h = ata_fmt.montar_html(self._ata(), idioma)
            self.assertNotIn("review", h.lower())

    def test_export_com_review_mostra_secao(self):
        t_en = ata_fmt.montar_texto(self._ata("#9 em revisao"), "en")
        self.assertIn("Waiting review:", t_en)
        self.assertIn("#9 em revisao", t_en)
        t_pt = ata_fmt.montar_texto(self._ata("#9 em revisao"), "pt")
        self.assertIn("Em revisão:", t_pt)

    def test_fechamento_nunca_tem_review(self):
        fech = dict(self._ata("texto"), tipo="fechamento")
        self.assertNotIn("review", ata_fmt.montar_texto(fech, "en").lower())

    def test_review_nao_rende_semente(self):
        # So review preenchido (feito/planejado vazios) -> nao conta como fala com semente.
        mid = self.ids()["Arthur"]
        appmod.app.config.update(TESTING=True)
        with appmod.app.test_request_context():
            db = appmod.get_db()
            appmod._salvar_fala(db, HOJE, "daily", mid, review="#5 revisando")
            db.commit()
            com_fala, _ = appmod._contagem_atas(db, [HOJE])
        self.assertEqual(com_fala.get(mid, 0), 0)

    def test_feito_rende_review_nao_muda(self):
        mid = self.ids()["Bento"]
        with appmod.app.test_request_context():
            db = appmod.get_db()
            appmod._salvar_fala(db, HOJE, "daily", mid, feito="fiz algo", review="#5 revisando")
            db.commit()
            com_fala, _ = appmod._contagem_atas(db, [HOJE])
        self.assertEqual(com_fala.get(mid, 0), 1)   # conta 1 pela fala, review nao soma


# ------------------------------------------------------------ leitor de .env (script)
class TestDotenv(unittest.TestCase):
    def setUp(self):
        # importa o script como modulo pelo caminho
        import importlib.util
        raiz = os.path.join(os.path.dirname(__file__), "..")
        caminho = os.path.join(raiz, "scripts", "sync_gitlab.py")
        spec = importlib.util.spec_from_file_location("sync_gitlab_mod", caminho)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self._tmp = tempfile.mkdtemp()
        self._guardar = {}
        for k in ("GL_A", "GL_B", "GL_C"):
            self._guardar[k] = os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._guardar.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _escrever(self, conteudo):
        p = os.path.join(self._tmp, ".env")
        with open(p, "w", encoding="utf-8") as f:
            f.write(conteudo)
        return p

    def test_le_valores_ignora_comentario_e_aspas(self):
        p = self._escrever('# comentario\nGL_A=valor1\nGL_B="com aspas"\n\nGL_C=\n')
        self.mod.carregar_dotenv(p)
        self.assertEqual(os.environ.get("GL_A"), "valor1")
        self.assertEqual(os.environ.get("GL_B"), "com aspas")

    def test_ambiente_tem_prioridade(self):
        os.environ["GL_A"] = "do-ambiente"
        p = self._escrever("GL_A=do-arquivo\n")
        self.mod.carregar_dotenv(p)
        self.assertEqual(os.environ.get("GL_A"), "do-ambiente")

    def test_sem_arquivo_nao_quebra(self):
        self.assertFalse(self.mod.carregar_dotenv(os.path.join(self._tmp, "nao-existe.env")))


if __name__ == "__main__":
    unittest.main()