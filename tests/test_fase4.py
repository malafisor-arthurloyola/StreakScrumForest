import os
import sqlite3
import sys
import tempfile
import unittest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "fase4.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402
import ata_fmt  # noqa: E402

DB = str(appmod.DB_PATH)
DATA = "2026-10-19"   # dia letivo, sprint 1
DATA2 = "2026-10-20"  # dia util seguinte


class Fase4Base(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        self.client = appmod.app.test_client()

    def ids(self):
        con = sqlite3.connect(DB)
        v = [r[0] for r in con.execute("SELECT id FROM members WHERE active = 1 ORDER BY id")]
        con.close()
        return v

    def presente(self, mid, data, ev="daily"):
        con = sqlite3.connect(DB)
        con.execute("INSERT OR REPLACE INTO attendance (member_id,event_date,event_type,status) "
                    "VALUES (?,?,?,?)", (mid, data, ev, "presente"))
        con.commit()
        con.close()

    def salvar(self, **p):
        return self.client.post("/api/ata/salvar", json=p)


# ---------------------------------------------------------------- schema
class TestSchema(Fase4Base):
    def test_tabelas_e_pks(self):
        con = sqlite3.connect(DB)
        tabs = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("atas", tabs)
        self.assertIn("ata_falas", tabs)
        # PK composta (data,tipo) em atas: inserir duplicado deve conflitar
        con.execute("INSERT INTO atas (data, tipo) VALUES (?, 'daily')", (DATA,))
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute("INSERT INTO atas (data, tipo) VALUES (?, 'daily')", (DATA,))
        con.close()

    def test_idempotente(self):
        appmod.init_db()  # 2a vez nao quebra
        con = sqlite3.connect(DB)
        n = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='atas'").fetchone()[0]
        con.close()
        self.assertEqual(n, 1)

    def test_config_idioma_e_gitlab(self):
        con = sqlite3.connect(DB)
        cfg = dict(con.execute("SELECT chave, valor FROM config"))
        con.close()
        self.assertEqual(cfg.get("idioma_ata"), "en")
        self.assertEqual(cfg.get("gitlab_base_url"), "")


# ---------------------------------------------------------------- recompensa (pura)
class TestRecompensa(unittest.TestCase):
    def setUp(self):
        self.dias = game.dias_letivos("2026-10-15", "2026-10-12", 10,
                                      {"2026-10-12", "2026-11-02", "2026-11-20"})
        self.sem = game.semanas_do_projeto("2026-10-12", 10,
                                           {"2026-10-12", "2026-11-02", "2026-11-20"})

    def _calc(self, **kw):
        return game.calcular_sementes(self.dias, self.sem, {self.dias[0]: {"presente": True}},
                                      False, **kw)

    def test_fala_rende_por_ata(self):
        r = self._calc(atas_com_fala=2)
        self.assertEqual(r["por_ata"], 2 * game.SEED_ATA)

    def test_relator_rende_por_relator(self):
        r = self._calc(atas_relatadas=3)
        self.assertEqual(r["por_relator"], 3 * game.SEED_RELATOR)

    def test_sem_atas_zero(self):
        r = self._calc()
        self.assertEqual(r["por_ata"], 0)
        self.assertEqual(r["por_relator"], 0)

    def test_conteudo_e_tamanho_nao_influem(self):
        # a recompensa e por contagem de atas, nao por tamanho: 1 ata = 1, sempre
        self.assertEqual(self._calc(atas_com_fala=1)["por_ata"], game.SEED_ATA)


class TestRecompensaNaRota(Fase4Base):
    def test_fala_vazia_nao_conta_impedimento_nao_rende(self):
        a = self.ids()[0]
        self.presente(a, DATA)
        # so impedimento preenchido (nenhuma fala) -> nao rende
        self.salvar(data=DATA, tipo="daily", campo="bloqueios", valor="sem acesso")
        with appmod.app.test_request_context():
            cf, rel = appmod._contagem_atas(appmod.get_db(), appmod._dias_letivos(appmod.get_db()))
        self.assertEqual(cf.get(a, 0), 0)  # impedimento nao vira fala
        self.assertEqual(rel.get(a, 0), 0)

    def test_fala_preenchida_conta_uma_vez_por_ata(self):
        a = self.ids()[0]
        self.presente(a, DATA)
        self.salvar(data=DATA, tipo="daily", campo="feito", member_id=a, valor="fiz X")
        self.salvar(data=DATA, tipo="daily", campo="planejado", member_id=a, valor="vou fazer Y")
        with appmod.app.test_request_context():
            cf, _ = appmod._contagem_atas(appmod.get_db(), appmod._dias_letivos(appmod.get_db()))
        self.assertEqual(cf.get(a), 1)  # mesma ata, conta 1

    def test_duas_atas_no_dia_contam_duas(self):
        a = self.ids()[0]
        self.presente(a, DATA)
        self.salvar(data=DATA, tipo="daily", campo="feito", member_id=a, valor="x")
        self.salvar(data=DATA, tipo="fechamento", campo="feito", member_id=a, valor="y")
        with appmod.app.test_request_context():
            cf, _ = appmod._contagem_atas(appmod.get_db(), appmod._dias_letivos(appmod.get_db()))
        self.assertEqual(cf.get(a), 2)

    def test_relator_conta(self):
        a = self.ids()[0]
        self.presente(a, DATA)
        self.salvar(data=DATA, tipo="daily", campo="relator", valor=a)
        with appmod.app.test_request_context():
            _, rel = appmod._contagem_atas(appmod.get_db(), appmod._dias_letivos(appmod.get_db()))
        self.assertEqual(rel.get(a), 1)

    def test_ata_em_dia_nao_letivo_nao_rende(self):
        # 2026-10-24 e sabado (nao letivo): preencher ata nao pode dar semente
        a = self.ids()[0]
        sabado = "2026-10-24"
        self.salvar(data=sabado, tipo="daily", campo="feito", member_id=a, valor="mexi no projeto")
        self.salvar(data=sabado, tipo="daily", campo="relator", valor=a)
        with appmod.app.test_request_context():
            cf, rel = appmod._contagem_atas(appmod.get_db(), appmod._dias_letivos(appmod.get_db()))
        self.assertEqual(cf.get(a, 0), 0)   # fala de sabado nao conta
        self.assertEqual(rel.get(a, 0), 0)  # relatar no sabado tambem nao


# ---------------------------------------------------------------- ata_fmt (modelo exato)
class TestAtaFmt(unittest.TestCase):
    def _ata(self, **kw):
        base = {"tipo": "daily", "data": "2026-08-26", "relator": "Arthur",
                "present": ["Arthur", "Bento"],
                "falas": [{"nome": "Arthur", "feito": "fechei a API #101", "planejado": "revisar PR"},
                          {"nome": "Bento", "feito": "", "planejado": ""}],
                "bloqueios": ""}
        base.update(kw)
        return base

    def test_modelo_en_daily_rotulos_exatos(self):
        t = ata_fmt.montar_texto(self._ata(), "en")
        self.assertIn("Daily — 26/08", t)
        self.assertIn("Scrum: Arthur", t)
        self.assertIn("Present: Arthur, Bento", t)
        self.assertIn("Done:", t)
        self.assertIn("* Arthur: fechei a API #101", t)
        self.assertIn("Doing:", t)
        self.assertIn("Blockers: None", t)   # vazio -> None

    def test_modelo_en_fechamento_rotulos_exatos(self):
        t = ata_fmt.montar_texto(self._ata(tipo="fechamento", quadro_atualizado=True), "en")
        self.assertIn("Day Closing — 26/08", t)
        self.assertIn("Completed today:", t)
        self.assertIn("Carried over:", t)
        self.assertIn("New blockers: None", t)
        self.assertIn("Board updated: yes", t)

    def test_board_updated_no(self):
        t = ata_fmt.montar_texto(self._ata(tipo="fechamento", quadro_atualizado=False), "en")
        self.assertIn("Board updated: no", t)

    def test_present_vazio_vira_none(self):
        t = ata_fmt.montar_texto(self._ata(present=[]), "en")
        self.assertIn("Present: None", t)

    def test_pt_opcional(self):
        t = ata_fmt.montar_texto(self._ata(), "pt")
        self.assertIn("Feito:", t)
        self.assertIn("Fazendo:", t)
        self.assertIn("Impedimentos: Nenhum", t)

    def test_cards_no_texto(self):
        self.assertEqual(ata_fmt.cards_no_texto("fiz #101 e #102, de novo #101"), ["101", "102"])

    def test_etiqueta_sem_link_por_padrao(self):
        html = ata_fmt.etiquetar_cards_html("ver #101", "")
        self.assertIn('<span class="card-tag">#101</span>', html)

    def test_etiqueta_com_link_se_gitlab(self):
        html = ata_fmt.etiquetar_cards_html("ver #101", "https://gitlab.exemplo/g/p/-/issues")
        self.assertIn('<a class="card-tag"', html)
        self.assertIn("/101", html)

    def test_html_escapa_e_etiqueta(self):
        html = ata_fmt.montar_html(self._ata(falas=[{"nome": "A", "feito": "<b>x</b> #5", "planejado": ""}]), "en")
        self.assertIn("&lt;b&gt;", html)  # escapou
        self.assertIn("card-tag", html)   # etiquetou #5


# ---------------------------------------------------------------- relator (rotas)
class TestRelator(Fase4Base):
    def test_present_automatico_e_linhas(self):
        a, b = self.ids()[:2]
        self.presente(a, DATA)
        self.presente(b, DATA)
        html = self.client.get(f"/ata/{DATA}/daily").get_data(as_text=True)
        self.assertEqual(self.client.get(f"/ata/{DATA}/daily").status_code, 200)
        self.assertIn("ata-linha", html)
        self.assertIn('<b id="ata-n-presentes">2</b>', html)
        self.assertIn("data-status=\"presente\"", html)

    def test_autosave_persiste(self):
        a = self.ids()[0]
        self.presente(a, DATA)
        self.salvar(data=DATA, tipo="daily", campo="feito", member_id=a, valor="texto X")
        con = sqlite3.connect(DB)
        v = con.execute("SELECT feito FROM ata_falas WHERE data=? AND tipo='daily' AND member_id=?",
                        (DATA, a)).fetchone()[0]
        con.close()
        self.assertEqual(v, "texto X")

    def test_tipo_invalido_404(self):
        self.assertEqual(self.client.get(f"/ata/{DATA}/xyz").status_code, 404)

    def test_imprimir_en_tem_rotulos(self):
        a = self.ids()[0]
        self.presente(a, DATA)
        self.salvar(data=DATA, tipo="daily", campo="feito", member_id=a, valor="fiz #101")
        h = self.client.get(f"/ata/{DATA}/daily/imprimir").get_data(as_text=True)
        self.assertIn("Done", h)
        self.assertIn("Blockers", h)
        self.assertIn("card-tag", h)

    def test_usar_planejado_de_ontem_aparece(self):
        a = self.ids()[0]
        # ontem (dia util anterior a DATA2 = DATA) tem planejado
        self.presente(a, DATA)
        self.presente(a, DATA2)
        self.salvar(data=DATA, tipo="daily", campo="planejado", member_id=a, valor="terminar o login")
        html = self.client.get(f"/ata/{DATA2}/daily").get_data(as_text=True)
        self.assertIn("usar o que ficou planejado ontem", html)


# ---------------------------------------------------------------- minha fala (/eu)
class TestMinhaFala(Fase4Base):
    def test_sem_login_recusa(self):
        self.assertEqual(self.client.post("/api/ata/minha-fala",
                         json={"data": DATA, "tipo": "daily", "campo": "feito", "valor": "x"}).status_code, 401)

    def test_so_edita_a_propria(self):
        a, b = self.ids()[:2]
        self.presente(a, DATA)
        self.client.post("/eu/criar", json={"member_id": a, "pin": "1234", "pin2": "1234"})
        self.client.post("/api/ata/minha-fala", json={"data": DATA, "tipo": "daily", "campo": "feito", "valor": "meu texto"})
        con = sqlite3.connect(DB)
        falas = con.execute("SELECT member_id, feito FROM ata_falas WHERE data=? AND tipo='daily'", (DATA,)).fetchall()
        con.close()
        self.assertEqual(falas, [(a, "meu texto")])  # so a de A, nunca a de B


# ---------------------------------------------------------------- ata da sprint
class TestAtaSprint(Fase4Base):
    def test_agrupa_cards_e_separa_impedimentos(self):
        a = self.ids()[0]
        self.presente(a, DATA)
        self.salvar(data=DATA, tipo="daily", campo="feito", member_id=a, valor="fiz #101 e #102")
        self.salvar(data=DATA, tipo="daily", campo="bloqueios", valor="travou #205")
        self.salvar(data=DATA, tipo="fechamento", campo="bloqueios", valor="deploy quebrado")
        self.salvar(data=DATA, tipo="fechamento", campo="bloqueios_resolvidos", valor=True)
        r = self.client.get("/ata/sprint/1")
        self.assertEqual(r.status_code, 200)
        h = r.get_data(as_text=True)
        for c in ("#101", "#102", "#205"):
            self.assertIn(c, h)
        self.assertIn("travou", h)         # aberto
        self.assertIn("deploy quebrado", h)  # resolvido
        self.assertIn("Daily", h)

    def test_sprint_invalida_404(self):
        self.assertEqual(self.client.get("/ata/sprint/99").status_code, 404)


class TestUxExtras(Fase4Base):
    def test_polling_estado_do_dia(self):
        a = self.ids()[0]
        self.presente(a, DATA)
        r = self.client.get(f"/api/dia/{DATA}/estado")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertIn("sementes_membros", j)
        self.assertIn("dia_cheio", j)
        celulas = {(c["member_id"], c["evento"]): c["status"] for c in j["celulas"]}
        self.assertEqual(celulas.get((a, "daily")), "presente")

    def test_polling_data_invalida_404(self):
        self.assertEqual(self.client.get("/api/dia/xx/estado").status_code, 404)

    def test_qr_fragmento_sem_html_completo(self):
        h = self.client.get("/qr/daily?fragmento=1").get_data(as_text=True)
        self.assertIn("<svg", h)
        self.assertNotIn("<html", h)

    def test_hoje_tem_botoes_ata_e_qr(self):
        h = self.client.get(f"/dia/{DATA}").get_data(as_text=True)
        self.assertIn("Ata do dia", h)
        self.assertIn("btn-qr-modal", h)


# ---------------------------------------------------------------- ata v2: situacao por pessoa
class TestAtaSituacao(Fase4Base):
    def estado(self, tipo="daily"):
        return self.client.get(f"/api/ata/estado?data={DATA}&tipo={tipo}").get_json()

    def status_db(self, mid, ev="daily"):
        con = sqlite3.connect(DB)
        r = con.execute("SELECT status FROM attendance WHERE member_id=? AND event_date=? AND event_type=?",
                        (mid, DATA, ev)).fetchone()
        con.close()
        return r[0] if r else None

    def test_a_ata_lista_todos_da_equipe_mesmo_sem_presenca(self):
        html = self.client.get(f"/ata/{DATA}/daily").get_data(as_text=True)
        for mid in self.ids():
            self.assertIn(f'data-member-id="{mid}"', html)
        self.assertIn("Quem é o relator", html)
        self.assertIn("ata-status", html)

    def test_relatar_a_fala_marca_presenca_automaticamente(self):
        a = self.ids()[0]
        self.assertIsNone(self.status_db(a))
        r = self.salvar(data=DATA, tipo="daily", campo="feito", member_id=a, valor="fiz o login")
        self.assertEqual(r.get_json().get("status"), "presente")
        self.assertEqual(self.status_db(a), "presente")

    def test_fala_vazia_nao_marca_presenca(self):
        a = self.ids()[0]
        self.salvar(data=DATA, tipo="daily", campo="feito", member_id=a, valor="   ")
        self.assertIsNone(self.status_db(a))

    def test_quem_avisou_continua_avisou_mesmo_com_fala(self):
        a = self.ids()[0]
        self.salvar(data=DATA, tipo="daily", campo="status", member_id=a, valor="justificada")
        self.salvar(data=DATA, tipo="daily", campo="feito", member_id=a, valor="deixei um recado")
        self.assertEqual(self.status_db(a), "justificada")

    def test_botao_de_situacao_define_e_limpa(self):
        a = self.ids()[0]
        self.salvar(data=DATA, tipo="daily", campo="status", member_id=a, valor="presente")
        self.assertEqual(self.status_db(a), "presente")
        self.salvar(data=DATA, tipo="daily", campo="status", member_id=a, valor="")
        self.assertIsNone(self.status_db(a))

    def test_situacao_invalida_recusada(self):
        a = self.ids()[0]
        r = self.salvar(data=DATA, tipo="daily", campo="status", member_id=a, valor="faltou")
        self.assertEqual(r.status_code, 400)

    def test_daily_usa_o_evento_daily_e_o_fechamento_usa_encerramento(self):
        a = self.ids()[0]
        self.salvar(data=DATA, tipo="fechamento", campo="feito", member_id=a, valor="terminei")
        self.assertEqual(self.status_db(a, "encerramento"), "presente")
        self.assertIsNone(self.status_db(a, "daily"))

    def test_present_da_ata_e_so_do_evento_dela(self):
        a, b = self.ids()[:2]
        self.presente(a, DATA, "daily")
        self.presente(b, DATA, "dev")
        con = self._con()
        try:
            ata = appmod._ata_para_fmt(con, DATA, "daily")
        finally:
            con.close()
        self.assertEqual(len(ata["present"]), 1)

    def _con(self):
        con = sqlite3.connect(DB)
        con.row_factory = sqlite3.Row
        return con

    def test_quem_avisou_vai_em_excused_na_exportacao(self):
        a = self.ids()[0]
        self.salvar(data=DATA, tipo="daily", campo="status", member_id=a, valor="justificada")
        h = self.client.get(f"/ata/{DATA}/daily/imprimir").get_data(as_text=True)
        self.assertIn("Excused:", h)

    def test_convidados_ficam_fora_da_ata(self):
        ids = self.ids()
        conv = ids[-1]
        con = sqlite3.connect(DB)
        con.execute("UPDATE members SET tipo = 'convidado' WHERE id = ?", (conv,))
        con.commit()
        con.close()
        html = self.client.get(f"/ata/{DATA}/daily").get_data(as_text=True)
        self.assertNotIn(f'data-member-id="{conv}"', html)

    def test_estado_para_atualizar_sozinho(self):
        a = self.ids()[0]
        self.salvar(data=DATA, tipo="daily", campo="feito", member_id=a, valor="oi")
        self.salvar(data=DATA, tipo="daily", campo="relator", valor=a)
        e = self.estado()
        self.assertTrue(e["ok"])
        self.assertEqual(e["relator_id"], a)
        linha = next(l for l in e["linhas"] if l["id"] == a)
        self.assertEqual(linha["status"], "presente")
        self.assertEqual(linha["feito"], "oi")

    def test_estado_valida_parametros(self):
        self.assertEqual(self.client.get("/api/ata/estado?data=xx&tipo=daily").status_code, 400)
        self.assertEqual(self.client.get(f"/api/ata/estado?data={DATA}&tipo=zzz").status_code, 400)

    def test_relatar_rende_semente_de_ata_para_quem_foi_relatado(self):
        a = self.ids()[0]
        self.salvar(data=DATA, tipo="daily", campo="feito", member_id=a, valor="fiz algo")
        con = self._con()
        with appmod.app.test_request_context():
            st = appmod._stats_membro(con, a)
        con.close()
        self.assertGreaterEqual(st["sementes_ganhas"], 1)


if __name__ == "__main__":
    unittest.main()
