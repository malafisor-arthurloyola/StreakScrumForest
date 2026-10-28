import os
import sqlite3
import sys
import tempfile
import unittest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "relator.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402

DB = str(appmod.DB_PATH)
DATA = "2026-10-19"          # dia letivo


class Base(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        self.client = appmod.app.test_client()          # localhost = administrador
        con = sqlite3.connect(DB)
        self.ids = [r[0] for r in con.execute("SELECT id FROM members WHERE active = 1 ORDER BY id")]
        con.close()
        self.a, self.b, self.c = self.ids[:3]

    def salvar(self, **p):
        return self.client.post("/api/ata/salvar", json=p)

    def relator(self, quem, tipo="daily"):
        self.salvar(data=DATA, tipo=tipo, campo="relator", valor=quem)

    def pelo_relator(self, quem, texto="algo", tipo="daily", campo="feito"):
        self.salvar(data=DATA, tipo=tipo, campo=campo, member_id=quem, valor=texto)

    def contagem(self):
        with appmod.app.test_request_context():
            db = appmod.get_db()
            return appmod._contagem_atas(db, appmod._dias_letivos(db))

    def entrar_como(self, mid):
        with self.client.session_transaction() as sess:
            sess["eu"] = mid

    def origem(self, mid, tipo="daily"):
        con = sqlite3.connect(DB)
        r = con.execute("SELECT origem FROM ata_falas WHERE data = ? AND tipo = ? AND member_id = ?",
                        (DATA, tipo, mid)).fetchone()
        con.close()
        return r[0] if r else None


class TestBonusDoRelator(Base):
    def test_uma_semente_por_fala_de_outra_pessoa(self):
        self.relator(self.a)
        self.pelo_relator(self.b)
        self.pelo_relator(self.c)                       # Guilherme e Pablo, no exemplo do dono
        _, rel = self.contagem()
        self.assertEqual(rel.get(self.a), 2)

    def test_a_propria_fala_do_relator_rende_so_o_bonus_normal(self):
        self.relator(self.a)
        self.pelo_relator(self.a)                       # ele preenche a dele
        com_fala, rel = self.contagem()
        self.assertEqual(com_fala.get(self.a), 1)        # +SEED_ATA normal
        self.assertEqual(rel.get(self.a, 0), 0)          # nada de bonus de relator por si mesmo

    def test_valor_no_saldo(self):
        self.relator(self.a)
        self.pelo_relator(self.a)
        self.pelo_relator(self.b)
        self.pelo_relator(self.c)
        with appmod.app.test_request_context():
            db = appmod.get_db()
            stats = next(s for s in appmod.get_member_stats(db) if s["id"] == self.a)
        # 1 pela propria fala + 2 por ter preenchido a de dois colegas
        base = game.SEED_ATA * 1 + game.SEED_RELATOR * 2
        self.assertGreaterEqual(stats["sementes_ganhas"], base)

    def test_fala_vazia_nao_conta(self):
        self.relator(self.a)
        self.pelo_relator(self.b, texto="   ")
        _, rel = self.contagem()
        self.assertEqual(rel.get(self.a, 0), 0)

    def test_sem_relator_ninguem_ganha(self):
        self.pelo_relator(self.b)
        _, rel = self.contagem()
        self.assertEqual(rel, {})

    def test_daily_e_day_closing_contam_separado(self):
        self.relator(self.a, "daily")
        self.relator(self.a, "fechamento")
        self.pelo_relator(self.b, tipo="daily")
        self.pelo_relator(self.b, tipo="fechamento")
        _, rel = self.contagem()
        self.assertEqual(rel.get(self.a), 2)

    def test_so_conta_uma_vez_por_pessoa_e_ata(self):
        self.relator(self.a)
        self.pelo_relator(self.b, campo="feito")
        self.pelo_relator(self.b, campo="planejado")    # mesma fala, outro campo
        _, rel = self.contagem()
        self.assertEqual(rel.get(self.a), 1)

    def test_dia_nao_letivo_nao_rende(self):
        sabado = "2026-10-24"
        self.salvar(data=sabado, tipo="daily", campo="relator", valor=self.a)
        self.salvar(data=sabado, tipo="daily", campo="feito", member_id=self.b, valor="x")
        _, rel = self.contagem()
        self.assertEqual(rel.get(self.a, 0), 0)


class TestQuemEscreveu(Base):
    def test_fala_escrita_pelo_relator_fica_marcada(self):
        self.relator(self.a)
        self.pelo_relator(self.b)
        self.assertEqual(self.origem(self.b), "relator")

    def test_fala_escrita_pela_propria_pessoa_nao_da_bonus_ao_relator(self):
        self.relator(self.a)
        self.entrar_como(self.b)
        r = self.client.post("/api/ata/minha-fala", json={"data": DATA, "tipo": "daily", "campo": "feito",
                                                          "valor": "escrevi eu mesmo"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.origem(self.b), "proprio")
        _, rel = self.contagem()
        self.assertEqual(rel.get(self.a, 0), 0)

    def test_o_ultimo_a_escrever_decide(self):
        self.relator(self.a)
        self.entrar_como(self.b)
        self.client.post("/api/ata/minha-fala", json={"data": DATA, "tipo": "daily", "campo": "feito", "valor": "meu"})
        self.pelo_relator(self.b, texto="meu, completado pelo relator")
        self.assertEqual(self.contagem()[1].get(self.a), 1)
        self.client.post("/api/ata/minha-fala", json={"data": DATA, "tipo": "daily", "campo": "feito", "valor": "meu de novo"})
        self.assertEqual(self.contagem()[1].get(self.a, 0), 0)

    def test_falas_antigas_sem_marca_contam(self):
        self.relator(self.a)
        con = sqlite3.connect(DB)
        con.execute("INSERT INTO ata_falas (data, tipo, member_id, feito, planejado, origem) "
                    "VALUES (?, 'daily', ?, 'antiga', '', '')", (DATA, self.b))
        con.commit()
        con.close()
        self.assertEqual(self.contagem()[1].get(self.a), 1)

    def test_a_coluna_origem_existe_e_a_migracao_e_idempotente(self):
        appmod.init_db()
        appmod.init_db()
        con = sqlite3.connect(DB)
        cols = {r[1] for r in con.execute("PRAGMA table_info(ata_falas)")}
        con.close()
        self.assertIn("origem", cols)


if __name__ == "__main__":
    unittest.main()
