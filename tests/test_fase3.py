import os
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest import mock
from datetime import date

# O banco de teste e sempre um arquivo temporario; nunca o banco real.
_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "fase3.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import qr_puro  # noqa: E402

DB = str(appmod.DB_PATH)
HOJE = date.today().isoformat()


class Fase3Base(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        appmod.PIN_TENTATIVAS.clear()
        self.client = appmod.app.test_client()

    def ids(self):
        con = sqlite3.connect(DB)
        v = [r[0] for r in con.execute("SELECT id FROM members WHERE active = 1 ORDER BY id")]
        con.close()
        return v

    def set_tipo(self, mid, tipo):
        con = sqlite3.connect(DB)
        con.execute("UPDATE members SET tipo = ? WHERE id = ?", (tipo, mid))
        con.commit()
        con.close()


# ---------------------------------------------------------------- PIN (puro)
class TestPinHash(unittest.TestCase):
    def test_hash_verifica(self):
        h, s = appmod.criar_pin_hash("1234")
        self.assertTrue(appmod.verificar_pin("1234", h, s))
        self.assertFalse(appmod.verificar_pin("0000", h, s))

    def test_salt_aleatorio(self):
        h1, s1 = appmod.criar_pin_hash("1234")
        h2, s2 = appmod.criar_pin_hash("1234")
        self.assertNotEqual(s1, s2)
        self.assertNotEqual(h1, h2)  # sal diferente -> hash diferente

    def test_pin_valido(self):
        self.assertTrue(appmod._pin_valido("0001"))
        self.assertFalse(appmod._pin_valido("123"))
        self.assertFalse(appmod._pin_valido("12a4"))
        self.assertFalse(appmod._pin_valido("12345"))


# ---------------------------------------------------------------- PIN (fluxo /eu)
class TestEuPin(Fase3Base):
    def test_criar_e_entrar(self):
        mid = self.ids()[0]
        r = self.client.post("/eu/criar", json={"member_id": mid, "pin": "1234", "pin2": "1234"})
        self.assertEqual(r.status_code, 200)
        self.client.get("/eu/sair")
        r = self.client.post("/eu/entrar", json={"member_id": mid, "pin": "1234"})
        self.assertEqual(r.status_code, 200)

    def test_criar_pins_diferentes_recusa(self):
        mid = self.ids()[0]
        r = self.client.post("/eu/criar", json={"member_id": mid, "pin": "1234", "pin2": "9999"})
        self.assertEqual(r.status_code, 400)

    def test_criar_pin_curto_recusa(self):
        mid = self.ids()[0]
        r = self.client.post("/eu/criar", json={"member_id": mid, "pin": "12", "pin2": "12"})
        self.assertEqual(r.status_code, 400)

    def test_pin_errado_401(self):
        mid = self.ids()[0]
        self.client.post("/eu/criar", json={"member_id": mid, "pin": "1234", "pin2": "1234"})
        self.client.get("/eu/sair")
        r = self.client.post("/eu/entrar", json={"member_id": mid, "pin": "0000"})
        self.assertEqual(r.status_code, 401)

    def test_bloqueio_apos_5_erros(self):
        mid = self.ids()[0]
        self.client.post("/eu/criar", json={"member_id": mid, "pin": "1234", "pin2": "1234"})
        self.client.get("/eu/sair")
        for _ in range(5):
            self.client.post("/eu/entrar", json={"member_id": mid, "pin": "0000"})
        # 6a tentativa (mesmo com PIN certo) deve estar bloqueada
        r = self.client.post("/eu/entrar", json={"member_id": mid, "pin": "1234"})
        self.assertEqual(r.status_code, 429)

    def test_dono_reseta_pin(self):
        mid = self.ids()[0]
        self.client.post("/eu/criar", json={"member_id": mid, "pin": "1234", "pin2": "1234"})
        self.client.post(f"/api/membros/{mid}", json={"resetar_pin": True})
        con = sqlite3.connect(DB)
        ph = con.execute("SELECT pin_hash FROM members WHERE id = ?", (mid,)).fetchone()[0]
        con.close()
        self.assertIsNone(ph)
        # entrar com o PIN antigo nao funciona mais
        self.assertEqual(self.client.post("/eu/entrar", json={"member_id": mid, "pin": "1234"}).status_code, 400)


# ---------------------------------------------------------------- codigo HMAC do QR
class TestCodigoEvento(unittest.TestCase):
    def test_janela_atual_e_anterior(self):
        t = 1_000_000
        cod = appmod.codigo_do_evento("2026-10-19", "daily", agora=t)
        self.assertTrue(appmod.verificar_codigo_evento(cod, "2026-10-19", "daily", agora=t))
        self.assertTrue(appmod.verificar_codigo_evento(cod, "2026-10-19", "daily", agora=t + 600))

    def test_expira_depois_de_duas_janelas(self):
        t = 1_000_000
        cod = appmod.codigo_do_evento("2026-10-19", "daily", agora=t)
        self.assertFalse(appmod.verificar_codigo_evento(cod, "2026-10-19", "daily", agora=t + 1300))

    def test_outro_evento_e_outro_dia_rejeitados(self):
        t = 1_000_000
        cod = appmod.codigo_do_evento("2026-10-19", "daily", agora=t)
        self.assertFalse(appmod.verificar_codigo_evento(cod, "2026-10-19", "dev", agora=t))
        self.assertFalse(appmod.verificar_codigo_evento(cod, "2026-10-20", "daily", agora=t))


# ---------------------------------------------------------------- QR puro (estrutura)
class TestQrPuro(unittest.TestCase):
    def _finder(self, mat, r0, c0):
        # anel externo escuro 7x7, anel interno claro, centro 3x3 escuro
        for i in range(7):
            if not (mat[r0][c0 + i] and mat[r0 + 6][c0 + i] and mat[r0 + i][c0] and mat[r0 + i][c0 + 6]):
                return False
        return mat[r0 + 3][c0 + 3]

    def test_quadrada_e_tamanho_por_versao(self):
        mat, n = qr_puro.fazer_matriz("ABC123")
        self.assertEqual(len(mat), n)
        self.assertTrue(all(len(linha) == n for linha in mat))
        self.assertEqual(n, 21)  # versao 1
        self.assertEqual((n - 17) % 4, 0)

    def test_tres_finder_patterns(self):
        mat, n = qr_puro.fazer_matriz("ABC123")
        self.assertTrue(self._finder(mat, 0, 0))
        self.assertTrue(self._finder(mat, 0, n - 7))
        self.assertTrue(self._finder(mat, n - 7, 0))

    def test_deterministico(self):
        a, _ = qr_puro.fazer_matriz("http://x/presenca/daily/abcd012345")
        b, _ = qr_puro.fazer_matriz("http://x/presenca/daily/abcd012345")
        self.assertEqual(a, b)

    def test_versao_cresce_com_texto(self):
        _, n1 = qr_puro.fazer_matriz("ABC123")
        _, n2 = qr_puro.fazer_matriz("x" * 100)
        self.assertGreater(n2, n1)

    def test_svg_valido(self):
        s = qr_puro.svg("http://x/presenca/daily/abcd012345")
        self.assertTrue(s.startswith("<svg"))
        self.assertIn("</svg>", s)
        self.assertIn("<rect", s)


# ---------------------------------------------------------------- QR + presenca (rotas)
class TestPresenca(Fase3Base):
    def _logar(self, mid, pin="1234"):
        self.client.post("/eu/criar", json={"member_id": mid, "pin": pin, "pin2": pin})

    def test_qr_mostra_svg_e_url(self):
        r = self.client.get("/qr/daily")
        self.assertEqual(r.status_code, 200)
        h = r.get_data(as_text=True)
        self.assertIn("<svg", h)
        self.assertIn("/presenca/daily/", h)

    def test_qr_em_producao_usa_o_endereco_do_site_nao_o_ip_da_maquina(self):
        # fora de localhost (ex.: PythonAnywhere) o QR deve apontar para o proprio dominio
        with self.client.session_transaction(base_url="https://time.pythonanywhere.com") as sess:
            sess["admin"] = True        # em producao o QR e do administrador
        r = self.client.get("/qr/daily", base_url="https://time.pythonanywhere.com")
        h = r.get_data(as_text=True)
        self.assertIn("https://time.pythonanywhere.com/presenca/daily/", h)

    def test_qr_evento_invalido_404(self):
        self.assertEqual(self.client.get("/qr/xyz").status_code, 404)

    def test_sem_login_pede_login(self):
        cod = appmod.codigo_do_evento(HOJE, "daily")
        h = self.client.get(f"/presenca/daily/{cod}").get_data(as_text=True)
        self.assertIn("Entre primeiro", h)

    def test_codigo_invalido_expirado(self):
        self._logar(self.ids()[0])
        h = self.client.get("/presenca/daily/0000000000").get_data(as_text=True)
        self.assertIn("xpirado", h)

    def test_marca_presente_idempotente(self):
        mid = self.ids()[0]
        self._logar(mid)
        cod = appmod.codigo_do_evento(HOJE, "daily")
        self.assertEqual(self.client.post(f"/presenca/daily/{cod}", json={}).status_code, 200)
        self.client.post(f"/presenca/daily/{cod}", json={})  # de novo
        con = sqlite3.connect(DB)
        linhas = con.execute(
            "SELECT status FROM attendance WHERE member_id = ? AND event_date = ? AND event_type = 'daily'",
            (mid, HOJE),
        ).fetchall()
        con.close()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0][0], "presente")

    def test_nao_marca_outro_membro(self):
        mid, outro = self.ids()[0], self.ids()[1]
        self._logar(mid)
        cod = appmod.codigo_do_evento(HOJE, "daily")
        self.client.post(f"/presenca/daily/{cod}", json={})
        con = sqlite3.connect(DB)
        n = con.execute("SELECT COUNT(*) FROM attendance WHERE member_id = ?", (outro,)).fetchone()[0]
        con.close()
        self.assertEqual(n, 0)

    def test_nunca_marca_faltou(self):
        mid = self.ids()[0]
        self._logar(mid)
        cod = appmod.codigo_do_evento(HOJE, "daily")
        self.client.post(f"/presenca/daily/{cod}", json={})
        con = sqlite3.connect(DB)
        st = con.execute(
            "SELECT status FROM attendance WHERE member_id = ? AND event_date = ?", (mid, HOJE)
        ).fetchone()[0]
        con.close()
        self.assertEqual(st, "presente")

    def test_convidado_marca_por_qr_e_fica_fora_do_time(self):
        conv = self.ids()[-1]
        self.set_tipo(conv, "convidado")
        self._logar(conv)
        cod = appmod.codigo_do_evento(HOJE, "daily")
        self.assertEqual(self.client.post(f"/presenca/daily/{cod}", json={}).status_code, 200)
        with appmod.app.test_request_context():
            ctx = appmod._base_coletivo(appmod.get_db())
        self.assertNotIn(conv, [m["id"] for m in ctx["ativos"]])
        self.assertIn(conv, [m["id"] for m in ctx["convidados"]])


# ---------------------------------------------------------------- QR/presenca v2: data e fala
class TestPresencaDataEFala(Fase3Base):
    def setUp(self):
        super().setUp()
        # usa o Dev/encerramento de hoje (relogio real); numa sexta eles nao existem
        sexta = mock.patch.object(appmod.game, "DIAS_SO_DAILY", ())
        sexta.start()
        self.addCleanup(sexta.stop)

    def _logar(self, mid, pin="1234"):
        self.client.post("/eu/criar", json={"member_id": mid, "pin": pin, "pin2": pin})

    def _fala(self, mid, tipo="daily"):
        con = sqlite3.connect(DB)
        r = con.execute("SELECT feito, planejado FROM ata_falas WHERE data=? AND tipo=? AND member_id=?",
                        (HOJE, tipo, mid)).fetchone()
        con.close()
        return r

    def test_qr_mostra_a_data_por_extenso(self):
        h = self.client.get("/qr/daily").get_data(as_text=True)
        self.assertIn(str(date.today().year), h)
        self.assertIn(str(date.today().day), h)

    def test_tela_de_presenca_mostra_a_data_e_as_duas_opcoes(self):
        self._logar(self.ids()[0])
        cod = appmod.codigo_do_evento(HOJE, "daily")
        h = self.client.get(f"/presenca/daily/{cod}").get_data(as_text=True)
        self.assertIn(str(date.today().year), h)
        self.assertIn("Marcar presença", h)
        self.assertIn("Preencher a", h)
        self.assertIn("+1 semente", h)

    def test_dev_nao_tem_opcao_de_preencher(self):
        self._logar(self.ids()[0])
        cod = appmod.codigo_do_evento(HOJE, "dev")
        h = self.client.get(f"/presenca/dev/{cod}").get_data(as_text=True)
        self.assertIn("Marcar presença", h)
        self.assertNotIn('id="pf-feito"', h)

    def test_marcar_e_preencher_grava_presenca_e_fala(self):
        mid = self.ids()[0]
        self._logar(mid)
        cod = appmod.codigo_do_evento(HOJE, "daily")
        r = self.client.post(f"/presenca/daily/{cod}", json={"fala": {"feito": "fiz #12", "planejado": "vou testar"}})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ganhou_ata"])
        self.assertEqual(self._fala(mid), ("fiz #12", "vou testar"))
        con = sqlite3.connect(DB)
        st = con.execute("SELECT status FROM attendance WHERE member_id=? AND event_date=? AND event_type='daily'",
                         (mid, HOJE)).fetchone()[0]
        con.close()
        self.assertEqual(st, "presente")

    def test_so_marcar_presenca_nao_cria_fala(self):
        mid = self.ids()[0]
        self._logar(mid)
        cod = appmod.codigo_do_evento(HOJE, "daily")
        self.client.post(f"/presenca/daily/{cod}", json={})
        self.assertIsNone(self._fala(mid))

    def test_ja_presente_ainda_pode_preencher_a_daily(self):
        mid = self.ids()[0]
        self._logar(mid)
        cod = appmod.codigo_do_evento(HOJE, "daily")
        self.client.post(f"/presenca/daily/{cod}", json={})
        h = self.client.get(f"/presenca/daily/{cod}").get_data(as_text=True)
        self.assertIn("já está registrada", h)
        self.assertIn("Preencher a", h)
        self.client.post(f"/presenca/daily/{cod}", json={"fala": {"feito": "depois eu escrevi", "planejado": ""}})
        self.assertEqual(self._fala(mid)[0], "depois eu escrevi")

    def test_encerramento_grava_na_ata_de_fechamento(self):
        mid = self.ids()[0]
        self._logar(mid)
        cod = appmod.codigo_do_evento(HOJE, "encerramento")
        self.client.post(f"/presenca/encerramento/{cod}", json={"fala": {"feito": "concluí", "planejado": ""}})
        self.assertEqual(self._fala(mid, "fechamento")[0], "concluí")

    def test_fala_vazia_nao_conta(self):
        mid = self.ids()[0]
        self._logar(mid)
        cod = appmod.codigo_do_evento(HOJE, "daily")
        r = self.client.post(f"/presenca/daily/{cod}", json={"fala": {"feito": "  ", "planejado": ""}})
        self.assertFalse(r.get_json()["ganhou_ata"])
        self.assertIsNone(self._fala(mid))


if __name__ == "__main__":
    unittest.main()
