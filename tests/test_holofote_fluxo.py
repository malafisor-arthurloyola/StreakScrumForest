"""Fluxo da rodada de fala (holofote) de ponta a ponta, do jeito que acontece na daily:
o Scrum sorteia, a planta de cada um acende, a pessoa preenche no celular dela ou o Scrum preenche
por ela, e as sementes caem conforme as regras de sempre."""
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "holofote_fluxo.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402

DB = str(appmod.DB_PATH)
HOJE = date.today().isoformat()


class _Celular:
    """Um cliente que NAO e o computador do Scrum: entra pelo PIN (sessao) e so tem o que um visitante tem."""

    def __init__(self, mid=None):
        self.client = appmod.app.test_client()
        if mid is not None:
            with self.client.session_transaction() as sess:
                sess["eu"] = mid

    def _com_visitante(self, fn):
        antes = os.environ.get("ADMIN_LOCAL")
        os.environ["ADMIN_LOCAL"] = "0"
        try:
            return fn()
        finally:
            if antes is None:
                os.environ.pop("ADMIN_LOCAL", None)
            else:
                os.environ["ADMIN_LOCAL"] = antes

    def get(self, url):
        return self._com_visitante(lambda: self.client.get(url))

    def post(self, url, **corpo):
        return self._com_visitante(lambda: self.client.post(url, json=corpo))


class FluxoBase(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        self.pc = appmod.app.test_client()          # o computador do Scrum (localhost = administrador)
        con = sqlite3.connect(DB)
        self.ids = [r[0] for r in con.execute(
            "SELECT id FROM members WHERE active = 1 AND COALESCE(tipo, 'equipe') = 'equipe' ORDER BY id")]
        con.close()
        self.scrum, self.ana, self.bia, self.caio, self.davi = self.ids[:5]

    def ganhas(self, mid):
        with appmod.app.test_request_context():
            return next(s for s in appmod.get_member_stats(appmod.get_db()) if s["id"] == mid)["sementes_ganhas"]

    def holofote(self, mid, modo="celular", tipo="daily", cliente=None):
        c = cliente or self.pc
        if isinstance(c, _Celular):
            return c.post("/api/holofote", member_id=mid, modo=modo, tipo=tipo)
        return c.post("/api/holofote", json={"member_id": mid, "modo": modo, "tipo": tipo})

    def estado(self, cliente=None):
        c = cliente or self.pc
        r = c.get("/api/holofote")
        return r.get_json()

    def status_no_banco(self, mid, evento="daily"):
        con = sqlite3.connect(DB)
        try:
            r = con.execute("SELECT status FROM attendance WHERE member_id = ? AND event_date = ? AND event_type = ?",
                            (mid, HOJE, evento)).fetchone()
            return r[0] if r else None
        finally:
            con.close()


class TestCelularDaPessoa(FluxoBase):
    def test_a_pessoa_preenche_no_proprio_celular_e_o_scrum_ve_o_texto_aparecer(self):
        self.holofote(self.ana)
        cel = _Celular(self.ana)
        antes = self.ganhas(self.ana)
        r = cel.post("/api/ata/minha-fala", data=HOJE, tipo="daily", campo="feito", valor="#52 revisado")
        self.assertEqual(r.status_code, 200)
        vista_do_scrum = self.estado()
        self.assertEqual(vista_do_scrum["falas"]["feito"], "#52 revisado")
        self.assertGreaterEqual(self.ganhas(self.ana) - antes, game.SEED_ATA)       # +1 por ter fala na ata, como sempre
        self.assertEqual(self.status_no_banco(self.ana), "presente")                # estava na vez dela: esta na sala

    def test_no_celular_da_pessoa_o_painel_e_dela_para_editar(self):
        self.holofote(self.ana)
        e = self.estado(_Celular(self.ana))
        self.assertEqual((e["eu"], e["member_id"], e["modo"], e["pode_scrum"]), (self.ana, self.ana, "celular", False))

    def test_o_celular_de_outro_colega_so_le(self):
        self.holofote(self.ana)
        e = self.estado(_Celular(self.bia))
        self.assertEqual((e["eu"], e["member_id"], e["pode_scrum"]), (self.bia, self.ana, False))
        r = _Celular(self.bia).post("/api/ata/salvar", data=HOJE, tipo="daily", campo="feito", member_id=self.ana, valor="invadindo")
        self.assertEqual(r.status_code, 403)

    def test_visitante_nao_acende_nem_apaga_o_holofote(self):
        self.holofote(self.ana)
        self.assertEqual(self.holofote(self.bia, cliente=_Celular(self.caio)).status_code, 403)
        self.assertEqual(self.estado()["member_id"], self.ana)

    def test_sem_login_ninguem_escreve_pelo_celular(self):
        r = _Celular(None).post("/api/ata/minha-fala", data=HOJE, tipo="daily", campo="feito", valor="x")
        self.assertEqual(r.status_code, 401)

    def test_o_campo_de_revisao_nao_rende_semente(self):
        cel = _Celular(self.ana)
        antes = self.ganhas(self.ana)
        cel.post("/api/ata/minha-fala", data=HOJE, tipo="daily", campo="review", valor="#58")
        self.assertEqual(self.ganhas(self.ana), antes)


class TestPresencaPeloCelular(FluxoBase):
    def test_fora_da_vez_escrever_a_fala_nao_marca_presenca(self):
        _Celular(self.ana).post("/api/ata/minha-fala", data=HOJE, tipo="daily", campo="feito", valor="de casa")
        self.assertIsNone(self.status_no_banco(self.ana))

    def test_na_vez_dela_escrever_marca_presenca(self):
        self.holofote(self.ana)
        _Celular(self.ana).post("/api/ata/minha-fala", data=HOJE, tipo="daily", campo="feito", valor="na sala")
        self.assertEqual(self.status_no_banco(self.ana), "presente")

    def test_na_vez_de_outra_pessoa_nao_marca(self):
        self.holofote(self.bia)
        _Celular(self.ana).post("/api/ata/minha-fala", data=HOJE, tipo="daily", campo="feito", valor="fora da vez")
        self.assertIsNone(self.status_no_banco(self.ana))

    def test_na_reuniao_errada_nao_marca(self):
        self.holofote(self.ana, tipo="fechamento")
        _Celular(self.ana).post("/api/ata/minha-fala", data=HOJE, tipo="daily", campo="feito", valor="outra reuniao")
        self.assertIsNone(self.status_no_banco(self.ana))

    def test_quem_avisou_continua_avisado(self):
        self.pc.post("/api/ata/salvar", json={"data": HOJE, "tipo": "daily", "campo": "status", "member_id": self.ana, "valor": "justificada"})
        self.holofote(self.ana)
        _Celular(self.ana).post("/api/ata/minha-fala", data=HOJE, tipo="daily", campo="feito", valor="x")
        self.assertEqual(self.status_no_banco(self.ana), "justificada")

    def test_o_scrum_pede_o_jogo_da_pessoa_para_acender_a_chama(self):
        self.holofote(self.ana)
        _Celular(self.ana).post("/api/ata/minha-fala", data=HOJE, tipo="daily", campo="feito", valor="na sala")
        j = self.pc.get("/api/holofote?comjogo=1").get_json()
        self.assertEqual(j["status"], "presente")
        self.assertTrue(j["jogo_resposta"]["jogo"]["aceso"])


class TestScrumPreenchePorEla(FluxoBase):
    def _scrum_logado(self):
        """O Scrum entra pelo PIN no celular e vira relator: nao depende do computador."""
        cel = _Celular(self.scrum)
        r = cel.post("/api/ata/assumir", data=HOJE, tipo="daily")
        self.assertEqual(r.status_code, 200)
        return cel

    def test_scrum_do_dia_conduz_do_proprio_celular(self):
        cel = self._scrum_logado()
        self.assertEqual(self.holofote(self.ana, modo="scrum", cliente=cel).status_code, 200)
        e = self.estado(cel)
        self.assertEqual((e["modo"], e["pode_scrum"]), ("scrum", True))

    def test_scrum_preenche_a_pessoa_ganha_e_o_scrum_ganha_o_bonus_de_relator(self):
        cel = self._scrum_logado()
        self.holofote(self.ana, modo="scrum", cliente=cel)
        a0, s0 = self.ganhas(self.ana), self.ganhas(self.scrum)
        r = cel.post("/api/ata/salvar", data=HOJE, tipo="daily", campo="feito", member_id=self.ana, valor="fiz o login")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(self.ganhas(self.ana) - a0, game.SEED_ATA)    # a pessoa ganha como se tivesse preenchido
        self.assertGreaterEqual(self.ganhas(self.scrum) - s0, game.SEED_RELATOR)

    def test_bonus_do_relator_tem_limite_por_ata(self):
        cel = self._scrum_logado()
        s0 = self.ganhas(self.scrum)
        for mid in (self.ana, self.bia, self.caio, self.davi):
            cel.post("/api/ata/salvar", data=HOJE, tipo="daily", campo="feito", member_id=mid, valor="algo")
        ganho = self.ganhas(self.scrum) - s0
        self.assertEqual(ganho - self._outros_ganhos_do_scrum(), game.SEED_RELATOR * game.SEED_RELATOR_MAX_POR_ATA)

    def _outros_ganhos_do_scrum(self):
        return 0           # o Scrum nao marcou presenca propria nesse teste, entao so conta o bonus

    def test_preencher_por_ela_marca_a_presenca_e_acende_a_chama(self):
        cel = self._scrum_logado()
        r = cel.post("/api/ata/salvar", data=HOJE, tipo="daily", campo="feito", member_id=self.ana, valor="algo").get_json()
        self.assertEqual(self.status_no_banco(self.ana), "presente")
        self.assertTrue(r["jogo_resposta"]["jogo"]["aceso"])

    def test_scrum_que_so_esta_no_pc_preenche_mas_nao_ganha_bonus(self):
        s0 = self.ganhas(self.scrum)
        self.pc.post("/api/ata/salvar", json={"data": HOJE, "tipo": "daily", "campo": "feito", "member_id": self.ana, "valor": "algo"})
        self.assertEqual(self.ganhas(self.scrum), s0)

    def test_quem_nao_e_o_scrum_nao_preenche_por_ninguem(self):
        r = _Celular(self.ana).post("/api/ata/salvar", data=HOJE, tipo="daily", campo="feito", member_id=self.bia, valor="x")
        self.assertEqual(r.status_code, 403)

    def test_a_ultima_escrita_vence_quando_os_dois_mexem_no_mesmo_campo(self):
        cel = self._scrum_logado()
        cel.post("/api/ata/salvar", data=HOJE, tipo="daily", campo="feito", member_id=self.ana, valor="do scrum")
        _Celular(self.ana).post("/api/ata/minha-fala", data=HOJE, tipo="daily", campo="feito", valor="da propria ana")
        self.holofote(self.ana)
        self.assertEqual(self.estado()["falas"]["feito"], "da propria ana")


class TestPresencaNoPainel(FluxoBase):
    def _status(self, mid, valor, tipo="daily"):
        return self.pc.post("/api/ata/salvar", json={"data": HOJE, "tipo": tipo, "campo": "status", "member_id": mid, "valor": valor})

    def test_presente_acende_a_chama_e_faltou_nao(self):
        self.assertTrue(self._status(self.ana, "presente").get_json()["jogo_resposta"]["jogo"]["aceso"])
        self.assertFalse(self._status(self.caio, "faltou").get_json()["jogo_resposta"]["jogo"]["aceso"])

    def test_avisou_nao_quebra_a_sequencia_nem_ganha_presenca(self):
        r = self._status(self.bia, "justificada").get_json()["jogo_resposta"]["jogo"]
        self.assertEqual(self.status_no_banco(self.bia), "justificada")
        self.assertEqual(r["dia_status"] != "regada", True)

    def test_o_painel_mostra_a_situacao_atual_de_quem_esta_na_vez(self):
        self._status(self.ana, "justificada")
        self.holofote(self.ana)
        self.assertEqual(self.estado()["status"], "justificada")
        self._status(self.ana, "")
        self.assertEqual(self.estado()["status"], "")

    def test_avisou_e_faltou_nao_tiram_semente(self):
        antes = self.ganhas(self.ana)
        self._status(self.ana, "justificada")
        self._status(self.ana, "faltou")
        self.assertEqual(self.ganhas(self.ana), antes)

    def test_preencher_a_fala_nao_desfaz_um_avisou(self):
        self._status(self.ana, "justificada")
        self.pc.post("/api/ata/salvar", json={"data": HOJE, "tipo": "daily", "campo": "feito", "member_id": self.ana, "valor": "mesmo assim"})
        self.assertEqual(self.status_no_banco(self.ana), "justificada")


class TestDayClosingNoHolofote(FluxoBase):
    def test_closing_usa_o_evento_de_encerramento_e_a_ata_do_fechamento(self):
        self.holofote(self.ana, modo="scrum", tipo="fechamento")
        self.pc.post("/api/ata/salvar", json={"data": HOJE, "tipo": "fechamento", "campo": "feito", "member_id": self.ana, "valor": "terminei"})
        self.assertEqual(self.status_no_banco(self.ana, "encerramento"), "presente")
        self.assertIsNone(self.status_no_banco(self.ana, "daily"))
        e = self.estado()
        self.assertEqual((e["tipo"], e["falas"]["feito"], e["status"]), ("fechamento", "terminei", "presente"))

    def test_trocar_a_reuniao_nao_mistura_as_falas(self):
        self.pc.post("/api/ata/salvar", json={"data": HOJE, "tipo": "daily", "campo": "feito", "member_id": self.ana, "valor": "da daily"})
        self.holofote(self.ana, tipo="fechamento")
        self.assertEqual(self.estado()["falas"]["feito"], "")
        self.holofote(self.ana, tipo="daily")
        self.assertEqual(self.estado()["falas"]["feito"], "da daily")


class TestVidaDoHolofote(FluxoBase):
    def test_encerrar_apaga_para_todos(self):
        self.holofote(self.ana)
        self.holofote(None)
        self.assertIsNone(self.estado(_Celular(self.bia))["member_id"])

    def test_passar_para_a_proxima_volta_ao_modo_celular(self):
        self.holofote(self.ana, modo="scrum")
        self.holofote(self.bia)                       # o controle da rodada manda 'celular' por padrao
        e = self.estado()
        self.assertEqual((e["member_id"], e["modo"]), (self.bia, "celular"))

    def test_pessoa_inexistente_ou_inativa_e_recusada(self):
        self.assertEqual(self.holofote(99999).status_code, 400)
        self.pc.post(f"/api/membros/{self.davi}", json={"active": False})
        con = sqlite3.connect(DB)
        ativo = con.execute("SELECT active FROM members WHERE id = ?", (self.davi,)).fetchone()[0]
        con.close()
        if not ativo:
            self.assertEqual(self.holofote(self.davi).status_code, 400)

    def test_holofote_esquecido_apaga_sozinho(self):
        self.holofote(self.ana)
        con = sqlite3.connect(DB)
        con.execute("UPDATE config SET valor = datetime('now', '-4 hours') WHERE chave = 'holofote_em'")
        con.commit()
        con.close()
        self.assertIsNone(self.estado()["member_id"])

    def test_qualquer_pagina_do_site_carrega_o_painel(self):
        for url in ("/", "/dashboard", "/loja?m=%d" % self.ana, "/sementes?m=%d" % self.ana):
            h = self.pc.get(url, follow_redirects=True).get_data(as_text=True)
            self.assertIn("holofote.js", h, url)


if __name__ == "__main__":
    unittest.main()
