"""Minigames da aba Meu jardim: Fala pronta, Fechamento pronto, Cuidar da planta e Album da estacao.

Regras que os testes guardam: o premio e por preencher (nunca pelo conteudo), uma vez por dia,
so vale em dia letivo com presenca, e a Fala pronta tem que vir antes da vez da pessoa na daily."""
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "minijogos.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402

DB = str(appmod.DB_PATH)
HOJE = "2026-10-20"          # terca, dia letivo da semana 2
ONTEM = "2026-10-19"         # segunda, o dia letivo anterior


class _HojeFixo(date):
    @classmethod
    def today(cls):
        return date(2026, 10, 20)


# ------------------------------------------------------------ puro: album e premios
class TestAlbumPuro(unittest.TestCase):
    SEMANAS = [["d1", "d2", "d3", "d4", "d5"], ["e1", "e2", "e3", "e4"], [], ["f1", "f2"]]

    def test_revela_com_tres_falas_e_guarda_a_data_da_terceira(self):
        a = game.album_estacao(["d1", "d3", "d5", "d4"], self.SEMANAS)
        self.assertTrue(a[0]["revelada"])
        self.assertEqual(a[0]["data"], "d4")
        self.assertFalse(a[1]["revelada"])

    def test_semana_curta_pede_so_os_dias_que_tem(self):
        a = game.album_estacao(["f1", "f2"], self.SEMANAS)
        self.assertEqual(a[3]["minimo"], 2)
        self.assertTrue(a[3]["revelada"])

    def test_semana_sem_aula_e_folga_e_nao_conta(self):
        a = game.album_estacao([], self.SEMANAS)
        self.assertTrue(a[2]["folga"])
        self.assertFalse(a[2]["revelada"])

    def test_sprint_completa_vira_dourada_so_na_ultima_figurinha(self):
        a = game.album_estacao(["d1", "d2", "d3", "e1", "e2", "e3"], self.SEMANAS)
        self.assertEqual([f["dourada"] for f in a[:2]], [False, True])
        b = game.album_estacao(["d1", "d2", "d3", "e1"], self.SEMANAS)
        self.assertFalse(any(f["dourada"] for f in b))

    def test_sprint_com_semana_de_folga_fecha_com_a_semana_que_teve_aula(self):
        a = game.album_estacao(["f1", "f2"], self.SEMANAS)          # sprint 2 = semana 3 (folga) + 4
        self.assertTrue(a[3]["dourada"])

    def test_premios_so_com_presenca_e_dia_letivo(self):
        reg = {"d1": {"presente": True}, "d2": {"presente": True}, "d3": {"presente": False}}
        jogadas = [("d1", "fala_pronta"), ("d2", "fala_pronta"), ("d3", "fala_pronta"), ("x9", "fala_pronta"),
                   ("d1", "cuidar_regar"), ("d1", "vez_daily"), ("d1", "cuidar")]
        p = game.premios_minijogos(jogadas, self.SEMANAS, reg)
        self.assertEqual(sorted((x["data"], x["valor"]) for x in p),
                         [("d1", game.SEED_CUIDAR), ("d1", game.SEED_FALA_PRONTA), ("d2", game.SEED_FALA_PRONTA)])

    def test_figurinha_e_dourada_entram_no_premio(self):
        reg = {d: {"presente": True} for d in ("d1", "d2", "d3", "e1", "e2", "e3")}
        jogadas = [(d, "fala_pronta") for d in reg]
        p = game.premios_minijogos(jogadas, self.SEMANAS[:2], reg)
        self.assertEqual(sum(x["valor"] for x in p),
                         6 * game.SEED_FALA_PRONTA + 2 * game.SEED_FIGURINHA + game.SEED_ESTACAO_COMPLETA)

    def test_extrato_fecha_com_o_total_tambem_com_minigames(self):
        dias = game.dias_letivos("2026-10-15", "2026-10-12", 10, [])
        semanas = game.semanas_do_projeto("2026-10-12", 10, set())
        reg = {d: {"presente": True, "eventos": {"daily", "dev", "encerramento"}} for d in dias[:12]}
        jogadas = [(d, j) for d in dias[:12] for j in game.MINIJOGOS]
        mj = game.premios_minijogos(jogadas, semanas, reg)
        meta = game.meta_floracao(len(dias))
        est = game.calcular_membro(dias, reg, meta)
        total = game.calcular_sementes(dias, semanas, reg, est["floresceu"], minijogos=mj)
        ext = game.extrato_sementes(dias, semanas, reg, meta, minijogos=mj)
        self.assertEqual(sum(x["valor"] for x in ext), total["total"])
        self.assertEqual(total["por_minijogos"], sum(x["valor"] for x in mj))


# ------------------------------------------------------------ no app
class MinijogosBase(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        p = mock.patch.object(appmod, "date", _HojeFixo)
        p.start()
        self.addCleanup(p.stop)
        antes = os.environ.get("ADMIN_LOCAL")
        os.environ["ADMIN_LOCAL"] = "0"                          # o celular nao e o PC do Scrum
        self.addCleanup(lambda: os.environ.__setitem__("ADMIN_LOCAL", antes) if antes is not None
                        else os.environ.pop("ADMIN_LOCAL", None))
        con = sqlite3.connect(DB)
        self.ids = [r[0] for r in con.execute(
            "SELECT id FROM members WHERE active = 1 AND COALESCE(tipo, 'equipe') = 'equipe' ORDER BY id")]
        con.close()
        self.ana, self.bia = self.ids[:2]
        self.cel = appmod.app.test_client()
        with self.cel.session_transaction() as sess:
            sess["eu"] = self.ana

    def fala(self, campo, valor, tipo="daily", data=HOJE):
        return self.cel.post("/api/ata/minha-fala", json={"data": data, "tipo": tipo, "campo": campo, "valor": valor})

    def jogo(self, nome, **corpo):
        return self.cel.post(f"/api/minijogo/{nome}", json=corpo)

    def presente(self, mid, data=HOJE, eventos=("daily", "dev", "encerramento")):
        con = sqlite3.connect(DB)
        for ev in eventos:
            con.execute("INSERT OR REPLACE INTO attendance (member_id, event_date, event_type, status) "
                        "VALUES (?, ?, ?, 'presente')", (mid, data, ev))
        con.commit()
        con.close()

    def jogadas(self, mid=None):
        con = sqlite3.connect(DB)
        try:
            return {r[0] for r in con.execute("SELECT jogo FROM minijogos WHERE member_id = ? AND data = ?",
                                              (mid or self.ana, HOJE))}
        finally:
            con.close()

    def stats(self, mid=None):
        with appmod.app.test_request_context():
            return next(s for s in appmod.get_member_stats(appmod.get_db()) if s["id"] == (mid or self.ana))


class TestFalaPronta(MinijogosBase):
    def test_precisa_dos_dois_campos(self):
        self.fala("feito", "#101 terminei a tela")
        r = self.jogo("fala-pronta")
        self.assertEqual(r.status_code, 400)
        self.fala("planejado", "#102 comecar a API")
        r = self.jogo("fala-pronta")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["ganhou"], game.SEED_FALA_PRONTA)
        self.assertIn("fala_pronta", self.jogadas())

    def test_uma_vez_por_dia(self):
        self.fala("feito", "a")
        self.fala("planejado", "b")
        self.jogo("fala-pronta")
        self.assertEqual(self.jogo("fala-pronta").get_json()["ganhou"], 0)

    def test_depois_da_vez_na_daily_nao_vale(self):
        self.fala("feito", "a")
        self.fala("planejado", "b")
        pc = appmod.app.test_client()
        os.environ["ADMIN_LOCAL"] = "1"
        pc.post("/api/holofote", json={"member_id": self.ana, "modo": "celular", "tipo": "daily"})
        os.environ["ADMIN_LOCAL"] = "0"
        self.assertIn("vez_daily", self.jogadas())
        r = self.jogo("fala-pronta")
        self.assertEqual(r.status_code, 400)
        self.assertIn("vez", r.get_json()["erro"].lower())

    def test_semente_so_cai_com_presenca(self):
        self.fala("feito", "a")
        self.fala("planejado", "b")
        self.jogo("fala-pronta")
        sem = self.stats()["sementes_ganhas"]
        self.presente(self.ana)
        com = self.stats()["sementes_ganhas"]
        self.assertGreaterEqual(com - sem, game.SEED_FALA_PRONTA)

    def test_sem_login_nao_joga(self):
        r = appmod.app.test_client().post("/api/minijogo/fala-pronta", json={})
        self.assertEqual(r.status_code, 401)

    def test_dia_sem_aula_nao_joga(self):
        class _Sabado(date):
            @classmethod
            def today(cls):
                return date(2026, 10, 24)
        with mock.patch.object(appmod, "date", _Sabado):
            r = self.jogo("fala-pronta")
        self.assertEqual(r.status_code, 400)

    def test_jogo_desconhecido(self):
        self.assertEqual(self.jogo("roleta").status_code, 404)


class TestFechamentoECuidar(MinijogosBase):
    def fechar(self):
        self.fala("feito", "terminei #101", tipo="fechamento")
        self.fala("planejado", "#102", tipo="fechamento")
        return self.jogo("fechamento")

    def test_fechamento_precisa_dos_campos_do_day_closing(self):
        self.fala("feito", "terminei", tipo="fechamento")
        self.assertEqual(self.jogo("fechamento").status_code, 400)
        self.fala("planejado", "amanha", tipo="fechamento")
        r = self.jogo("fechamento")
        self.assertEqual(r.get_json()["ganhou"], game.SEED_FECHAMENTO_PRONTO)

    def test_cuidar_vale_a_qualquer_hora_do_dia(self):
        r = self.jogo("cuidar", acao="regar")                    # sem fechar o dia
        self.assertEqual(r.status_code, 200)

    def test_cuidar_premia_uma_vez_com_os_tres_cuidados(self):
        ganhos = [self.jogo("cuidar", acao=a).get_json()["ganhou"] for a in ("regar", "regar", "adubar", "carinho")]
        self.assertEqual(ganhos, [0, 0, 0, game.SEED_CUIDAR])
        self.assertEqual(self.jogo("cuidar", acao="carinho").get_json()["ganhou"], 0)
        self.assertTrue(self.jogo("cuidar", acao="regar").get_json()["estado"]["cuidar"])

    def test_cuidado_invalido(self):
        self.fechar()
        self.assertEqual(self.jogo("cuidar", acao="podar").status_code, 400)

    def test_extrato_da_pessoa_fecha_com_o_saldo(self):
        self.presente(self.ana)
        self.fala("feito", "a")
        self.fala("planejado", "b")
        self.jogo("fala-pronta")
        self.fechar()
        for a in game.CUIDADOS:
            self.jogo("cuidar", acao=a)
        stats = self.stats()
        with appmod.app.test_request_context():
            ctx = appmod._contexto_sementes(appmod.get_db(), self.ana, None)
        ext = ctx["detalhe"]["extrato"]
        self.assertEqual(ext["ganho"], stats["sementes_ganhas"])
        mj = [x for x in ext["linhas"] if x["fonte"] == "minijogo"]
        self.assertEqual(sum(x["valor"] for x in mj),
                         game.SEED_FALA_PRONTA + game.SEED_FECHAMENTO_PRONTO + game.SEED_CUIDAR)


class TestPaginaMeuJardim(MinijogosBase):
    def test_a_daily_aparece_antes_da_presenca(self):
        h = self.cel.get("/eu").get_data(as_text=True)
        self.assertIn('id="fala-daily"', h)
        self.assertIn("Seu dia no jardim", h)
        self.assertIn('data-minijogo="fala-pronta"', h)
        self.assertIn("Álbum da estação", h)

    def test_o_que_fica_para_amanha_vira_sugestao_sem_salvar(self):
        self.presente(self.ana, data=ONTEM)
        con = sqlite3.connect(DB)
        con.execute("INSERT INTO ata_falas (data, tipo, member_id, feito, planejado) "
                    "VALUES (?, 'fechamento', ?, 'x', 'terminar o #77')", (ONTEM, self.ana))
        con.commit()
        con.close()
        h = self.cel.get("/eu").get_data(as_text=True)
        self.assertIn("terminar o #77", h)
        self.assertIn("data-sugerido", h)
        con = sqlite3.connect(DB)
        salvo = con.execute("SELECT planejado FROM ata_falas WHERE data = ? AND tipo = 'daily' AND member_id = ?",
                            (HOJE, self.ana)).fetchone()
        con.close()
        self.assertTrue(salvo is None or not salvo[0])

    def test_canteiro_aberto_desde_cedo(self):
        h = self.cel.get("/eu").get_data(as_text=True)
        self.assertIn('id="cuidar"', h)
        self.assertIn('data-aberto="1"', h)


class TestCaminhoAteOJardim(MinijogosBase):
    def test_meu_jardim_esta_na_barra_principal(self):
        h = self.cel.get(f"/dia/{HOJE}").get_data(as_text=True)
        nav = h[h.index('<nav class="nav"'):h.index("</nav>", h.index('<nav class="nav"'))]
        self.assertIn("Meu jardim", nav)
        self.assertNotIn("Histórico", nav)                      # foi para as abas do Painel

    def test_hoje_chama_a_pessoa_para_preparar_a_fala(self):
        h = self.cel.get(f"/dia/{HOJE}").get_data(as_text=True)
        self.assertIn("chamada-jardim", h)
        self.assertIn("Preparar minha fala", h)
        self.assertIn("/eu#fala-daily", h)

    def test_hoje_sem_login_convida_a_entrar(self):
        h = appmod.app.test_client().get(f"/dia/{HOJE}").get_data(as_text=True)
        self.assertIn("Seu jardim no celular", h)

    def test_a_chamada_segue_o_passo_do_dia(self):
        self.fala("feito", "a")
        self.fala("planejado", "b")
        self.jogo("fala-pronta")
        h = self.cel.get(f"/dia/{HOJE}").get_data(as_text=True)
        self.assertIn("Cuidar da planta", h)
        self.assertNotIn("Preparar minha fala", h)

    def test_outro_dia_nao_tem_chamada(self):
        h = self.cel.get(f"/dia/{ONTEM}").get_data(as_text=True)
        self.assertNotIn("chamada-jardim", h)

    def test_paginas_de_informacao_ficam_nas_abas_do_painel(self):
        for url in ("/dashboard", "/sementes", "/historico", "/membros"):
            r = self.cel.get(url, follow_redirects=True)
            self.assertIn("painel-abas", r.get_data(as_text=True), url)



class TestAvisarQueNaoVai(MinijogosBase):
    def status(self, evento="daily"):
        con = sqlite3.connect(DB)
        try:
            r = con.execute("SELECT status FROM attendance WHERE member_id = ? AND event_date = ? AND event_type = ?",
                            (self.ana, HOJE, evento)).fetchone()
            return r[0] if r else None
        finally:
            con.close()

    def preencher(self):
        self.fala("feito", "#101 terminei")
        self.fala("planejado", "#102 seguir")

    def test_so_avisar_ja_vale_sem_a_fala(self):
        r = self.jogo("avisar")
        self.assertEqual(r.get_json()["ganhou"], game.SEED_FALA_AVISADA)
        self.assertEqual(self.status(), "justificada")

    def test_avisar_marca_avisou_e_paga_tres(self):
        self.preencher()
        antes = self.stats()["sementes_ganhas"]
        r = self.jogo("avisar")
        self.assertEqual(r.get_json()["ganhou"], game.SEED_FALA_AVISADA)
        self.assertEqual(self.status(), "justificada")
        self.assertIsNone(self.status("encerramento"))                    # so a daily, se nao marcar o dia todo
        self.assertEqual(self.stats()["sementes_ganhas"] - antes, game.SEED_FALA_AVISADA)
        self.assertTrue(r.get_json()["estado"]["fala_avisada"])

    def test_dia_todo_marca_os_outros_eventos(self):
        self.preencher()
        self.jogo("avisar", dia_todo=True)
        self.assertEqual(self.status("encerramento"), "justificada")

    def test_nao_avisa_por_cima_de_presenca_ou_falta(self):
        self.presente(self.ana, eventos=("daily",))
        self.assertEqual(self.jogo("avisar").status_code, 400)
        self.assertEqual(self.status(), "presente")

    def test_se_acabou_indo_vale_a_fala_pronta_e_nao_soma_as_duas(self):
        self.preencher()
        self.jogo("avisar")
        self.jogo("desavisar")
        self.assertIsNone(self.status())
        self.assertNotIn("fala_avisada", self.jogadas())
        self.assertEqual(self.jogo("fala-pronta").get_json()["ganhou"], game.SEED_FALA_PRONTA)

    def test_fala_pronta_recusa_quem_avisou(self):
        self.preencher()
        self.jogo("avisar")
        self.assertEqual(self.jogo("fala-pronta").status_code, 400)

    def test_avisou_e_apareceu_depois_no_dia_continua_valendo(self):
        self.jogo("avisar")
        antes = self.stats()["sementes_ganhas"]
        self.presente(self.ana, eventos=("dev", "encerramento"))             # chegou depois da daily
        mj = [x for x in self._extrato() if x["fonte"] == "minijogo"]
        self.assertIn(game.SEED_FALA_AVISADA, [x["valor"] for x in mj])
        self.assertGreater(self.stats()["sementes_ganhas"], antes)

    def test_se_o_scrum_marca_presenca_na_daily_o_aviso_nao_paga(self):
        self.jogo("avisar")
        self.presente(self.ana, eventos=("daily",))
        mj = [x for x in self._extrato() if x["fonte"] == "minijogo"]
        self.assertNotIn(game.SEED_FALA_AVISADA, [x["valor"] for x in mj])

    def _extrato(self):
        with appmod.app.test_request_context():
            return appmod._contexto_sementes(appmod.get_db(), self.ana, None)["detalhe"]["extrato"]["linhas"]

    def test_aviso_conta_para_o_album(self):
        reg = {d: {"justificada": True} for d in ("d1", "d2", "d3")}
        a = game.premios_minijogos([(d, "fala_avisada") for d in reg], [["d1", "d2", "d3"]], reg)
        self.assertIn(game.SEED_FIGURINHA, [x["valor"] for x in a])

    def test_meu_jardim_mostra_a_data_do_dia(self):
        h = self.cel.get("/eu").get_data(as_text=True)
        self.assertIn("Terça, 20 de outubro", h)

    def test_pagina_mostra_a_opcao_de_avisar(self):
        h = self.cel.get("/eu").get_data(as_text=True)
        self.assertIn("Não vou hoje", h)
        self.assertIn('data-minijogo="avisar"', h)


class _SextaFixa(date):
    @classmethod
    def today(cls):
        return date(2026, 10, 23)


class TestVespera(MinijogosBase):
    """O dia seguinte abre na vespera (so o dia seguinte do calendario, e so se for letivo)."""
    AMANHA = "2026-10-21"

    def jogadas_em(self, data):
        con = sqlite3.connect(DB)
        try:
            return {r[0] for r in con.execute("SELECT jogo FROM minijogos WHERE member_id = ? AND data = ?",
                                              (self.ana, data))}
        finally:
            con.close()

    def test_da_para_deixar_a_fala_de_amanha_pronta(self):
        self.assertEqual(self.fala("feito", "#101 terminei", data=self.AMANHA).status_code, 200)
        self.fala("planejado", "#102 seguir", data=self.AMANHA)
        r = self.jogo("fala-pronta", data=self.AMANHA)
        self.assertEqual(r.status_code, 200)
        self.assertIn("fala_pronta", self.jogadas_em(self.AMANHA))
        self.assertNotIn("fala_pronta", self.jogadas())                  # hoje continua aberto
        self.assertTrue(r.get_json()["estado"]["fala_pronta"])

    def test_fala_de_amanha_so_paga_com_presenca_no_dia(self):
        self.fala("feito", "a", data=self.AMANHA)
        self.fala("planejado", "b", data=self.AMANHA)
        antes = self.stats()["sementes_ganhas"]
        self.jogo("fala-pronta", data=self.AMANHA)
        self.assertEqual(self.stats()["sementes_ganhas"], antes)
        self.presente(self.ana, data=self.AMANHA)
        self.assertGreater(self.stats()["sementes_ganhas"], antes)

    def test_cuidar_e_avisar_de_amanha(self):
        for acao in game.CUIDADOS:
            r = self.jogo("cuidar", acao=acao, data=self.AMANHA)
        self.assertEqual(r.get_json()["ganhou"], game.SEED_CUIDAR)
        self.assertIn("cuidar", self.jogadas_em(self.AMANHA))
        r = self.jogo("avisar", data=self.AMANHA)
        self.assertEqual(r.get_json()["ganhou"], game.SEED_FALA_AVISADA)

    def test_depois_de_amanha_nao_abre(self):
        depois = "2026-10-22"
        self.assertEqual(self.jogo("cuidar", acao="regar", data=depois).status_code, 400)
        self.assertEqual(self.jogo("avisar", data=depois).status_code, 400)
        self.assertEqual(self.fala("feito", "cedo demais", data=depois).status_code, 400)
        self.assertEqual(self.jogadas_em(depois), set())

    def test_o_dia_so_fecha_no_proprio_dia(self):
        self.fala("feito", "a", tipo="fechamento", data=self.AMANHA)
        self.fala("planejado", "b", tipo="fechamento", data=self.AMANHA)
        self.assertEqual(self.jogo("fechamento", data=self.AMANHA).status_code, 400)

    def test_sexta_nao_abre_a_segunda(self):
        with mock.patch.object(appmod, "date", _SextaFixa):
            self.assertEqual(self.jogo("cuidar", acao="regar", data="2026-10-26").status_code, 400)
            h = self.cel.get("/eu?dia=amanha").get_data(as_text=True)
        self.assertNotIn("ritual-dias", h)
        self.assertIn("Sexta, 23 de outubro", h)

    def test_meu_jardim_tem_hoje_e_amanha(self):
        h = self.cel.get("/eu").get_data(as_text=True)
        self.assertIn("ritual-dias", h)
        self.assertIn('data-dia="2026-10-20"', h)
        h = self.cel.get("/eu?dia=amanha").get_data(as_text=True)
        self.assertIn('data-dia="2026-10-21"', h)
        self.assertIn("Quarta, 21 de outubro", h)
        self.assertIn("Minha fala de amanhã", h)
        self.assertIn("Não vou amanhã", h)


if __name__ == "__main__":
    unittest.main()
