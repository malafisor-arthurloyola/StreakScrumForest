import os
import sqlite3
import sys
import tempfile
import unittest

# O banco de teste e sempre um arquivo temporario; nunca o banco real.
_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "fase1.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402

DB = str(appmod.DB_PATH)
DATA = "2026-10-19"  # segunda-feira, dia letivo


class Fase1Base(unittest.TestCase):
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

    def inserir(self, member_id, data, event_type, status="presente"):
        con = sqlite3.connect(DB)
        con.execute(
            "INSERT OR REPLACE INTO attendance (member_id, event_date, event_type, status) "
            "VALUES (?,?,?,?)", (member_id, data, event_type, status),
        )
        con.commit()
        con.close()

    def marcar(self, member_id, data, event_type, status="presente"):
        return self.client.post("/api/attendance", json={
            "member_id": member_id, "event_date": data,
            "event_type": event_type, "status": status,
        })

    def get(self, url):
        return self.client.get(url)


class TestDiaCheioContadores(Fase1Base):
    """Fase 1.1: a resposta de /api/attendance traz as sementes de todos os ativos e
    o estado de dia cheio, para o JS atualizar todos os contadores."""

    def test_fechar_dia_cheio_da_mais_uma_para_todos(self):
        ativos = self.ativos()
        self.assertGreaterEqual(len(ativos), 2)
        ultimo = ativos[-1]

        # Todos menos o ultimo ja marcados presentes na daily.
        for mid in ativos[:-1]:
            self.inserir(mid, DATA, "daily")

        r = self.marcar(ultimo, DATA, "daily")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()

        # A marcacao fechou o dia cheio.
        self.assertTrue(data["dia_cheio"])

        # A resposta inclui as sementes de todos os ativos.
        self.assertIn("sementes_membros", data)
        por_id = {m["id"]: m for m in data["sementes_membros"]}
        for mid in ativos:
            self.assertIn(mid, por_id)
            # Cada um presente ganhou: +1 do evento daily, +1 do dia cheio e as
            # boas-vindas (bonus unico da 1a presenca).
            esperado = 2 + game.SEED_BOAS_VINDAS
            self.assertEqual(por_id[mid]["sementes_ganhas"], esperado, f"membro {mid}")

    def test_sem_dia_cheio_nao_marca_a_flag(self):
        ativos = self.ativos()
        # So um membro presente: nao e dia cheio.
        r = self.marcar(ativos[0], DATA, "daily")
        data = r.get_json()
        self.assertFalse(data["dia_cheio"])
        por_id = {m["id"]: m for m in data["sementes_membros"]}
        # So o presente ganhou: +1 do evento + boas-vindas; os ausentes, 0.
        self.assertEqual(por_id[ativos[0]]["sementes_ganhas"], 1 + game.SEED_BOAS_VINDAS)
        for mid in ativos[1:]:
            self.assertEqual(por_id[mid]["sementes_ganhas"], 0)

    def test_desmarcar_quebra_o_dia_cheio(self):
        ativos = self.ativos()
        for mid in ativos:
            self.inserir(mid, DATA, "daily")
        # Desmarca um (status None apaga): deixa de ser dia cheio.
        r = self.marcar(ativos[0], DATA, "daily", status=None)
        data = r.get_json()
        self.assertFalse(data["dia_cheio"])


class TestDiaCheioEstadoInicial(Fase1Base):
    """Fase 1.2: a pagina Hoje expoe o estado inicial de dia cheio da data, para o JS
    so celebrar na transicao nao-cheio -> cheio (nunca ao recarregar)."""

    def test_pagina_marca_false_quando_nao_e_dia_cheio(self):
        html = self.get("/dia/" + DATA).get_data(as_text=True)
        self.assertIn('data-dia-cheio-inicial="false"', html)

    def test_pagina_marca_true_quando_ja_e_dia_cheio(self):
        for mid in self.ativos():
            self.inserir(mid, DATA, "daily")
        html = self.get("/dia/" + DATA).get_data(as_text=True)
        self.assertIn('data-dia-cheio-inicial="true"', html)


class TestAbaSementes(Fase1Base):
    """Fase 1.3: a aba /sementes responde 200, mostra os valores das constantes e
    funciona sem 'quem sou eu'."""

    def test_pagina_responde_e_funciona_sem_quem_sou_eu(self):
        r = self.get("/sementes")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("De onde vêm as sementes", html)
        self.assertIn("Quem acompanhar?", html)  # seletor sempre presente
        self.assertIn("Escolha um nome", html)    # estado vazio, sem pessoa escolhida

    def test_mostra_os_valores_das_constantes(self):
        html = self.get("/sementes").get_data(as_text=True)
        # floresceu e boas-vindas (+20 cada)
        self.assertIn("+" + str(game.SEED_FLORESCEU), html)
        self.assertIn("+" + str(game.SEED_BOAS_VINDAS), html)
        # semana fechada (+3)
        self.assertIn("+" + str(game.SEED_SEMANA_FECHADA), html)
        # cada marco aparece na trilha (dias e bonus)
        for dias, bonus in game.SEED_MILESTONES:
            self.assertIn(str(dias) + " dias", html)
            self.assertIn("+" + str(bonus), html)

    def test_grafico_composicao_soma_o_total(self):
        html = self.get("/sementes").get_data(as_text=True)
        self.assertIn("sem-barra-svg", html)  # grafico SVG no servidor
        # o total do dedicado e derivado do calendario; confirma que aparece na pagina
        with appmod.app.test_request_context():
            db = appmod.get_db()
            ctx = appmod._contexto_sementes(db, None)
        self.assertEqual(sum(c["valor"] for c in ctx["composicao"]), ctx["total_dedicado"])
        self.assertIn(str(ctx["total_dedicado"]), html)

    def test_explica_que_a_sequencia_nao_multiplica(self):
        html = self.get("/sementes").get_data(as_text=True)
        self.assertIn("sequência multiplica? Não", html)

    def test_com_quem_sou_eu_mostra_progresso(self):
        ativos = self.ativos()
        for d in ("2026-10-15", "2026-10-16", DATA):
            self.inserir(ativos[0], d, "daily")
        r = self.get("/sementes?m=" + str(ativos[0]))
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Acompanhar o progresso", html)
        self.assertIn("Próximo marco", html)
        # com uma pessoa escolhida, aparece a opcao de comparar com outra
        self.assertIn("Comparar com", html)

    def test_comparar_dois_membros_lado_a_lado(self):
        ativos = self.ativos()
        a, b = ativos[0], ativos[1]
        for d in ("2026-10-15", "2026-10-16", DATA):
            self.inserir(a, d, "daily")
        self.inserir(b, "2026-10-15", "daily")
        r = self.get(f"/sementes?m={a}&b={b}")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        # duas colunas e o aviso neutro (sem ranking)
        self.assertIn("progresso-comparar", html)
        self.assertIn("sem apontar", html)
        self.assertIn("Sair da comparação", html)

    def test_nao_compara_consigo_mesmo(self):
        ativos = self.ativos()
        a = ativos[0]
        self.inserir(a, "2026-10-15", "daily")
        html = self.get(f"/sementes?m={a}&b={a}").get_data(as_text=True)
        # b == a e ignorado: nao entra em modo comparacao
        self.assertNotIn("progresso-comparar", html)


class TestCardProximosMarcos(Fase1Base):
    """Fase 1.4: o Painel mostra o card Proximos marcos, em ordem alfabetica, com link
    para /sementes."""

    def test_card_aparece_no_painel(self):
        html = self.get("/dashboard").get_data(as_text=True)
        self.assertIn("Próximos marcos", html)

    def test_linka_para_sementes(self):
        html = self.get("/dashboard").get_data(as_text=True)
        self.assertIn("/sementes", html)

    def test_ordem_alfabetica_dos_membros(self):
        html = self.get("/dashboard").get_data(as_text=True)
        ini = html.index('aria-label="Próximos marcos"')
        trecho = html[ini:html.index("</section>", ini)]
        con = sqlite3.connect(DB)
        nomes = [r[0] for r in con.execute("SELECT name FROM members WHERE active = 1")]
        con.close()
        esperado = sorted(nomes, key=lambda s: s.lower())
        posicoes = [trecho.find(">" + n + "<") for n in esperado]
        self.assertTrue(all(p >= 0 for p in posicoes))
        self.assertEqual(posicoes, sorted(posicoes))

    def test_mostra_o_proximo_marco_e_o_bonus(self):
        ativos = self.ativos()
        for d in ("2026-10-15", "2026-10-16", "2026-10-19"):
            self.inserir(ativos[0], d, "daily")
        html = self.get("/dashboard").get_data(as_text=True)
        self.assertIn("de 5 dias, +3 sementes", html)


class TestProximoMarco(unittest.TestCase):
    """Fase 1.4 (regra pura usada tambem na 1.3): proximo marco de sequencia."""

    def test_antes_do_primeiro_marco(self):
        r = game.proximo_marco(0)
        self.assertEqual(r["alvo"], 5)
        self.assertEqual(r["bonus"], 3)
        self.assertEqual(r["faltam"], 5)
        self.assertFalse(r["feito"])

    def test_no_meio(self):
        r = game.proximo_marco(8)
        self.assertEqual(r["alvo"], 10)
        self.assertEqual(r["bonus"], 5)
        self.assertEqual(r["faltam"], 2)

    def test_exatamente_em_um_marco_aponta_para_o_proximo(self):
        r = game.proximo_marco(5)
        self.assertEqual(r["alvo"], 10)
        self.assertEqual(r["faltam"], 5)

    def test_depois_do_ultimo_marco(self):
        r = game.proximo_marco(40)
        self.assertTrue(r["feito"])
        self.assertIsNone(r["alvo"])
        self.assertIsNone(r["faltam"])

    def test_coerente_com_as_constantes(self):
        # O primeiro alvo e o primeiro marco das constantes.
        self.assertEqual(game.proximo_marco(0)["alvo"], game.SEED_MILESTONES[0][0])


class TestBoasVindas(unittest.TestCase):
    """Fase 1.5: +20 boas-vindas uma vez para quem tem pelo menos 1 presenca."""

    def setUp(self):
        self.dias = game.dias_letivos(
            "2026-10-15", "2026-10-12", 10, {"2026-10-12", "2026-11-02", "2026-11-20"}
        )
        self.semanas = game.semanas_do_projeto(
            "2026-10-12", 10, {"2026-10-12", "2026-11-02", "2026-11-20"}
        )

    def test_sem_presenca_sem_boas_vindas(self):
        r = game.calcular_sementes(self.dias, self.semanas, {}, False)
        self.assertEqual(r["por_boas_vindas"], 0)

    def test_uma_presenca_da_boas_vindas(self):
        regs = {self.dias[0]: {"presente": True}}
        r = game.calcular_sementes(self.dias, self.semanas, regs, False)
        self.assertEqual(r["por_boas_vindas"], game.SEED_BOAS_VINDAS)

    def test_boas_vindas_nao_duplica(self):
        # Varios dias de presenca nao dao boas-vindas repetidas.
        regs = {d: {"presente": True} for d in self.dias[:5]}
        r = game.calcular_sementes(self.dias, self.semanas, regs, False)
        self.assertEqual(r["por_boas_vindas"], game.SEED_BOAS_VINDAS)

    def test_so_falta_nao_da_boas_vindas(self):
        regs = {self.dias[0]: {"faltou": True}}
        r = game.calcular_sementes(self.dias, self.semanas, regs, False)
        self.assertEqual(r["por_boas_vindas"], 0)


class TestEFundador(unittest.TestCase):
    """Fase 1.5: e_fundador puro - presenca em qualquer dia ate fundador_ate."""

    def test_presenca_dentro_do_prazo(self):
        regs = {"2026-10-20": {"presente": True}}
        self.assertTrue(game.e_fundador(regs, "2026-10-23"))

    def test_presenca_depois_do_prazo_nao_conta(self):
        regs = {"2026-10-24": {"presente": True}}
        self.assertFalse(game.e_fundador(regs, "2026-10-23"))

    def test_so_falta_nao_torna_fundador(self):
        regs = {"2026-10-20": {"faltou": True}}
        self.assertFalse(game.e_fundador(regs, "2026-10-23"))

    def test_prazo_vazio_ninguem_e_fundador(self):
        regs = {"2026-10-20": {"presente": True}}
        self.assertFalse(game.e_fundador(regs, ""))


class TestFundadorNaRota(Fase1Base):
    """Fase 1.5: o fundador aparece em get_member_stats e pode equipar o selo."""

    def test_membro_com_presenca_no_prazo_e_fundador(self):
        ativos = self.ativos()
        self.inserir(ativos[0], "2026-10-20", "daily")  # dentro de fundador_ate (23/10)
        with appmod.app.test_request_context():
            db = appmod.get_db()
            stats = get_member_stats_by_id(db, ativos[0])
        self.assertTrue(stats["fundador"])

    def test_membro_sem_presenca_nao_e_fundador(self):
        ativos = self.ativos()
        with appmod.app.test_request_context():
            db = appmod.get_db()
            stats = get_member_stats_by_id(db, ativos[0])
        self.assertFalse(stats["fundador"])

    def test_fundador_equipa_o_selo_via_api(self):
        ativos = self.ativos()
        self.inserir(ativos[0], "2026-10-20", "daily")
        with self.client.session_transaction() as sess:
            sess["eu"] = ativos[0]
        r = self.client.post("/api/loja/equipar", json={
            "member_id": ativos[0], "slot": "acessorio", "item_id": "selo_fundador",
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_nao_fundador_nao_equipa_o_selo(self):
        ativos = self.ativos()  # sem presenca ate o prazo
        with self.client.session_transaction() as sess:
            sess["eu"] = ativos[0]
        r = self.client.post("/api/loja/equipar", json={
            "member_id": ativos[0], "slot": "acessorio", "item_id": "selo_fundador",
        })
        self.assertEqual(r.status_code, 400)


def get_member_stats_by_id(db, member_id):
    return next(s for s in appmod.get_member_stats(db) if s["id"] == member_id)


if __name__ == "__main__":
    unittest.main()
