import os
import sqlite3
import sys
import tempfile
import unittest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "fase6l.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import app as appmod  # noqa: E402
import ata_fmt  # noqa: E402
import sync_gitlab  # noqa: E402

DB = str(appmod.DB_PATH)
TOKEN = "token-de-teste-123"       # valor FALSO, so para os testes
URL52 = "https://git.inteli.edu.br/graduacao/2026-2b/t24/g01/-/issues/52"


class TestBaseDosLinks(unittest.TestCase):
    def test_vem_do_link_real_de_um_card(self):
        cards = [{"iid": 52, "url": URL52}]
        self.assertEqual(sync_gitlab._base_url_cards("https://git.inteli.edu.br", "123", cards),
                         "https://git.inteli.edu.br/graduacao/2026-2b/t24/g01/-/issues")

    def test_sem_cards_monta_pelo_caminho_do_projeto(self):
        self.assertEqual(sync_gitlab._base_url_cards("https://git.inteli.edu.br/", "graduacao/2026-2b/t24/g01"),
                         "https://git.inteli.edu.br/graduacao/2026-2b/t24/g01/-/issues")

    def test_id_numerico_sem_cards_nao_chuta(self):
        self.assertEqual(sync_gitlab._base_url_cards("https://git.inteli.edu.br", "1234"), "")

    def test_nunca_devolve_a_base_antiga_sem_o_projeto(self):
        base = sync_gitlab._base_url_cards("https://git.inteli.edu.br", "graduacao/2026-2b/t24/g01", [])
        self.assertNotEqual(base, "https://git.inteli.edu.br/-/issues")


class TestLinkNaExportacao(unittest.TestCase):
    def test_usa_a_url_exata_do_card(self):
        h = ata_fmt.etiquetar_cards_html("fiz #52", "https://errado/-/issues", {52: URL52})
        self.assertIn(f'href="{URL52}"', h)
        self.assertNotIn("errado", h)

    def test_sem_url_conhecida_usa_a_base(self):
        h = ata_fmt.etiquetar_cards_html("fiz #7", "https://host/g/p/-/issues", {52: URL52})
        self.assertIn('href="https://host/g/p/-/issues/7"', h)

    def test_sem_nada_vira_so_etiqueta(self):
        h = ata_fmt.etiquetar_cards_html("fiz #7")
        self.assertIn('<span class="card-tag">#7</span>', h)
        self.assertNotIn("href", h)

    def test_montar_html_passa_as_urls(self):
        ata = {"tipo": "daily", "data": "2026-10-28", "relator": "Ana", "present": ["Ana"], "excused": [],
               "falas": [{"nome": "Ana", "feito": "terminei #52", "planejado": ""}], "bloqueios": ""}
        h = ata_fmt.montar_html(ata, "pt", "https://errado/-/issues", {52: URL52})
        self.assertIn(URL52, h)


class TestExportacaoDoSite(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        os.environ["SYNC_TOKEN"] = TOKEN
        self.addCleanup(lambda: os.environ.pop("SYNC_TOKEN", None))
        self.client = appmod.app.test_client()                  # localhost = administrador

    def test_link_certo_mesmo_com_base_antiga_errada(self):
        con = sqlite3.connect(DB)
        con.execute("UPDATE config SET valor = 'https://git.inteli.edu.br/-/issues' WHERE chave = 'gitlab_base_url'")
        mid = con.execute("SELECT MIN(id) FROM members").fetchone()[0]
        con.execute("INSERT OR REPLACE INTO attendance (member_id, event_date, event_type, status) "
                    "VALUES (?, '2026-10-28', 'daily', 'presente')", (mid,))
        con.commit()
        con.close()
        card = {"iid": 52, "coluna": "doing", "usuario": "ana", "titulo": "Algo", "url": URL52, "labels": ""}
        r = self.client.post("/api/gitlab/snapshot", json={"cards": [card], "base_url": ""},
                             headers={"Authorization": "Bearer " + TOKEN})
        self.assertEqual(r.status_code, 200)
        self.client.post("/api/ata/salvar", json={"data": "2026-10-28", "tipo": "daily", "campo": "feito",
                                                  "member_id": mid, "valor": "fechei o #52"})
        h = self.client.get("/ata/2026-10-28/daily/imprimir").get_data(as_text=True)
        self.assertIn(URL52, h)
        self.assertNotIn("git.inteli.edu.br/-/issues/52", h)


if __name__ == "__main__":
    unittest.main()
