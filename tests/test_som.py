"""Sons do jardim (static/som.js): carregado em todas as paginas, antes de quem chama Som.tocar,
e sem nenhum som de perda (nunca punir: Faltou e Avisou usam o mesmo toque neutro)."""
import os
import re
import shutil
import subprocess
import unittest

RAIZ = os.path.join(os.path.dirname(__file__), "..")


def ler(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as f:
        return f.read()


class TestSom(unittest.TestCase):
    def test_base_carrega_som_antes_do_app(self):
        base = ler("templates", "base.html")
        self.assertIn("som.css", base)
        self.assertLess(base.index("filename='som.js'"), base.index("filename='app.js'"))

    def test_sem_som_de_perda(self):
        som = ler("static", "som.js")
        bloco = som[som.index("var SONS = {"):som.index("var ultimo = {}")]
        nomes = re.findall(r"^\s{4}(\w+): function", bloco, flags=re.M)
        self.assertIn("neutro", nomes)
        for proibido in ("erro", "falta", "faltou", "perdeu", "triste", "fracasso"):
            self.assertNotIn(proibido, [n.lower() for n in nomes])

    def test_todo_som_chamado_existe(self):
        som = ler("static", "som.js")
        bloco = som[som.index("var SONS = {"):som.index("var ultimo = {}")]
        nomes = set(re.findall(r"^\s{4}(\w+): function", bloco, flags=re.M))
        chamados = set()
        for arq in ("static/app.js", "static/holofote.js", "static/rodada.js", "static/som.js",
                    "templates/eu.html", "templates/loja.html"):
            texto = ler(*arq.split("/"))
            chamados |= set(re.findall(r"(?:Som\.)?tocar\('(\w+)'\)", texto))
            chamados |= set(re.findall(r"'fx-\w+': '(\w+)'", texto))
            for par in re.findall(r"Som\.tocar\([^)]*\? '(\w+)' : '(\w+)'", texto):
                chamados |= set(par)
        self.assertTrue(chamados)
        self.assertEqual(chamados - nomes, set())

    def test_padroes_efeitos_ligados_musica_desligada(self):
        som = ler("static", "som.js")
        self.assertIn("ler(CHAVE_EF, true)", som)
        self.assertIn("ler(CHAVE_MU, false)", som)

    @unittest.skipUnless(shutil.which("node"), "Node nao instalado")
    def test_sintaxe(self):
        r = subprocess.run([shutil.which("node"), "--check", os.path.join(RAIZ, "static", "som.js")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
