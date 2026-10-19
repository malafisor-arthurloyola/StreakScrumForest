import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import backup  # noqa: E402


def _banco(pasta):
    caminho = Path(pasta) / "origem.db"
    con = sqlite3.connect(caminho)
    con.execute("CREATE TABLE t (x INTEGER)")
    con.executemany("INSERT INTO t VALUES (?)", [(1,), (2,), (3,)])
    con.commit()
    con.close()
    return caminho


class TestBackup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.origem = _banco(self.tmp)
        self.pasta = Path(self.tmp) / "backups"

    def test_cria_copia_valida(self):
        destino = backup.fazer_backup(self.origem, self.pasta, hoje=date(2026, 11, 5))
        self.assertEqual(destino.name, "strikes-diario-2026-11-05.db")
        con = sqlite3.connect(destino)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM t").fetchone()[0], 3)
        self.assertEqual(con.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        con.close()

    def test_mesmo_dia_sobrescreve_com_dados_novos(self):
        backup.fazer_backup(self.origem, self.pasta, hoje=date(2026, 11, 5))
        con = sqlite3.connect(self.origem)
        con.execute("INSERT INTO t VALUES (4)")
        con.commit()
        con.close()
        destino = backup.fazer_backup(self.origem, self.pasta, hoje=date(2026, 11, 5))
        con = sqlite3.connect(destino)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM t").fetchone()[0], 4)
        con.close()
        self.assertEqual(len(list(self.pasta.glob("strikes-diario-*.db"))), 1)

    def test_guarda_so_os_ultimos_n(self):
        for dia in range(1, 21):
            backup.fazer_backup(self.origem, self.pasta, manter=14, hoje=date(2026, 11, dia))
        arquivos = sorted(p.name for p in self.pasta.glob("strikes-diario-*.db"))
        self.assertEqual(len(arquivos), 14)
        self.assertEqual(arquivos[0], "strikes-diario-2026-11-07.db")
        self.assertEqual(arquivos[-1], "strikes-diario-2026-11-20.db")

    def test_nao_apaga_outros_arquivos(self):
        self.pasta.mkdir()
        outro = self.pasta / "strikes-pre-migracao-2026-10-17.db"
        outro.write_bytes(b"x")
        for dia in range(1, 20):
            backup.fazer_backup(self.origem, self.pasta, manter=3, hoje=date(2026, 11, dia))
        self.assertTrue(outro.exists())

    def test_origem_inexistente(self):
        with self.assertRaises(FileNotFoundError):
            backup.fazer_backup(Path(self.tmp) / "nao-existe.db", self.pasta)

    def test_nao_toca_na_origem(self):
        antes = self.origem.read_bytes()
        backup.fazer_backup(self.origem, self.pasta)
        self.assertEqual(self.origem.read_bytes(), antes)


if __name__ == "__main__":
    unittest.main()
