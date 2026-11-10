"""Quem entra com o PIN e nao edita a ata (nem admin nem relator) escreve a PROPRIA fala na ata.

O JavaScript so salva a linha marcada com data-minha="1". Um escape do Jinja ja deixou o
atributo como data-minha="&#34;1&#34;" e o texto nunca era enviado: parecia salvo, mas sumia."""
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "ata_minha.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402

DB = str(appmod.DB_PATH)
DATA = "2026-10-29"


class TestAtaMinhaLinha(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        p = mock.patch.dict(os.environ, {"ADMIN_LOCAL": "0"})     # sem "computador" admin
        p.start()
        self.addCleanup(p.stop)
        self.client = appmod.app.test_client()
        con = sqlite3.connect(DB)
        self.mid = con.execute("SELECT id FROM members WHERE active = 1 ORDER BY id").fetchone()[0]
        con.close()
        with self.client.session_transaction() as s:
            s["eu"] = self.mid

    def _linha(self, tipo):
        h = self.client.get(f"/ata/{DATA}/{tipo}").get_data(as_text=True)
        self.assertIn('data-pode-editar="0"', h)
        m = re.search(r'<article class="ata-linha[^"]*" data-member-id="%d"[^>]*>' % self.mid, h)
        self.assertIsNotNone(m)
        return m.group(0)

    def test_a_propria_linha_sai_marcada_com_data_minha_1(self):
        for tipo in ("daily", "fechamento"):
            with self.subTest(tipo=tipo):
                self.assertIn(' data-minha="1"', self._linha(tipo))

    def test_linha_de_outra_pessoa_nao_e_minha(self):
        with self.client.session_transaction() as s:
            s["eu"] = self.mid + 1
        self.assertNotIn("data-minha", self._linha("daily"))


if __name__ == "__main__":
    unittest.main()
