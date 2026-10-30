"""Sexta so tem daily (a aula vai ate 12h): sem Dev e sem encerramento/Day Closing.
Ninguem perde por um evento que nao existe, e o historico antigo continua valendo."""
import os
import sqlite3
import sys
import tempfile
import unittest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "sexta.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402

DB = str(appmod.DB_PATH)
QUINTA = "2026-10-22"
SEXTA = "2026-10-23"
SEGUNDA = "2026-10-26"


class TestRegraPura(unittest.TestCase):
    def test_sexta_so_tem_daily(self):
        self.assertEqual(game.eventos_do_dia(SEXTA), ("daily",))
        self.assertEqual(game.eventos_do_dia("2026-10-30"), ("daily",))
        self.assertEqual(game.eventos_do_dia(QUINTA), ("daily", "dev", "encerramento"))
        self.assertEqual(game.eventos_do_dia(SEGUNDA), ("daily", "dev", "encerramento"))

    def test_falta_e_aviso_em_evento_que_nao_existe_nao_valem(self):
        self.assertFalse(game.registro_vale(SEXTA, "dev", "faltou"))
        self.assertFalse(game.registro_vale(SEXTA, "encerramento", "justificada"))
        self.assertTrue(game.registro_vale(SEXTA, "daily", "faltou"))
        self.assertTrue(game.registro_vale(QUINTA, "dev", "faltou"))

    def test_presenca_antiga_continua_valendo(self):
        self.assertTrue(game.registro_vale(SEXTA, "dev", "presente"))


class Base(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        self.client = appmod.app.test_client()
        con = sqlite3.connect(DB)
        self.ids = [r[0] for r in con.execute(
            "SELECT id FROM members WHERE active = 1 AND COALESCE(tipo, 'equipe') = 'equipe' ORDER BY id")]
        con.close()
        self.mid = self.ids[0]

    def gravar(self, mid, data, evento, status):
        """Grava direto no banco, como um registro antigo (de antes da regra da sexta)."""
        con = sqlite3.connect(DB)
        con.execute("INSERT OR REPLACE INTO attendance (member_id, event_date, event_type, status) VALUES (?,?,?,?)",
                    (mid, data, evento, status))
        con.commit()
        con.close()

    def status(self, mid, data, evento):
        con = sqlite3.connect(DB)
        r = con.execute("SELECT status FROM attendance WHERE member_id=? AND event_date=? AND event_type=?",
                        (mid, data, evento)).fetchone()
        con.close()
        return r[0] if r else None

    def marcar(self, data, evento, status, mid=None):
        return self.client.post("/api/attendance", json={
            "member_id": mid or self.mid, "event_date": data, "event_type": evento, "status": status})


class TestContas(Base):
    def test_falta_antiga_no_dev_da_sexta_nao_derruba_planta_nem_sequencia(self):
        self.gravar(self.mid, QUINTA, "daily", "presente")
        self.gravar(self.mid, SEXTA, "daily", "presente")
        self.gravar(self.mid, SEXTA, "dev", "faltou")
        with appmod.app.app_context():
            reg = appmod._registros_membro(appmod.get_db(), self.mid)
        self.assertEqual(reg[SEXTA], {"presente": True})
        e = game.calcular_membro([QUINTA, SEXTA], reg, 36)
        self.assertEqual((e["g"], e["streak"]), (2, 2))

    def test_so_falta_no_dev_da_sexta_nao_vira_falta_do_dia(self):
        self.gravar(self.mid, SEXTA, "encerramento", "faltou")
        with appmod.app.app_context():
            reg = appmod._registros_membro(appmod.get_db(), self.mid)
        self.assertNotIn(SEXTA, reg)

    def test_dia_cheio_na_sexta_so_pede_a_daily(self):
        for mid in self.ids:
            self.gravar(mid, SEXTA, "daily", "presente")
        self.gravar(self.mid, SEXTA, "dev", "faltou")      # registro antigo: nao conta
        with appmod.app.app_context():
            db = appmod.get_db()
            self.assertTrue(appmod._dia_cheio_na_data(db, SEXTA, appmod._dias_letivos(db)))

    def test_presenca_antiga_no_dev_da_sexta_mantem_a_semente(self):
        self.gravar(self.mid, SEXTA, "daily", "presente")
        self.gravar(self.mid, SEXTA, "dev", "presente")
        with appmod.app.app_context():
            glob = appmod._registros_globais(appmod.get_db())
        self.assertEqual(glob[SEXTA][self.mid]["eventos"], {"daily", "dev"})


class TestMarcacao(Base):
    def test_nao_marca_dev_nem_encerramento_na_sexta(self):
        for ev in ("dev", "encerramento"):
            for st in ("presente", "faltou", "justificada"):
                r = self.marcar(SEXTA, ev, st)
                self.assertEqual(r.status_code, 400)
                self.assertIn("só tem daily", r.get_json()["erro"])
        self.assertIsNone(self.status(self.mid, SEXTA, "dev"))

    def test_daily_da_sexta_marca_normal(self):
        self.assertEqual(self.marcar(SEXTA, "daily", "presente").status_code, 200)
        self.assertEqual(self.status(self.mid, SEXTA, "daily"), "presente")

    def test_quinta_continua_com_os_tres(self):
        self.assertEqual(self.marcar(QUINTA, "dev", "faltou").status_code, 200)

    def test_registro_antigo_da_sexta_ainda_pode_ser_limpo(self):
        self.gravar(self.mid, SEXTA, "dev", "faltou")
        self.assertEqual(self.marcar(SEXTA, "dev", None).status_code, 200)
        self.assertIsNone(self.status(self.mid, SEXTA, "dev"))

    def test_todos_presentes_no_dev_da_sexta_e_recusado(self):
        r = self.client.post("/api/attendance/marcar_todos", json={"event_date": SEXTA, "event_type": "dev"})
        self.assertEqual(r.status_code, 400)

    def test_definir_status_ignora_evento_que_nao_existe(self):
        with appmod.app.app_context():
            db = appmod.get_db()
            appmod._definir_status(db, self.mid, SEXTA, "encerramento", "presente")
            db.commit()
        self.assertIsNone(self.status(self.mid, SEXTA, "encerramento"))

    def test_relator_na_closing_da_sexta_nao_marca_encerramento(self):
        self.client.post("/api/ata/salvar", json={"data": SEXTA, "tipo": "fechamento", "campo": "feito",
                                                  "member_id": self.mid, "valor": "terminei"})
        self.assertIsNone(self.status(self.mid, SEXTA, "encerramento"))


class TestTelas(Base):
    def test_hoje_da_sexta_mostra_so_a_daily(self):
        h = self.client.get(f"/dia/{SEXTA}").get_data(as_text=True)
        self.assertIn("Sexta só tem daily", h)
        self.assertIn('data-event-type="daily"', h)
        self.assertNotIn('data-event-type="dev"', h)
        self.assertNotIn('data-event-type="encerramento"', h)
        self.assertIn("--n-eventos: 1", h)

    def test_quinta_mostra_os_tres(self):
        h = self.client.get(f"/dia/{QUINTA}").get_data(as_text=True)
        self.assertNotIn("Sexta só tem daily", h)
        self.assertIn('data-event-type="dev"', h)
        self.assertIn("--n-eventos: 3", h)

    def test_sexta_com_registro_antigo_mostra_a_coluna_para_limpar(self):
        self.gravar(self.mid, SEXTA, "dev", "presente")
        h = self.client.get(f"/dia/{SEXTA}").get_data(as_text=True)
        self.assertIn('data-event-type="dev"', h)
        self.assertIn("registro antigo", h)
        self.assertNotIn('class="btn btn-ghost btn-marcar-todos" data-event-type="dev"', h)

    def test_day_closing_da_sexta_volta_para_a_daily(self):
        r = self.client.get(f"/ata/{SEXTA}/fechamento")
        self.assertEqual(r.status_code, 302)
        self.assertIn(f"/ata/{SEXTA}/daily", r.headers["Location"])
        h = self.client.get(f"/ata/{SEXTA}/daily").get_data(as_text=True)
        self.assertNotIn(f"/ata/{SEXTA}/fechamento", h)

    def test_day_closing_antigo_da_sexta_continua_abrindo(self):
        con = sqlite3.connect(DB)
        con.execute("INSERT INTO atas (data, tipo) VALUES (?, 'fechamento')", (SEXTA,))
        con.commit()
        con.close()
        self.assertEqual(self.client.get(f"/ata/{SEXTA}/fechamento").status_code, 200)

    def test_minigame_fechar_o_dia_nao_aparece_na_sexta(self):
        with appmod.app.app_context():
            db = appmod.get_db()
            self.assertFalse(appmod._estado_minijogos(db, self.mid, SEXTA)["tem_fechamento"])
            self.assertTrue(appmod._estado_minijogos(db, self.mid, QUINTA)["tem_fechamento"])


class TestFicaParaSegunda(Base):
    def fala(self, data, tipo, planejado):
        con = sqlite3.connect(DB)
        con.execute("INSERT INTO atas (data, tipo) VALUES (?, ?) ON CONFLICT DO NOTHING", (data, tipo))
        con.execute("INSERT INTO ata_falas (data, tipo, member_id, feito, planejado) VALUES (?,?,?,?,?)",
                    (data, tipo, self.mid, "", planejado))
        con.commit()
        con.close()

    def test_segunda_sugere_o_plano_da_daily_de_sexta(self):
        self.fala(SEXTA, "daily", "revisar o MR #12")
        with appmod.app.app_context():
            self.assertEqual(appmod._fica_para_amanha(appmod.get_db(), self.mid, SEGUNDA), "revisar o MR #12")

    def test_day_closing_antigo_da_sexta_tem_prioridade(self):
        self.fala(SEXTA, "daily", "daily")
        self.fala(SEXTA, "fechamento", "closing")
        with appmod.app.app_context():
            self.assertEqual(appmod._fica_para_amanha(appmod.get_db(), self.mid, SEGUNDA), "closing")

    def test_outros_dias_seguem_so_com_o_day_closing(self):
        self.fala(QUINTA, "daily", "plano da daily")
        with appmod.app.app_context():
            self.assertEqual(appmod._fica_para_amanha(appmod.get_db(), self.mid, SEXTA), "")


if __name__ == "__main__":
    unittest.main()
