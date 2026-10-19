import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

# O banco de teste e sempre um arquivo temporario; nunca o banco real.
_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "acesso.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402

DB = str(appmod.DB_PATH)
CODIGO = "codigo-de-teste-123"


class AcessoBase(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        appmod.TENTATIVAS.clear()
        self.client = appmod.app.test_client()

    def entrar(self, codigo=CODIGO, destino=None):
        dados = {"codigo": codigo}
        if destino:
            dados["next"] = destino
        return self.client.post("/entrar", data=dados)


class TestSemCodigoConfigurado(AcessoBase):
    """Uso local: sem ACCESS_CODE nada muda."""

    def setUp(self):
        super().setUp()
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("ACCESS_CODE", None)

    def tearDown(self):
        self._env.stop()

    def test_paginas_abrem_sem_login(self):
        for url in ("/dashboard", "/loja", "/historico", "/dia/2026-10-19"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_api_funciona_sem_cabecalho(self):
        r = self.client.post("/api/membros", json={"name": "Teste"})
        self.assertEqual(r.status_code, 200)

    def test_entrar_redireciona_para_home(self):
        r = self.client.get("/entrar")
        self.assertEqual(r.status_code, 302)

    def test_baixar_banco_nao_existe_sem_codigo(self):
        self.assertEqual(self.client.get("/admin/baixar-banco").status_code, 404)


class TestComCodigo(AcessoBase):
    def setUp(self):
        super().setUp()
        self._env = mock.patch.dict(os.environ, {"ACCESS_CODE": CODIGO, "SECRET_KEY": "segredo-de-teste"})
        self._env.start()

    def tearDown(self):
        self._env.stop()

    def test_sem_login_vai_para_a_tela_de_entrada(self):
        r = self.client.get("/dashboard")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/entrar", r.headers["Location"])

    def test_tela_de_entrada_abre(self):
        r = self.client.get("/entrar")
        self.assertEqual(r.status_code, 200)
        self.assertIn("código", r.get_data(as_text=True).lower())

    def test_static_fica_liberado(self):
        r = self.client.get("/static/style.css")
        r.close()
        self.assertEqual(r.status_code, 200)

    def test_api_sem_login_da_401(self):
        r = self.client.post("/api/membros", json={"name": "X"})
        self.assertEqual(r.status_code, 401)

    def test_codigo_errado(self):
        r = self.entrar("errado")
        self.assertEqual(r.status_code, 401)
        self.assertIn("incorreto", r.get_data(as_text=True))
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def test_codigo_certo_libera(self):
        r = self.entrar()
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_volta_para_a_pagina_pedida(self):
        r = self.entrar(destino="/loja")
        self.assertTrue(r.headers["Location"].endswith("/loja"))

    def test_nao_redireciona_para_fora(self):
        r = self.entrar(destino="https://site-malicioso.example/")
        self.assertFalse(r.headers["Location"].startswith("https://site-malicioso"))
        r = self.entrar(destino="//site-malicioso.example/")
        self.assertFalse("site-malicioso" in r.headers["Location"])

    def test_bloqueia_depois_de_5_erros(self):
        for _ in range(4):
            self.assertEqual(self.entrar("errado").status_code, 401)
        self.assertEqual(self.entrar("errado").status_code, 429)
        # mesmo o codigo certo fica bloqueado durante a espera
        self.assertEqual(self.entrar().status_code, 429)

    def test_bloqueio_expira(self):
        for _ in range(5):
            self.entrar("errado")
        for estado in appmod.TENTATIVAS.values():
            estado["bloqueado_ate"] = 0
        self.assertEqual(self.entrar().status_code, 302)

    def test_acerto_zera_os_erros(self):
        for _ in range(3):
            self.entrar("errado")
        self.assertEqual(self.entrar().status_code, 302)
        self.client.get("/sair")
        for _ in range(4):
            self.assertEqual(self.entrar("errado").status_code, 401)

    def test_sair_encerra_a_sessao(self):
        self.entrar()
        self.client.get("/sair")
        self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def test_post_logado_exige_cabecalho(self):
        self.entrar()
        r = self.client.post("/api/membros", json={"name": "Novo"})
        self.assertEqual(r.status_code, 403)
        r = self.client.post("/api/membros", json={"name": "Novo"}, headers={"X-Requested-With": "fetch"})
        self.assertEqual(r.status_code, 200)

    def test_trocar_o_codigo_derruba_sessoes_antigas(self):
        self.entrar()
        with mock.patch.dict(os.environ, {"ACCESS_CODE": "outro-codigo"}):
            self.assertEqual(self.client.get("/dashboard").status_code, 302)

    def test_cookie_de_sessao_e_httponly_e_samesite(self):
        r = self.entrar()
        cookie = r.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

    def test_baixar_banco_exige_login(self):
        self.assertEqual(self.client.get("/admin/baixar-banco").status_code, 302)

    def test_baixar_banco_devolve_um_banco_valido(self):
        self.entrar()
        r = self.client.get("/admin/baixar-banco")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers.get("Content-Disposition", ""))
        copia = os.path.join(_TMP, "baixado.db")
        with open(copia, "wb") as f:
            f.write(r.data)
        con = sqlite3.connect(copia)
        self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertGreater(con.execute("SELECT COUNT(*) FROM members").fetchone()[0], 0)
        con.close()


if __name__ == "__main__":
    unittest.main()
