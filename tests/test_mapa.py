"""Mapa do jardim (prototipo): a pagina abre com o time e os convidados, e as posicoes dos canteiros
sempre deixam o vao de baixo livre para o caminho de entrada."""
import sqlite3
import unittest

from test_coletivo import DB, ColetivoBase, appmod


class TestPosicoesMapa(unittest.TestCase):
    def test_quantidade_e_vao_embaixo(self):
        cx, cy = appmod.MAPA_CENTRO
        for n in range(1, 13):
            pos = appmod._posicoes_mapa(n)
            self.assertEqual(len(pos), n)
            # nenhum canteiro cai bem em cima do caminho de entrada (abaixo da fonte, no centro)
            for x, y in pos:
                self.assertFalse(abs(x - cx) < 60 and y > cy, (n, x, y))

    def test_vazio(self):
        self.assertEqual(appmod._posicoes_mapa(0), [])


class TestPaginaMapa(ColetivoBase):
    def test_abre_com_um_canteiro_por_pessoa_do_time(self):
        con = sqlite3.connect(DB)
        con.execute("INSERT INTO members (name, active) VALUES ('Ana', 1)")
        con.execute("INSERT INTO members (name, active) VALUES ('Bia', 1)")
        con.commit()
        n_time = con.execute("SELECT COUNT(*) FROM members WHERE active = 1 AND COALESCE(tipo, 'equipe') <> 'convidado'").fetchone()[0]
        con.close()
        r = self.get("/mapa")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertEqual(html.count('class="lote" '), n_time)
        self.assertIn("Ana", html)
        self.assertIn("Bia", html)


if __name__ == "__main__":
    unittest.main()
