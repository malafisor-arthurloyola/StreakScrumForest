import os
import sqlite3
import sys
import tempfile
import unittest

# O banco de teste e sempre um arquivo temporario; nunca o banco real.
_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "teste.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402

DB = str(appmod.DB_PATH)


def _dias():
    return game.dias_letivos("2026-10-15", "2026-10-12", 10,
                             {"2026-10-12", "2026-11-02", "2026-11-20"})


class LojaBase(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        self.client = appmod.app.test_client()
        self.dias = _dias()

    def presencas(self, member_id, n, eventos=("daily",)):
        con = sqlite3.connect(DB)
        for d in self.dias[:n]:
            for ev in eventos:
                con.execute(
                    "INSERT INTO attendance (member_id, event_date, event_type, status) VALUES (?,?,?,?)",
                    (member_id, d, ev, "presente"),
                )
        con.commit()
        con.close()

    def stats(self, member_id):
        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row
        try:
            return next(s for s in appmod.get_member_stats(con) if s["id"] == member_id)
        finally:
            con.close()

    def entrar_como(self, member_id):
        """A loja e de cada um: entra no jardim da pessoa (sessao) antes de mexer nela."""
        with self.client.session_transaction() as sess:
            sess["eu"] = member_id

    def post(self, url, **dados):
        if url.startswith("/api/loja/") and isinstance(dados.get("member_id"), int):
            self.entrar_como(dados["member_id"])
        return self.client.post(url, json=dados)

    def comprar(self, member_id, item_id):
        return self.post("/api/loja/comprar", member_id=member_id, item_id=item_id)

    def equipar(self, member_id, slot, item_id):
        return self.post("/api/loja/equipar", member_id=member_id, slot=slot, item_id=item_id)


class TestSementes(LojaBase):
    def test_sem_presenca_sem_sementes(self):
        s = self.stats(1)
        self.assertEqual(s["sementes"], 0)

    def test_sementes_crescem_com_presenca(self):
        self.presencas(1, 10)
        s = self.stats(1)
        # 10 presencas + 1 semana fechada (3) + marcos 5 e 10 (3+5) + boas-vindas (20)
        self.assertEqual(s["sementes_ganhas"], 41)
        self.assertEqual(s["sementes"], 41)

    def test_resposta_da_presenca_traz_sementes(self):
        r = self.post("/api/attendance", member_id=1, event_date=self.dias[0],
                      event_type="daily", status="presente")
        self.assertEqual(r.status_code, 200)
        self.assertIn("sementes", r.get_json()["jogo"])


class TestSementesPorEvento(LojaBase):
    def test_cada_evento_rende_uma_semente(self):
        self.presencas(1, 1, ("daily",))
        self.presencas(2, 1, ("daily", "dev", "encerramento"))
        self.assertEqual(self.stats(2)["sementes_ganhas"], self.stats(1)["sementes_ganhas"] + 2)

    def test_dev_e_encerramento_sozinhos_tambem_rendem(self):
        self.presencas(1, 1, ("dev",))
        self.presencas(2, 1, ("encerramento",))
        self.assertEqual(self.stats(1)["sementes_ganhas"], self.stats(2)["sementes_ganhas"])
        self.assertGreater(self.stats(1)["sementes_ganhas"], 0)

    def test_crescimento_continua_por_dia(self):
        self.presencas(1, 3, ("daily",))
        self.presencas(2, 3, ("daily", "dev", "encerramento"))
        self.assertEqual(self.stats(1)["g"], self.stats(2)["g"])


class TestCompra(LojaBase):
    def test_comprar_desconta_do_saldo(self):
        self.presencas(1, 20)
        antes = self.stats(1)["sementes"]
        r = self.comprar(1, "girassol")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.stats(1)["sementes"], antes - 40)

    def test_sem_saldo_nao_compra(self):
        r = self.comprar(2, "girassol")
        self.assertEqual(r.status_code, 400)
        self.assertIn("semente", r.get_json()["erro"])

    def test_nao_compra_duas_vezes(self):
        self.presencas(1, 20)
        self.assertEqual(self.comprar(1, "girassol").status_code, 200)
        self.assertEqual(self.comprar(1, "girassol").status_code, 400)

    def test_baoba_bloqueado_sem_florescer(self):
        self.presencas(1, 30)
        self.assertEqual(self.comprar(1, "baoba").status_code, 400)

    def test_item_inexistente(self):
        self.assertEqual(self.comprar(1, "fantasma").status_code, 400)

    def test_membro_inexistente(self):
        self.assertEqual(self.comprar(999, "laco").status_code, 404)


class TestEquipar(LojaBase):
    def test_equipar_exige_posse(self):
        r = self.equipar(1, "especie", "girassol")
        self.assertEqual(r.status_code, 400)

    def test_equipar_e_aparecer_no_visual(self):
        self.presencas(1, 20)
        self.comprar(1, "girassol")
        self.assertEqual(self.equipar(1, "especie", "girassol").status_code, 200)
        v = self.stats(1)["visual"]
        self.assertEqual(v["especie"], "girassol")
        self.assertEqual(v["vaso"], "terracota")

    def test_voltar_ao_padrao(self):
        self.presencas(1, 20)
        self.comprar(1, "girassol")
        self.equipar(1, "especie", "girassol")
        self.assertEqual(self.equipar(1, "especie", "muda").status_code, 200)
        self.assertEqual(self.stats(1)["visual"]["especie"], "muda")

    def test_desequipar_companheiro(self):
        self.presencas(1, 20)
        self.comprar(1, "joaninha")
        self.equipar(1, "companheiro", "joaninha")
        self.assertEqual(self.stats(1)["visual"]["companheiro"], "joaninha")
        r = self.equipar(1, "companheiro", None)
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(self.stats(1)["visual"]["companheiro"])

    def test_segunda_planta(self):
        self.presencas(1, 30, ("daily", "dev", "encerramento"))
        self.assertEqual(self.comprar(1, "slot_2").status_code, 200)
        self.comprar(1, "samambaia")
        self.assertEqual(self.equipar(1, "especie_2", "samambaia").status_code, 200)
        extras = self.stats(1)["visual"]["extras"]
        self.assertEqual(len(extras), 1)
        self.assertEqual(extras[0]["especie"], "samambaia")

    def test_segunda_planta_exige_slot(self):
        self.presencas(1, 30)
        self.comprar(1, "samambaia")
        self.assertEqual(self.equipar(1, "especie_2", "samambaia").status_code, 400)


class TestDesfazer(LojaBase):
    def _compra_id(self, member_id, item_id):
        con = sqlite3.connect(DB)
        row = con.execute(
            "SELECT id FROM compras WHERE member_id=? AND item_id=? AND desfeita_em IS NULL",
            (member_id, item_id),
        ).fetchone()
        con.close()
        return row[0]

    def test_desfazer_devolve_sementes(self):
        self.presencas(1, 20)
        antes = self.stats(1)["sementes"]
        self.comprar(1, "girassol")
        cid = self._compra_id(1, "girassol")
        r = self.post("/api/loja/desfazer", member_id=1, compra_id=cid)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.stats(1)["sementes"], antes)

    def test_desfazer_desequipa(self):
        self.presencas(1, 20)
        self.comprar(1, "girassol")
        self.equipar(1, "especie", "girassol")
        self.post("/api/loja/desfazer", member_id=1, compra_id=self._compra_id(1, "girassol"))
        self.assertEqual(self.stats(1)["visual"]["especie"], "muda")

    def test_pode_comprar_de_novo_depois_de_desfazer(self):
        self.presencas(1, 20)
        self.comprar(1, "girassol")
        self.post("/api/loja/desfazer", member_id=1, compra_id=self._compra_id(1, "girassol"))
        self.assertEqual(self.comprar(1, "girassol").status_code, 200)

    def test_nao_desfaz_slot_2_com_slot_3(self):
        self.presencas(1, 45, ("daily", "dev", "encerramento"))
        self.assertEqual(self.comprar(1, "slot_2").status_code, 200)
        self.assertEqual(self.comprar(1, "slot_3").status_code, 200)
        r = self.post("/api/loja/desfazer", member_id=1, compra_id=self._compra_id(1, "slot_2"))
        self.assertEqual(r.status_code, 400)

    def test_nao_desfaz_compra_de_outro_membro(self):
        self.presencas(1, 20)
        self.comprar(1, "girassol")
        r = self.post("/api/loja/desfazer", member_id=2, compra_id=self._compra_id(1, "girassol"))
        self.assertEqual(r.status_code, 404)


class TestPaginas(LojaBase):
    def test_loja_abre_sem_membro(self):
        self.assertEqual(self.client.get("/loja").status_code, 200)

    def test_loja_abre_com_membro(self):
        self.presencas(1, 10)
        r = self.client.get("/loja?m=1")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Girassol", r.get_data(as_text=True))

    def test_album_abre(self):
        self.assertEqual(self.client.get("/album?m=1").status_code, 200)

    def test_hoje_e_painel_abrem_com_itens_equipados(self):
        self.presencas(1, 30)
        self.comprar(1, "slot_2")
        self.comprar(1, "gato")
        self.equipar(1, "companheiro", "gato")
        self.assertEqual(self.client.get("/dia/2026-10-19").status_code, 200)
        self.assertEqual(self.client.get("/dashboard").status_code, 200)


class TestExcluirMembro(LojaBase):
    def test_excluir_membro_com_compras(self):
        self.presencas(1, 20)
        self.comprar(1, "girassol")
        self.equipar(1, "especie", "girassol")
        nome = self.stats(1)["name"]
        r = self.post("/api/membros/1/excluir", confirmar_nome=nome)
        self.assertEqual(r.status_code, 200)
        con = sqlite3.connect(DB)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM compras WHERE member_id=1").fetchone()[0], 0)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM equipados WHERE member_id=1").fetchone()[0], 0)
        con.close()


if __name__ == "__main__":
    unittest.main()
