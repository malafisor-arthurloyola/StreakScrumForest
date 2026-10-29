import os
import sqlite3
import sys
import tempfile
import unittest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "ata_faltou.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402

DB = str(appmod.DB_PATH)
DATA = "2026-10-29"


class TestAtaFaltou(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        self.client = appmod.app.test_client()
        con = sqlite3.connect(DB)
        self.mid = con.execute("SELECT id FROM members WHERE active = 1 ORDER BY id").fetchone()[0]
        con.close()

    def _status(self, valor):
        return self.client.post("/api/ata/salvar", json={
            "data": DATA, "tipo": "daily", "campo": "status", "member_id": self.mid, "valor": valor})

    def _no_banco(self):
        con = sqlite3.connect(DB)
        try:
            return con.execute("SELECT status FROM attendance WHERE member_id = ? AND event_date = ? AND event_type = 'daily'",
                               (self.mid, DATA)).fetchone()
        finally:
            con.close()

    def test_faltou_grava_e_limpar_apaga(self):
        r = self._status("faltou")
        self.assertEqual((r.status_code, r.get_json()["status"]), (200, "faltou"))
        self.assertEqual(self._no_banco()[0], "faltou")
        self.assertEqual(self._status("").status_code, 200)
        self.assertIsNone(self._no_banco())

    def test_valor_invalido_continua_recusado(self):
        self.assertEqual(self._status("sumiu").status_code, 400)

    def test_a_ata_tem_o_botao_faltou_e_a_rodada_mostra_a_situacao(self):
        h = self.client.get(f"/ata/{DATA}/daily").get_data(as_text=True)
        self.assertIn('data-st="faltou"', h)
        self.assertIn('data-rst="faltou"', h)
        self.assertIn('data-rst="justificada"', h)


class TestHolofote(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        self.client = appmod.app.test_client()
        con = sqlite3.connect(DB)
        self.mid = con.execute("SELECT id FROM members WHERE active = 1 ORDER BY id").fetchone()[0]
        con.close()

    def test_acende_le_e_apaga(self):
        self.assertIsNone(self.client.get("/api/holofote").get_json()["member_id"])
        self.assertEqual(self.client.post("/api/holofote", json={"member_id": self.mid}).status_code, 200)
        self.assertEqual(self.client.get("/api/holofote").get_json()["member_id"], self.mid)
        self.client.post("/api/holofote", json={"member_id": None})
        self.assertIsNone(self.client.get("/api/holofote").get_json()["member_id"])

    def test_pessoa_invalida_e_recusada(self):
        self.assertEqual(self.client.post("/api/holofote", json={"member_id": 99999}).status_code, 400)

    def test_holofote_esquecido_apaga_sozinho(self):
        self.client.post("/api/holofote", json={"member_id": self.mid})
        con = sqlite3.connect(DB)
        con.execute("UPDATE config SET valor = datetime('now', '-4 hours') WHERE chave = 'holofote_em'")
        con.commit()
        con.close()
        self.assertIsNone(self.client.get("/api/holofote").get_json()["member_id"])

    def test_so_o_admin_acende(self):
        os.environ["ADMIN_LOCAL"] = "0"
        try:
            self.assertEqual(self.client.post("/api/holofote", json={"member_id": self.mid}).status_code, 403)
            self.assertEqual(self.client.get("/api/holofote").status_code, 200)       # qualquer um so ve
        finally:
            os.environ.pop("ADMIN_LOCAL", None)


if __name__ == "__main__":
    unittest.main()
