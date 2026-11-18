"""Aba Graficos do Painel: numeros do time derivados das mesmas regras do extrato e da ata."""
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

# O banco de teste e sempre um arquivo temporario; nunca o banco real.
_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "graficos.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402

DB = str(appmod.DB_PATH)
DIAS = game.dias_letivos("2026-10-15", "2026-10-12", 10, {"2026-10-12", "2026-11-02", "2026-11-20"})


class _HojeFixo(date):
    """'Hoje' fixo na Sprint 2 (quarta, 28/10), para o teste nao depender do relogio."""
    @classmethod
    def today(cls):
        return date(2026, 10, 28)


class TestGraficos(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        patcher = mock.patch.object(appmod, "date", _HojeFixo)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = appmod.app.test_client()
        con = sqlite3.connect(DB)
        con.execute("UPDATE members SET active = 0")
        self.ids = {}
        for nome in ("Zeca", "Ana", "Bia"):          # inseridos fora da ordem alfabetica de proposito
            cur = con.execute("INSERT INTO members (name, active) VALUES (?, 1)", (nome,))
            self.ids[nome] = cur.lastrowid
        # todos presentes na daily dos 6 primeiros dias letivos (Sprint 1)
        for mid in self.ids.values():
            for d in DIAS[:6]:
                con.execute("INSERT INTO attendance (member_id, event_date, event_type, status) "
                            "VALUES (?,?,'daily','presente')", (mid, d))
        a, b, z = self.ids["Ana"], self.ids["Bia"], self.ids["Zeca"]
        # Ana conduz a daily dos dias 0 e 1 e escreve a fala da Bia no dia 0
        for d in DIAS[:2]:
            con.execute("INSERT INTO atas (data, tipo, relator_id) VALUES (?, 'daily', ?)", (d, a))
        con.execute("INSERT INTO atas (data, tipo, relator_id) VALUES (?, 'fechamento', ?)", (DIAS[0], z))
        falas = [(DIAS[0], "daily", a, "proprio"), (DIAS[0], "daily", b, "relator"),
                 (DIAS[1], "daily", a, "proprio"), ("2026-10-26", "daily", z, "proprio"),
                 (DIAS[0], "fechamento", z, "proprio")]
        for d, tipo, mid, origem in falas:
            con.execute("INSERT INTO ata_falas (data, tipo, member_id, feito, planejado, origem) "
                        "VALUES (?,?,?,'card','card',?)", (d, tipo, mid, origem))
        con.execute("INSERT INTO ata_falas (data, tipo, member_id, feito, planejado) VALUES (?, 'daily', ?, ' ', '')",
                    (DIAS[2], b))                     # fala vazia nao conta
        con.execute("INSERT INTO minijogos (member_id, data, jogo) VALUES (?, ?, 'fala_pronta')", (a, DIAS[1]))
        con.commit()
        con.close()

    def ctx(self, sprint=None):
        with appmod.app.app_context():
            return appmod._contexto_graficos(appmod.get_db(), sprint)

    def test_pagina_abre_e_aparece_na_aba(self):
        html = self.client.get("/graficos").get_data(as_text=True)
        self.assertIn("Gráficos do time", html)
        self.assertIn('href="/graficos"', self.client.get("/dashboard").get_data(as_text=True))
        self.assertEqual(self.client.get("/graficos?sprint=2").status_code, 200)
        self.assertEqual(self.client.get("/graficos?sprint=99").status_code, 200)   # vira o projeto todo

    def test_pessoas_em_ordem_alfabetica(self):
        self.assertEqual([p["name"] for p in self.ctx()["pessoas"]], ["Ana", "Bia", "Zeca"])

    def test_sementes_batem_com_o_ganho_do_painel(self):
        with appmod.app.app_context():
            stats = {m["id"]: m["sementes_ganhas"] for m in appmod.get_member_stats(appmod.get_db())}
        c = self.ctx()
        for p in c["pessoas"]:
            self.assertEqual(p["sementes_total"], stats[p["id"]], p["name"])
            self.assertGreater(p["sementes_total"], 0)
        # a tendencia do time soma o mesmo total
        self.assertEqual(sum(b["total"] for b in c["baldes"]), c["resumo"]["sementes"])

    def test_contagens_de_ata_scrum_e_preparo(self):
        p = {x["name"]: x for x in self.ctx()["pessoas"]}
        self.assertEqual((p["Ana"]["daily"], p["Bia"]["daily"], p["Zeca"]["daily"]), (2, 1, 1))
        self.assertEqual(p["Zeca"]["fechamento"], 1)
        self.assertEqual((p["Ana"]["conduziu_daily"], p["Zeca"]["conduziu_fechamento"]), (2, 1))
        self.assertEqual(p["Ana"]["falas_colegas"], 1)
        self.assertEqual(p["Ana"]["fala_pronta"], 1)
        self.assertEqual(p["Bia"]["conduziu_daily"] + p["Bia"]["falas_colegas"], 0)

    def test_taxa_da_daily_e_do_time(self):
        r = self.ctx()["resumo"]
        dias_ate_hoje = len([d for d in DIAS if d <= "2026-10-28"])
        self.assertEqual(r["daily"], 4)
        self.assertEqual(r["taxa_daily"], round(100 * 4 / (dias_ate_hoje * 3)))

    def test_filtro_por_sprint(self):
        c = self.ctx(sprint=2)                       # Sprint 2 comeca em 26/10
        self.assertTrue(c["por_dia"])
        self.assertTrue(all("2026-10-26" <= b["inicio"] <= "2026-10-28" for b in c["baldes"]))
        p = {x["name"]: x for x in c["pessoas"]}
        self.assertEqual((p["Ana"]["daily"], p["Zeca"]["daily"]), (0, 1))   # a fala do Zeca e de 26/10
        self.assertEqual(p["Ana"]["conduziu_daily"], 0)
        self.assertIsNone(self.ctx(sprint=9)["sprint"])

    def test_tendencia_por_semana_so_ate_hoje(self):
        rotulos = [b["rotulo"] for b in self.ctx()["baldes"]]
        self.assertEqual(rotulos, ["S1", "S2", "S3"])

    def test_escala(self):
        self.assertEqual([appmod._escala(v) for v in (0, 1, 7, 9, 31, 304, 1000)], [1, 1, 8, 10, 40, 400, 1000])


if __name__ == "__main__":
    unittest.main()
