import os
import sqlite3
import sys
import tempfile
import unittest

# O banco de teste e sempre um arquivo temporario; nunca o banco real.
_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "fase2.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402

DB = str(appmod.DB_PATH)
DATA = "2026-10-19"  # dia letivo (segunda)


class Fase2Base(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        self.client = appmod.app.test_client()

    def ativos(self):
        con = sqlite3.connect(DB)
        ids = [r[0] for r in con.execute("SELECT id FROM members WHERE active = 1 ORDER BY id")]
        con.close()
        return ids

    def set_tipo(self, member_id, tipo):
        con = sqlite3.connect(DB)
        con.execute("UPDATE members SET tipo = ? WHERE id = ?", (tipo, member_id))
        con.commit()
        con.close()

    def presente(self, member_id, data, event_type="daily"):
        con = sqlite3.connect(DB)
        con.execute(
            "INSERT OR REPLACE INTO attendance (member_id, event_date, event_type, status) "
            "VALUES (?,?,?,?)", (member_id, data, event_type, "presente"),
        )
        con.commit()
        con.close()

    def stats(self):
        with appmod.app.test_request_context():
            return appmod.get_member_stats(appmod.get_db())

    def base(self):
        with appmod.app.test_request_context():
            return appmod._base_coletivo(appmod.get_db())


class TestSchema(Fase2Base):
    def test_coluna_tipo_existe_e_default_equipe(self):
        con = sqlite3.connect(DB)
        cols = {r[1]: r for r in con.execute("PRAGMA table_info(members)")}
        self.assertIn("tipo", cols)
        tipos = [r[0] for r in con.execute("SELECT DISTINCT tipo FROM members")]
        con.close()
        self.assertEqual(set(tipos), {"equipe"})  # todo mundo comeca na equipe

    def test_migracao_idempotente(self):
        # rodar init_db de novo nao quebra nem duplica a coluna
        appmod.init_db()
        con = sqlite3.connect(DB)
        n = sum(1 for r in con.execute("PRAGMA table_info(members)") if r[1] == "tipo")
        con.close()
        self.assertEqual(n, 1)


class TestDiaCheioIgnoraConvidado(Fase2Base):
    def test_equipe_presente_e_dia_cheio_mesmo_com_convidado_ausente(self):
        ativos = self.ativos()
        equipe, convidados = ativos[:-2], ativos[-2:]
        for mid in convidados:
            self.set_tipo(mid, "convidado")
        # toda a equipe presente; convidados ausentes
        for mid in equipe:
            self.presente(mid, DATA)
        with appmod.app.test_request_context():
            db = appmod.get_db()
            cheio = appmod._dia_cheio_na_data(db, DATA, appmod._dias_letivos(db))
        self.assertTrue(cheio)

    def test_convidado_presente_nao_e_exigido_para_dia_cheio(self):
        ativos = self.ativos()
        equipe, convidado = ativos[:-1], ativos[-1]
        self.set_tipo(convidado, "convidado")
        for mid in equipe:
            self.presente(mid, DATA)
        # convidado tambem presente: continua dia cheio (nao muda nada)
        self.presente(convidado, DATA)
        with appmod.app.test_request_context():
            db = appmod.get_db()
            self.assertTrue(appmod._dia_cheio_na_data(db, DATA, appmod._dias_letivos(db)))

    def test_falta_da_equipe_quebra_dia_cheio(self):
        ativos = self.ativos()
        equipe, convidado = ativos[:-1], ativos[-1]
        self.set_tipo(convidado, "convidado")
        # falta um da equipe
        for mid in equipe[:-1]:
            self.presente(mid, DATA)
        with appmod.app.test_request_context():
            db = appmod.get_db()
            self.assertFalse(appmod._dia_cheio_na_data(db, DATA, appmod._dias_letivos(db)))


class TestColetivoInalterado(Fase2Base):
    def test_progresso_coletivo_nao_muda_ao_tornar_convidado(self):
        ativos = self.ativos()
        for mid in ativos:
            self.presente(mid, DATA)
        base_antes = self.base()
        prog_antes = appmod._progresso_coletivo(base_antes["ativos"], base_antes["meta"])
        n_equipe_antes = len(base_antes["ativos"])
        # torna o ultimo convidado
        self.set_tipo(ativos[-1], "convidado")
        base_depois = self.base()
        prog_depois = appmod._progresso_coletivo(base_depois["ativos"], base_depois["meta"])
        # o progresso do time (media por membro da equipe) nao deve mudar so por
        # reclassificar alguem: todos tinham o mesmo estado neste cenario
        self.assertEqual(prog_antes, prog_depois)
        self.assertEqual(len(base_depois["ativos"]), n_equipe_antes - 1)
        self.assertEqual(len(base_depois["convidados"]), 1)

    def test_metas_nao_mudam_ao_tornar_convidado(self):
        ativos = self.ativos()
        # equipe inteira presente em alguns dias (menos o ultimo, que vira convidado)
        for mid in ativos[:-1]:
            for d in ("2026-10-15", "2026-10-16", DATA):
                self.presente(mid, d)
        r = self.client.post("/api/metas", json={
            "acao": "adicionar", "sprint": 1, "tipo": "presenca_pct", "alvo": 100,
        })
        self.assertEqual(r.status_code, 200)

        def valor_meta():
            with appmod.app.test_request_context():
                db = appmod.get_db()
                ctx = appmod._base_coletivo(db)
                metas = appmod._metas_da_sprint(db, ctx, 1)
            return next(m["valor"] for m in metas if m["tipo"] == "presenca_pct")

        # o ultimo ainda e equipe, mas sem presencas: puxa a % do time para baixo
        antes = valor_meta()
        # ao vira convidado, ele sai do calculo do time -> a % so pode melhorar ou ficar igual,
        # e nunca depende mais dele
        self.set_tipo(ativos[-1], "convidado")
        depois = valor_meta()
        self.assertGreaterEqual(depois, antes)
        # agora todos os membros de equipe restantes estao 100% presentes nos dias marcados;
        # adicionar/mexer no convidado nunca mais muda o valor
        self.presente(ativos[-1], "2026-10-15")  # convidado marca presenca
        self.assertEqual(valor_meta(), depois)  # nao muda nada no time


class TestConvidadoForaDoColetivo(Fase2Base):
    def test_convidado_nao_entra_em_destaques(self):
        ativos = self.ativos()
        convidado = ativos[-1]
        self.set_tipo(convidado, "convidado")
        # so o convidado tem uma sequencia longa
        for d in ("2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"):
            self.presente(convidado, d)
        base = self.base()
        destaques = appmod._destaques(base["ativos"])
        nomes = [n for d in destaques for n in d["nomes"]]
        con = sqlite3.connect(DB)
        nome_conv = con.execute("SELECT name FROM members WHERE id = ?", (convidado,)).fetchone()[0]
        con.close()
        self.assertNotIn(nome_conv, nomes)

    def test_convidado_fora_do_panorama_e_denominador(self):
        ativos = self.ativos()
        convidado = ativos[-1]
        self.set_tipo(convidado, "convidado")
        with appmod.app.test_request_context():
            db = appmod.get_db()
            ctx = appmod._base_coletivo(db)
            pan = appmod._panorama(db, ctx, "projeto", hoje="2026-10-21")
        # o denominador (uma linha por pessoa) e so a equipe
        self.assertEqual(len(pan["linhas"]), len(ctx["ativos"]))
        self.assertNotIn(convidado, [l["id"] for l in pan["linhas"]])

    def test_convidado_fora_do_bosque(self):
        ativos = self.ativos()
        convidado = ativos[-1]
        self.set_tipo(convidado, "convidado")
        # convidado floresce (presenca em todos os dias letivos)
        con = sqlite3.connect(DB)
        dias = game.dias_letivos("2026-10-15", "2026-10-12", 10,
                                 {"2026-10-12", "2026-11-02", "2026-11-20"})
        for d in dias:
            con.execute("INSERT OR REPLACE INTO attendance (member_id,event_date,event_type,status) "
                        "VALUES (?,?,?,?)", (convidado, d, "daily", "presente"))
        con.commit()
        con.close()
        html = self.client.get("/dashboard").get_data(as_text=True)
        # o convidado floresceu, mas o bosque (coletivo) nao deve inclui-lo
        base = self.base()
        conv = next(m for m in base["convidados"] if m["id"] == convidado)
        self.assertTrue(conv["floresceu"])  # ele floresceu de fato
        trecho = html[html.index('id="bosque"'):]
        nome = conv["name"]
        self.assertNotIn(">" + nome + "<", trecho)


class TestConvidadoTemJogoProprio(Fase2Base):
    def test_convidado_ganha_sementes_e_boas_vindas(self):
        ativos = self.ativos()
        convidado = ativos[-1]
        self.set_tipo(convidado, "convidado")
        self.presente(convidado, DATA)
        conv = next(m for m in self.stats() if m["id"] == convidado)
        # +1 do evento + boas-vindas (bonus unico da Fase 1)
        self.assertEqual(conv["sementes_ganhas"], 1 + game.SEED_BOAS_VINDAS)
        self.assertTrue(conv["convidado"])

    def test_convidado_tem_loja_e_perfil(self):
        ativos = self.ativos()
        convidado = ativos[-1]
        self.set_tipo(convidado, "convidado")
        self.presente(convidado, DATA)
        self.assertEqual(self.client.get(f"/loja?m={convidado}").status_code, 200)
        perfil = self.client.get(f"/membro/{convidado}")
        self.assertEqual(perfil.status_code, 200)
        self.assertIn("chip-convidado", perfil.get_data(as_text=True))


class TestCrudTipo(Fase2Base):
    def test_criar_convidado_pela_api(self):
        r = self.client.post("/api/membros", json={"name": "Visitante", "tipo": "convidado"})
        self.assertEqual(r.status_code, 200)
        con = sqlite3.connect(DB)
        tipo = con.execute("SELECT tipo FROM members WHERE name = 'Visitante'").fetchone()[0]
        con.close()
        self.assertEqual(tipo, "convidado")

    def test_tipo_invalido_recusado(self):
        r = self.client.post("/api/membros", json={"name": "X", "tipo": "chefe"})
        self.assertEqual(r.status_code, 400)

    def test_trocar_tipo_pela_api(self):
        mid = self.ativos()[0]
        self.assertEqual(self.client.post(f"/api/membros/{mid}", json={"tipo": "convidado"}).status_code, 200)
        con = sqlite3.connect(DB)
        self.assertEqual(con.execute("SELECT tipo FROM members WHERE id = ?", (mid,)).fetchone()[0], "convidado")
        con.close()


class TestMarcarTodosPorTipo(Fase2Base):
    def _marcados(self):
        con = sqlite3.connect(DB)
        ids = {r[0] for r in con.execute("SELECT member_id FROM attendance WHERE event_date = ?", (DATA,))}
        con.close()
        return ids

    def test_marcar_todos_so_convidados(self):
        ativos = self.ativos()
        conv = ativos[-1]
        self.set_tipo(conv, "convidado")
        r = self.client.post("/api/attendance/marcar_todos", json={
            "event_date": DATA, "event_type": "daily", "status": "presente", "tipo": "convidado",
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._marcados(), {conv})

    def test_marcar_todos_so_equipe(self):
        ativos = self.ativos()
        conv = ativos[-1]
        self.set_tipo(conv, "convidado")
        self.client.post("/api/attendance/marcar_todos", json={
            "event_date": DATA, "event_type": "daily", "status": "presente", "tipo": "equipe",
        })
        self.assertEqual(self._marcados(), set(ativos[:-1]))

    def test_tipo_invalido_no_marcar_todos(self):
        r = self.client.post("/api/attendance/marcar_todos", json={
            "event_date": DATA, "event_type": "daily", "status": "presente", "tipo": "xyz",
        })
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
