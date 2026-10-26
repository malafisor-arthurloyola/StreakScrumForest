import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "fase6u.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import app as appmod  # noqa: E402
import gitlab_sync  # noqa: E402
import sync_gitlab  # noqa: E402

DB = str(appmod.DB_PATH)
TOKEN = "token-de-teste-123"       # valor FALSO, so para os testes


def _u(username, nome):
    return {"username": username, "nome": nome}


# ------------------------------------------------------------ casamento pessoa x usuario (puro)
class TestSugerirMapeamento(unittest.TestCase):
    def test_primeiro_nome_dentro_do_nome_completo(self):
        r = gitlab_sync.sugerir_mapeamento([{"id": 1, "name": "Arthur"}], [_u("arthur.l", "Arthur Loyola")])
        self.assertEqual(r, {1: "arthur.l"})

    def test_ignora_acentos_e_caixa(self):
        r = gitlab_sync.sugerir_mapeamento([{"id": 1, "name": "João"}], [_u("jsilva", "JOAO SILVA")])
        self.assertEqual(r, {1: "jsilva"})

    def test_nome_completo_igual_tem_prioridade(self):
        r = gitlab_sync.sugerir_mapeamento(
            [{"id": 1, "name": "Ana Souza"}],
            [_u("ana.s", "Ana Souza"), _u("ana.m", "Ana Maria Souza Lima")])
        self.assertEqual(r, {1: "ana.s"})

    def test_username_que_contem_o_nome(self):
        r = gitlab_sync.sugerir_mapeamento([{"id": 1, "name": "Heloisa"}], [_u("heloisa.santos", "H. Santos")])
        self.assertEqual(r, {1: "heloisa.santos"})

    def test_ambiguo_nao_adivinha(self):
        r = gitlab_sync.sugerir_mapeamento(
            [{"id": 1, "name": "Ana"}], [_u("a1", "Ana Souza"), _u("a2", "Ana Lima")])
        self.assertEqual(r, {})

    def test_sem_candidato(self):
        self.assertEqual(gitlab_sync.sugerir_mapeamento([{"id": 1, "name": "Zeca"}], [_u("x", "Outro Nome")]), {})

    def test_um_usuario_nunca_vai_para_duas_pessoas(self):
        r = gitlab_sync.sugerir_mapeamento(
            [{"id": 1, "name": "Ana"}, {"id": 2, "name": "Ana"}], [_u("ana.s", "Ana Souza")])
        self.assertEqual(r, {})

    def test_cada_um_com_o_seu(self):
        r = gitlab_sync.sugerir_mapeamento(
            [{"id": 1, "name": "Bruno"}, {"id": 2, "name": "Luiz"}],
            [_u("bruno.a", "Bruno Alves"), _u("luiz.c", "Luiz Costa"), _u("zz", "Zé")])
        self.assertEqual(r, {1: "bruno.a", 2: "luiz.c"})


class TestUsuariosDoProjeto(unittest.TestCase):
    def test_montar_ignora_bloqueados_e_bots(self):
        lista = [
            {"username": "ana", "name": "Ana", "state": "active"},
            {"username": "velho", "name": "Velho", "state": "blocked"},
            {"username": "project_1_bot_abc", "name": "bot", "state": "active"},
            {"username": "", "name": "sem usuario", "state": "active"},
        ]
        self.assertEqual(gitlab_sync.montar_usuarios(lista), [_u("ana", "Ana")])

    def test_validar_usuarios(self):
        self.assertEqual(gitlab_sync.validar_usuarios(None), [])
        self.assertEqual(gitlab_sync.validar_usuarios([_u("a", "A"), _u("a", "A de novo")]), [_u("a", "A")])
        with self.assertRaises(ValueError):
            gitlab_sync.validar_usuarios("nao e lista")
        with self.assertRaises(ValueError):
            gitlab_sync.validar_usuarios([{"nome": "sem username"}])
        with self.assertRaises(ValueError):
            gitlab_sync.validar_usuarios([_u("x" * 5000, "A")])


# ------------------------------------------------------------ rota do snapshot
class TestSnapshotMapeiaSozinho(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        os.environ["SYNC_TOKEN"] = TOKEN
        os.environ.pop("ADMIN_LOCAL", None)
        try:
            appmod.GITLAB_SYNC_ERROS.clear()
        except Exception:
            pass
        self.addCleanup(lambda: os.environ.pop("SYNC_TOKEN", None))
        self.client = appmod.app.test_client()
        con = sqlite3.connect(DB)
        con.execute("DELETE FROM attendance")
        con.execute("DELETE FROM members")
        for nome, tipo in (("Arthur", "equipe"), ("Bruno", "equipe"), ("Camila", "convidado")):
            con.execute("INSERT INTO members (name, active, tipo) VALUES (?, 1, ?)", (nome, tipo))
        con.commit()
        con.close()

    def _gitlab_user(self, nome):
        con = sqlite3.connect(DB)
        r = con.execute("SELECT gitlab_user FROM members WHERE name = ?", (nome,)).fetchone()
        con.close()
        return r[0]

    def _enviar(self, usuarios, cards=None):
        return self.client.post(
            "/api/gitlab/snapshot",
            json={"cards": cards or [], "base_url": "", "usuarios": usuarios},
            headers={"Authorization": "Bearer " + TOKEN},
        )

    def test_liga_as_pessoas_pelo_nome(self):
        r = self._enviar([_u("arthur.l", "Arthur Loyola"), _u("bruno.a", "Bruno Alves"), _u("camila.x", "Camila X")])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["mapeados"], 2)          # o convidado fica de fora
        self.assertEqual(self._gitlab_user("Arthur"), "arthur.l")
        self.assertEqual(self._gitlab_user("Bruno"), "bruno.a")
        self.assertFalse(self._gitlab_user("Camila"))

    def test_nunca_sobrescreve_o_que_o_admin_definiu(self):
        con = sqlite3.connect(DB)
        con.execute("UPDATE members SET gitlab_user = 'escolhido.na.mao' WHERE name = 'Arthur'")
        con.commit()
        con.close()
        self._enviar([_u("arthur.l", "Arthur Loyola")])
        self.assertEqual(self._gitlab_user("Arthur"), "escolhido.na.mao")

    def test_usuario_ja_usado_por_outro_nao_e_repetido(self):
        con = sqlite3.connect(DB)
        con.execute("UPDATE members SET gitlab_user = 'arthur.l' WHERE name = 'Bruno'")
        con.commit()
        con.close()
        self._enviar([_u("arthur.l", "Arthur Loyola")])
        self.assertFalse(self._gitlab_user("Arthur"))

    def test_sem_usuarios_no_retrato_nao_mexe_em_nada(self):
        r = self._enviar([])
        self.assertEqual(r.get_json()["mapeados"], 0)
        self.assertFalse(self._gitlab_user("Arthur"))

    def test_lista_de_usuarios_fica_guardada_para_sugerir_na_tela_membros(self):
        self._enviar([_u("arthur.l", "Arthur Loyola")])
        h = self.client.get("/membros").get_data(as_text=True)         # localhost = admin
        self.assertIn('id="gl-usuarios"', h)
        self.assertIn("arthur.l", h)

    def test_retrato_invalido_de_usuarios_e_recusado(self):
        r = self.client.post("/api/gitlab/snapshot", json={"cards": [], "usuarios": "x"},
                             headers={"Authorization": "Bearer " + TOKEN})
        self.assertEqual(r.status_code, 400)


# ------------------------------------------------------------ script: destinos
class TestDestinos(unittest.TestCase):
    VARS = ("SITE_URL", "SITE_URL_PRODUCAO", "SITE_URL_LOCAL", "SITE_SYNC_TOKEN",
            "SITE_SYNC_TOKEN_LOCAL", "SITE_SYNC_TOKEN_PRODUCAO")

    def _env(self, **kw):
        base = {k: "" for k in self.VARS}
        base.update(kw)
        return mock.patch.dict(os.environ, base, clear=False)

    def test_so_producao(self):
        with self._env(SITE_URL_PRODUCAO="https://p.exemplo", SITE_SYNC_TOKEN="t"):
            self.assertEqual(sync_gitlab.escolher_destinos(None), [("producao", "https://p.exemplo", "t")])

    def test_com_os_dois_o_padrao_e_producao_e_da_para_escolher(self):
        with self._env(SITE_URL_PRODUCAO="https://p.exemplo", SITE_URL_LOCAL="http://localhost:5000", SITE_SYNC_TOKEN="t"):
            self.assertEqual([d[0] for d in sync_gitlab.escolher_destinos(None)], ["producao"])
            self.assertEqual([d[0] for d in sync_gitlab.escolher_destinos("local")], ["local"])
            self.assertEqual([d[0] for d in sync_gitlab.escolher_destinos("ambos")], ["producao", "local"])

    def test_token_proprio_de_cada_destino(self):
        with self._env(SITE_URL_PRODUCAO="https://p", SITE_URL_LOCAL="http://l", SITE_SYNC_TOKEN="geral",
                       SITE_SYNC_TOKEN_LOCAL="so-local"):
            d = {n: t for n, _u, t in sync_gitlab.escolher_destinos("ambos")}
            self.assertEqual(d, {"producao": "geral", "local": "so-local"})

    def test_variavel_antiga_site_url_continua_funcionando(self):
        with self._env(SITE_URL="http://antigo", SITE_SYNC_TOKEN="t"):
            self.assertEqual(sync_gitlab.escolher_destinos(None), [("padrao", "http://antigo", "t")])

    def test_destino_nao_configurado_sai_com_erro(self):
        with self._env(SITE_URL_PRODUCAO="https://p", SITE_SYNC_TOKEN="t"):
            with self.assertRaises(SystemExit):
                sync_gitlab.escolher_destinos("local")

    def test_sem_nenhum_destino_sai_com_erro(self):
        with self._env(SITE_SYNC_TOKEN="t"):
            with self.assertRaises(SystemExit):
                sync_gitlab.escolher_destinos(None)

    def test_falha_de_um_destino_nao_derruba_o_outro(self):
        chamados = []

        def falso_envio(url, token, cards, base, usuarios=None):
            chamados.append(url)
            if "p.exemplo" in url:
                raise sync_gitlab.ErroEnvio("o site recusou a autorizacao.")
            return {"ok": True, "cards": 0}

        issues = []
        with self._env(SITE_URL_PRODUCAO="https://p.exemplo", SITE_URL_LOCAL="http://localhost:5000",
                       SITE_SYNC_TOKEN="t", GITLAB_URL="https://gl", GITLAB_PROJECT="1", GITLAB_TOKEN="x"):
            with mock.patch.object(sync_gitlab, "carregar_dotenv", lambda *a, **k: False), \
                 mock.patch.object(sync_gitlab, "ler_issues_do_gitlab", lambda *a, **k: issues), \
                 mock.patch.object(sync_gitlab, "ler_membros_do_projeto", lambda *a, **k: []), \
                 mock.patch.object(sync_gitlab, "enviar_snapshot", falso_envio):
                codigo = sync_gitlab.main(["--destino", "ambos"])
        self.assertEqual(len(chamados), 2)           # tentou os dois
        self.assertEqual(codigo, 1)                  # mas avisa que um falhou


if __name__ == "__main__":
    unittest.main()
