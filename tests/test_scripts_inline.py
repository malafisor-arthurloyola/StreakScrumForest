"""Rede de seguranca: todo <script> inline dos templates precisa ser JavaScript valido.

Um erro de sintaxe num desses scripts derruba a pagina inteira em silencio (os botoes
simplesmente nao fazem nada). Usa o Node para conferir quando ele existe; sem Node, o teste e pulado.
"""
import glob
import os
import re
import shutil
import subprocess
import sqlite3
import sys
import tempfile
import unittest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "scripts.db"))
RAIZ = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, RAIZ)
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "Node nao instalado: nao da para conferir a sintaxe do JavaScript")
class TestScriptsInline(unittest.TestCase):
    def _checar(self, codigo, origem):
        with tempfile.TemporaryDirectory() as pasta:
            arq = os.path.join(pasta, "t.js")
            with open(arq, "w", encoding="utf-8") as f:
                f.write(codigo)
            r = subprocess.run([NODE, "--check", arq], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{origem}: {r.stderr.strip()[:300]}")

    def test_scripts_inline_dos_templates_sem_jinja(self):
        for caminho in sorted(glob.glob(os.path.join(RAIZ, "templates", "*.html"))):
            with open(caminho, encoding="utf-8") as f:
                texto = f.read()
            for i, bloco in enumerate(re.findall(r"<script>(.*?)</script>", texto, flags=re.S)):
                if "{%" in bloco or "{{" in bloco:
                    continue    # tem Jinja: so da para checar renderizado (veja o teste abaixo)
                self._checar(bloco, f"{os.path.basename(caminho)} (script {i})")

    def test_scripts_das_paginas_renderizadas(self):
        """Confere tambem os scripts que usam Jinja, ja renderizados (ata, presenca, eu, loja...)."""
        import app as appmod
        db_path = str(appmod.DB_PATH)
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(db_path + ext):
                os.remove(db_path + ext)
        appmod.init_db()
        con = sqlite3.connect(db_path)
        mid = con.execute("SELECT id FROM members ORDER BY id LIMIT 1").fetchone()[0]
        con.close()
        cliente = appmod.app.test_client()                  # localhost = administrador
        codigo = appmod.codigo_do_evento("2026-10-19", "daily")
        with cliente.session_transaction() as sess:
            sess["eu"] = mid
        urls = ["/dia/2026-10-19", "/dashboard", "/historico", "/membros", "/calendario", f"/loja?m={mid}",
                "/sementes", "/album", "/sprint/1", "/ata/2026-10-19/daily", "/ata/2026-10-19/fechamento",
                "/ata/2026-10-19/daily/imprimir", "/ata/sprint/1", "/eu", f"/membro/{mid}", "/qr/daily"]
        for url in urls:
            r = cliente.get(url)
            self.assertLess(r.status_code, 400, url)
            html = r.get_data(as_text=True)
            for i, bloco in enumerate(re.findall(r"<script>(.*?)</script>", html, flags=re.S)):
                self._checar(bloco, f"{url} (script {i})")
        # a pagina de presenca so renderiza com o codigo certo do dia de HOJE
        from datetime import date
        hoje = date.today().isoformat()
        cod = appmod.codigo_do_evento(hoje, "daily")
        html = cliente.get(f"/presenca/daily/{cod}").get_data(as_text=True)
        for i, bloco in enumerate(re.findall(r"<script>(.*?)</script>", html, flags=re.S)):
            self._checar(bloco, f"/presenca (script {i})")

    def test_app_js(self):
        with open(os.path.join(RAIZ, "static", "app.js"), encoding="utf-8") as f:
            self._checar(f.read(), "static/app.js")


if __name__ == "__main__":
    unittest.main()
