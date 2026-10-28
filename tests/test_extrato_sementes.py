import os
import sqlite3
import sys
import tempfile
import unittest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "extrato.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402

DB = str(appmod.DB_PATH)
SEMANA1 = "2026-10-12"
FERIADOS = {"2026-10-12", "2026-11-02", "2026-11-20"}
DIAS = game.dias_letivos("2026-10-15", SEMANA1, 10, list(FERIADOS))
SEMANAS = game.semanas_do_projeto(SEMANA1, 10, FERIADOS)
META = game.meta_floracao(len(DIAS))


def _reg(presentes, eventos=("daily", "dev", "encerramento"), faltas=()):
    r = {d: {"presente": True, "eventos": set(eventos)} for d in presentes}
    for d in faltas:
        r[d] = {"faltou": True}
    return r


def _soma(linhas):
    return sum(x["valor"] for x in linhas)


# ------------------------------------------------------------ puro: o extrato fecha com o total
class TestExtratoPuro(unittest.TestCase):
    def _confere(self, reg, cheios=None, falas=(), relatadas=None):
        estado = game.calcular_membro(DIAS, reg, META)
        n_rel = sum(min(len(n), game.SEED_RELATOR_MAX_POR_ATA) for n in (relatadas or {}).values())
        total = game.calcular_sementes(DIAS, SEMANAS, reg, estado["floresceu"], dias_cheios=cheios or set(),
                                       atas_com_fala=len(set(falas)), falas_relatadas=n_rel)["total"]
        ext = game.extrato_sementes(DIAS, SEMANAS, reg, META, dias_cheios=cheios or set(),
                                    falas=falas, relatadas=relatadas)
        self.assertEqual(_soma(ext), total)
        return ext

    def test_dedicado_completo(self):
        falas = [(d, t) for d in DIAS for t in ("daily", "fechamento")]
        self._confere(_reg(DIAS), cheios=set(DIAS), falas=falas)

    def test_tipico_com_faltas_e_sequencia_quebrada(self):
        presentes = [d for i, d in enumerate(DIAS) if i % 8 != 7]
        faltas = [d for i, d in enumerate(DIAS) if i % 8 == 7 and i < 20]
        reg = _reg(presentes, eventos=("daily", "dev"))
        reg.update(_reg([], faltas=faltas))
        self._confere(reg, cheios={DIAS[0], DIAS[1]})

    def test_sem_nada(self):
        self.assertEqual(self._confere({}), [])

    def test_so_daily_e_registro_antigo_sem_eventos(self):
        reg = {d: {"presente": True} for d in DIAS[:5]}               # sem a chave "eventos"
        self._confere(reg)

    def test_relator_com_limite_por_ata(self):
        rel = {(DIAS[0], "daily"): ["Ana", "Bia", "Caio", "Davi", "Edu"],          # 5 colegas: so 3 contam
               (DIAS[0], "fechamento"): ["Ana", "Bia"]}
        ext = self._confere(_reg(DIAS[:3]), relatadas=rel)
        linhas = [x for x in ext if x["fonte"] == "relator"]
        self.assertEqual(sorted(x["valor"] for x in linhas), [2, game.SEED_RELATOR_MAX_POR_ATA])
        cortada = next(x for x in linhas if x["valor"] == game.SEED_RELATOR_MAX_POR_ATA)
        self.assertIn("limite", cortada["detalhe"])                    # explica o corte

    def test_cada_linha_tem_data_motivo_e_valor(self):
        ext = self._confere(_reg(DIAS[:6]))
        for x in ext:
            self.assertTrue(x["data"] and x["rotulo"] and x["valor"] > 0)
        marco = [x for x in ext if x["fonte"] == "marcos"]
        self.assertEqual([m["detalhe"] for m in marco], ["5 dias seguidos"])
        self.assertEqual(marco[0]["data"], DIAS[4])                    # o dia em que chegou aos 5

    def test_boas_vindas_no_primeiro_dia(self):
        ext = self._confere(_reg(DIAS[2:4]))
        bv = [x for x in ext if x["fonte"] == "boas_vindas"]
        self.assertEqual((len(bv), bv[0]["data"]), (1, DIAS[2]))

    def test_dia_cheio_so_conta_se_a_pessoa_veio(self):
        ext = self._confere(_reg(DIAS[:2]), cheios={DIAS[0], DIAS[5]})
        self.assertEqual(len([x for x in ext if x["fonte"] == "dia_cheio"]), 1)

    def test_floresceu_no_dia_certo(self):
        ext = self._confere(_reg(DIAS))
        fl = [x for x in ext if x["fonte"] == "floresceu"]
        self.assertEqual(len(fl), 1)
        self.assertEqual(game.calcular_membro(DIAS[: DIAS.index(fl[0]["data"]) + 1], _reg(DIAS), META)["floresceu"], True)
        self.assertEqual(game.calcular_membro(DIAS[: DIAS.index(fl[0]["data"])], _reg(DIAS), META)["floresceu"], False)


# ------------------------------------------------------------ no app: extrato = saldo real
class TestExtratoNoApp(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        self.client = appmod.app.test_client()                  # localhost = administrador
        con = sqlite3.connect(DB)
        self.ids = [r[0] for r in con.execute("SELECT id FROM members WHERE active = 1 ORDER BY id")]
        con.close()
        self.a, self.b, self.c = self.ids[:3]

    def _presente(self, mid, data, eventos=("daily", "dev", "encerramento")):
        con = sqlite3.connect(DB)
        for ev in eventos:
            con.execute("INSERT OR REPLACE INTO attendance (member_id, event_date, event_type, status) VALUES (?,?,?, 'presente')",
                        (mid, data, ev))
        con.commit()
        con.close()

    def _ata(self, data, tipo, mid, texto="algo"):
        self.client.post("/api/ata/salvar", json={"data": data, "tipo": tipo, "campo": "feito", "member_id": mid, "valor": texto})

    def _ctx(self, mid, compare=None):
        with appmod.app.test_request_context():
            return appmod._contexto_sementes(appmod.get_db(), mid, compare)

    def test_o_total_do_extrato_e_o_saldo_real_da_loja(self):
        for d in DIAS[:4]:
            self._presente(self.a, d)
        self.client.post("/api/ata/salvar", json={"data": DIAS[0], "tipo": "daily", "campo": "relator", "valor": self.a})
        self._ata(DIAS[0], "daily", self.a)                     # a propria fala
        self._ata(DIAS[0], "daily", self.b)                     # fala do colega, preenchida pelo relator
        self._ata(DIAS[0], "daily", self.c)
        with appmod.app.test_request_context():
            db = appmod.get_db()
            stats = next(s for s in appmod.get_member_stats(db) if s["id"] == self.a)
        ctx = self._ctx(self.a)
        extrato = ctx["detalhe"]["extrato"]
        self.assertEqual(extrato["ganho"], stats["sementes_ganhas"])
        self.assertEqual(ctx["detalhe"]["ganho"]["total"], stats["sementes_ganhas"])
        self.assertEqual(extrato["saldo"], stats["sementes"])
        fontes = {x["fonte"] for x in extrato["linhas"]}
        self.assertIn("ata", fontes)
        self.assertIn("relator", fontes)

    def test_compras_aparecem_como_gasto_e_descontam_do_saldo(self):
        for d in DIAS[:6]:
            self._presente(self.a, d)
        con = sqlite3.connect(DB)
        con.execute("INSERT INTO compras (member_id, item_id, custo) VALUES (?, 'girassol', 40)", (self.a,))
        con.commit()
        con.close()
        det = self._ctx(self.a)["detalhe"]
        gastos = [x for x in det["extrato"]["linhas"] if x["fonte"] == "gasto"]
        self.assertEqual([x["valor"] for x in gastos], [-40])
        self.assertEqual(det["gasto"], 40)
        self.assertEqual(det["saldo"], max(det["ganho"]["total"] - 40, 0))

    def test_limite_do_relator_por_ata_no_saldo(self):
        self.client.post("/api/ata/salvar", json={"data": DIAS[0], "tipo": "daily", "campo": "relator", "valor": self.a})
        con = sqlite3.connect(DB)
        mais = self.ids[1:]                                      # todos os outros membros
        con.close()
        for mid in mais:
            self._ata(DIAS[0], "daily", mid)
        com_fala, rel = None, None
        with appmod.app.test_request_context():
            db = appmod.get_db()
            com_fala, rel = appmod._contagem_atas(db, appmod._dias_letivos(db))
        self.assertEqual(rel.get(self.a), game.SEED_RELATOR_MAX_POR_ATA)        # tinha mais gente, o limite vale

    def test_a_pagina_mostra_extrato_e_fontes_novas(self):
        self._presente(self.a, DIAS[0])
        h = self.client.get(f"/sementes?m={self.a}").get_data(as_text=True)
        self.assertIn("extrato", h.lower())
        self.assertIn("Atas preenchidas", h)
        self.assertIn("Scrum: falas de colegas preenchidas", h)
        self.assertIn("Saldo para gastar", h)

    def test_a_pagina_explica_a_diferenca_entre_duas_pessoas(self):
        self.client.post("/api/ata/salvar", json={"data": DIAS[0], "tipo": "daily", "campo": "relator", "valor": self.a})
        for mid in (self.a, self.b):
            for d in DIAS[:3]:
                self._presente(mid, d)
        self._ata(DIAS[0], "daily", self.a)
        self._ata(DIAS[0], "daily", self.c)                      # o relator preencheu a do Pablo (c)
        ctx = self._ctx(self.a, self.b)
        rotulos = {d["rotulo"]: d["delta"] for d in ctx["diferencas"]}
        self.assertIn("Scrum: falas de colegas preenchidas", rotulos)
        self.assertGreater(rotulos["Scrum: falas de colegas preenchidas"], 0)
        h = self.client.get(f"/sementes?m={self.a}&b={self.b}").get_data(as_text=True)
        self.assertIn("De onde vem a diferença", h)

    def test_logado_abre_na_propria_pessoa(self):
        with self.client.session_transaction() as sess:
            sess["eu"] = self.a
        r = self.client.get("/sementes")
        self.assertEqual(r.status_code, 302)
        self.assertIn(f"m={self.a}", r.headers["Location"])


if __name__ == "__main__":
    unittest.main()
