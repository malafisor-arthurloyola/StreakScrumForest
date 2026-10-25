import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "papeis.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402

DB = str(appmod.DB_PATH)
HOJE = date.today().isoformat()
DATA = "2026-10-19"
# um visitante: outro aparelho (celular) falando com o servidor pela rede
REMOTO = {"environ_overrides": {"REMOTE_ADDR": "192.168.0.23"}, "base_url": "http://192.168.0.10:5000"}


class PapeisBase(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        os.environ.pop("ADMIN_CODE", None)
        os.environ.pop("ADMIN_LOCAL", None)
        appmod.TENTATIVAS.clear()
        self.client = appmod.app.test_client()

    def ids(self):
        con = sqlite3.connect(DB)
        v = [r[0] for r in con.execute("SELECT id FROM members WHERE active = 1 ORDER BY id")]
        con.close()
        return v

    def post(self, url, json=None, **kw):
        return self.client.post(url, json=json or {}, **{**REMOTO, **kw})

    def get(self, url, **kw):
        return self.client.get(url, **{**REMOTO, **kw})

    def entrar_como(self, mid):
        with self.client.session_transaction(base_url=REMOTO["base_url"]) as sess:
            sess["eu"] = mid

    def fazer_relator(self, mid, data=None):
        con = sqlite3.connect(DB)
        con.execute("INSERT OR IGNORE INTO atas (data, tipo) VALUES (?, 'daily')", (data or HOJE,))
        con.execute("UPDATE atas SET relator_id = ? WHERE data = ? AND tipo = 'daily'", (mid, data or HOJE))
        con.commit()
        con.close()


class TestVisitanteSoVe(PapeisBase):
    def test_visitante_nao_marca_presenca_de_ninguem(self):
        a = self.ids()[0]
        r = self.post("/api/attendance", {"member_id": a, "event_date": DATA, "event_type": "daily", "status": "presente"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("administrador", r.get_json()["erro"])

    def test_visitante_nao_marca_todos(self):
        r = self.post("/api/attendance/marcar_todos", {"event_date": DATA, "event_type": "daily"})
        self.assertEqual(r.status_code, 403)

    def test_visitante_nao_edita_ata(self):
        a = self.ids()[0]
        r = self.post("/api/ata/salvar", {"data": DATA, "tipo": "daily", "campo": "feito", "member_id": a, "valor": "x"})
        self.assertEqual(r.status_code, 403)

    def test_visitante_nao_mexe_em_membros_calendario_e_metas(self):
        self.assertEqual(self.post("/api/membros", {"name": "Fulano"}).status_code, 403)
        self.assertEqual(self.post(f"/api/membros/{self.ids()[0]}", {"name": "X"}).status_code, 403)
        self.assertEqual(self.post(f"/api/membros/{self.ids()[0]}/excluir", {"confirmar_nome": "x"}).status_code, 403)
        self.assertEqual(self.post("/api/calendario", {"num_semanas": 3}).status_code, 403)
        self.assertEqual(self.post("/api/feriados", {"data": DATA, "nome": "x"}).status_code, 403)
        self.assertEqual(self.post("/api/metas", {"acao": "sugeridas", "sprint": 1}).status_code, 403)

    def test_visitante_nao_abre_o_qr_nem_baixa_o_banco(self):
        self.assertEqual(self.get("/qr/daily").status_code, 403)
        self.assertEqual(self.get("/admin/baixar-banco").status_code, 403)

    def test_visitante_ve_as_abas(self):
        for url in (f"/dia/{DATA}", "/dashboard", "/historico", "/membros", "/calendario", "/sementes",
                    "/loja", f"/ata/{DATA}/daily", "/ata/sprint/1"):
            self.assertEqual(self.get(url).status_code, 200, url)

    def test_ata_para_visitante_vem_desabilitada(self):
        h = self.get(f"/ata/{DATA}/daily").get_data(as_text=True)
        self.assertIn("só vendo esta ata", h)
        self.assertIn("disabled", h)
        self.assertNotIn("btn-qr-modal", h)

    def test_hoje_para_visitante_sem_botoes_de_marcar_todos(self):
        h = self.get(f"/dia/{DATA}").get_data(as_text=True)
        self.assertIn("somente-leitura", h)
        self.assertIn('data-admin="0"', h)

    def test_visitante_ainda_pode_preencher_a_propria_fala_e_presenca_pelo_qr(self):
        a = self.ids()[0]
        self.entrar_como(a)
        r = self.post("/api/ata/minha-fala", {"data": HOJE, "tipo": "daily", "campo": "feito", "valor": "fiz"})
        self.assertEqual(r.status_code, 200)


class TestQuemEAdmin(PapeisBase):
    def test_quem_esta_no_computador_e_admin(self):
        a = self.ids()[0]
        r = self.client.post("/api/attendance", json={"member_id": a, "event_date": DATA, "event_type": "daily", "status": "presente"})
        self.assertEqual(r.status_code, 200)   # test client = localhost

    def test_admin_local_pode_ser_desligado(self):
        os.environ["ADMIN_LOCAL"] = "0"
        try:
            r = self.client.post("/api/attendance", json={"member_id": self.ids()[0], "event_date": DATA,
                                                          "event_type": "daily", "status": "presente"})
            self.assertEqual(r.status_code, 403)
        finally:
            os.environ.pop("ADMIN_LOCAL", None)

    def test_proxy_nao_conta_como_computador(self):
        r = self.client.post("/api/attendance", json={"member_id": self.ids()[0], "event_date": DATA,
                                                      "event_type": "daily", "status": "presente"},
                             headers={"X-Forwarded-For": "203.0.113.5"})
        self.assertEqual(r.status_code, 403)

    def test_scrum_do_dia_logado_no_celular_e_admin(self):
        a = self.ids()[0]
        self.fazer_relator(a)
        self.entrar_como(a)
        r = self.post("/api/attendance", {"member_id": self.ids()[1], "event_date": DATA, "event_type": "daily", "status": "presente"})
        self.assertEqual(r.status_code, 200)

    def test_quem_nao_e_o_scrum_continua_visitante(self):
        a, b = self.ids()[:2]
        self.fazer_relator(a)
        self.entrar_como(b)
        r = self.post("/api/attendance", {"member_id": a, "event_date": DATA, "event_type": "daily", "status": "presente"})
        self.assertEqual(r.status_code, 403)

    def test_scrum_de_outro_dia_nao_vale_hoje(self):
        a = self.ids()[0]
        self.fazer_relator(a, data="2020-01-01")
        self.entrar_como(a)
        r = self.post("/api/attendance", {"member_id": a, "event_date": DATA, "event_type": "daily", "status": "presente"})
        self.assertEqual(r.status_code, 403)

    def test_scrum_ve_o_botao_de_qr_na_ata(self):
        a = self.ids()[0]
        self.fazer_relator(a)
        self.entrar_como(a)
        h = self.get(f"/ata/{DATA}/daily").get_data(as_text=True)
        self.assertIn("btn-qr-modal", h)
        self.assertIn('data-pode-editar="1"', h)

    def test_admin_no_computador_ve_o_botao_de_qr_na_ata_e_no_hoje(self):
        self.assertIn("btn-qr-modal", self.client.get(f"/ata/{DATA}/daily").get_data(as_text=True))
        self.assertIn("btn-qr-modal", self.client.get(f"/dia/{DATA}").get_data(as_text=True))

    def test_codigo_de_admin(self):
        os.environ["ADMIN_CODE"] = "segredo-adm"
        try:
            ruim = self.client.post("/admin/entrar", data={"codigo": "errado"}, **REMOTO)
            self.assertEqual(ruim.status_code, 401)
            self.assertEqual(self.post("/api/membros", {"name": "Fulano"}).status_code, 403)
            bom = self.client.post("/admin/entrar", data={"codigo": "segredo-adm"}, **REMOTO)
            self.assertEqual(bom.status_code, 302)
            self.assertEqual(self.post("/api/membros", {"name": "Fulano"}).status_code, 200)
            self.client.get("/admin/sair", **REMOTO)
            self.assertEqual(self.post("/api/membros", {"name": "Outro"}).status_code, 403)
        finally:
            os.environ.pop("ADMIN_CODE", None)

    def test_codigo_de_admin_bloqueia_apos_erros(self):
        os.environ["ADMIN_CODE"] = "segredo-adm"
        try:
            for _ in range(appmod.MAX_ERROS):
                self.client.post("/admin/entrar", data={"codigo": "x"}, **REMOTO)
            r = self.client.post("/admin/entrar", data={"codigo": "segredo-adm"}, **REMOTO)
            self.assertEqual(r.status_code, 429)
        finally:
            os.environ.pop("ADMIN_CODE", None)

    def test_sem_admin_code_a_pagina_explica(self):
        h = self.get("/admin/entrar").get_data(as_text=True)
        self.assertIn("não está configurado", h)


class TestLojaSoDoDono(PapeisBase):
    def _dar_sementes(self, mid):
        con = sqlite3.connect(DB)
        for d in ("2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22"):
            for ev in ("daily", "dev", "encerramento"):
                con.execute("INSERT OR REPLACE INTO attendance (member_id, event_date, event_type, status) VALUES (?,?,?,'presente')",
                            (mid, d, ev))
        con.commit()
        con.close()

    def test_sem_login_nao_compra(self):
        a = self.ids()[0]
        self._dar_sementes(a)
        r = self.client.post("/api/loja/comprar", json={"member_id": a, "item_id": "girassol"}, **REMOTO)
        self.assertEqual(r.status_code, 403)

    def test_outra_pessoa_nao_compra_pela_sua(self):
        a, b = self.ids()[:2]
        self._dar_sementes(a)
        self.entrar_como(b)
        r = self.client.post("/api/loja/comprar", json={"member_id": a, "item_id": "girassol"}, **REMOTO)
        self.assertEqual(r.status_code, 403)

    def test_o_admin_escolhe_um_perfil_e_compra_por_ele(self):
        a, b = self.ids()[:2]
        self._dar_sementes(a)
        self.entrar_como(b)
        self.fazer_relator(b)                 # b e o Scrum de hoje (admin)
        r = self.client.post("/api/loja/comprar", json={"member_id": a, "item_id": "girassol"}, **REMOTO)
        self.assertEqual(r.status_code, 200)

    def test_o_computador_tambem_compra_por_qualquer_perfil(self):
        a = self.ids()[0]
        self._dar_sementes(a)
        r = self.client.post("/api/loja/comprar", json={"member_id": a, "item_id": "girassol"})  # localhost
        self.assertEqual(r.status_code, 200)

    def test_admin_ve_acoes_na_loja_de_outro(self):
        a = self.ids()[0]
        h = self.client.get(f"/loja?m={a}").get_data(as_text=True)   # localhost = admin
        self.assertIn("var PODE_AGIR = true", h)

    def test_dono_compra_equipa_e_desfaz(self):
        a = self.ids()[0]
        self._dar_sementes(a)
        self.entrar_como(a)
        r = self.client.post("/api/loja/comprar", json={"member_id": a, "item_id": "girassol"}, **REMOTO)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.post("/api/loja/equipar", json={"member_id": a, "slot": "especie", "item_id": "girassol"}, **REMOTO).status_code, 200)

    def test_loja_redireciona_para_a_minha_quando_logado(self):
        a = self.ids()[0]
        self.entrar_como(a)
        r = self.client.get("/loja", **REMOTO)
        self.assertEqual(r.status_code, 302)
        self.assertIn(f"m={a}", r.headers["Location"])

    def test_ver_a_loja_de_outro_nao_mostra_acoes(self):
        a, b = self.ids()[:2]
        self.entrar_como(a)
        h = self.client.get(f"/loja?m={b}", **REMOTO).get_data(as_text=True)
        self.assertIn("vendo a loja de outra pessoa", h)
        self.assertIn("var PODE_AGIR = false", h)


class TestRelatorEscreveDeQualquerAparelho(PapeisBase):
    """O relator (inclusive num PC fora do localhost) escreve a ata da sua propria ata."""

    def _salvar(self, data, mid, valor="fiz algo"):
        return self.post("/api/ata/salvar", {"data": data, "tipo": "daily", "campo": "feito",
                                              "member_id": mid, "valor": valor})

    def test_assumir_exige_login(self):
        r = self.post("/api/ata/assumir", {"data": DATA, "tipo": "daily"})
        self.assertEqual(r.status_code, 401)

    def test_logado_assume_e_passa_a_poder_editar_aquela_ata(self):
        a, b = self.ids()[:2]
        self.entrar_como(a)
        self.assertEqual(self._salvar(DATA, b).status_code, 403)       # ainda so visitante
        self.assertEqual(self.post("/api/ata/assumir", {"data": DATA, "tipo": "daily"}).status_code, 200)
        self.assertEqual(self._salvar(DATA, b).status_code, 200)       # agora e o relator (data != hoje)

    def test_relator_de_uma_ata_nao_edita_outra(self):
        a, b = self.ids()[:2]
        self.entrar_como(a)
        self.post("/api/ata/assumir", {"data": DATA, "tipo": "daily"})
        self.assertEqual(self._salvar("2026-10-20", b).status_code, 403)

    def test_nao_toma_o_lugar_de_outro_relator(self):
        a, b = self.ids()[:2]
        self.fazer_relator(a, data=DATA)
        self.entrar_como(b)
        r = self.post("/api/ata/assumir", {"data": DATA, "tipo": "daily"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self._salvar(DATA, a).status_code, 403)

    def test_quem_ja_e_o_relator_pode_assumir_de_novo_sem_erro(self):
        a = self.ids()[0]
        self.entrar_como(a)
        self.post("/api/ata/assumir", {"data": DATA, "tipo": "daily"})
        self.assertEqual(self.post("/api/ata/assumir", {"data": DATA, "tipo": "daily"}).status_code, 200)

    def test_convidado_nao_assume(self):
        conv = self.ids()[-1]
        con = sqlite3.connect(DB)
        con.execute("UPDATE members SET tipo = 'convidado' WHERE id = ?", (conv,))
        con.commit()
        con.close()
        self.entrar_como(conv)
        self.assertEqual(self.post("/api/ata/assumir", {"data": DATA, "tipo": "daily"}).status_code, 403)

    def test_pagina_do_relator_vem_editavel_e_a_do_visitante_oferece_entrar(self):
        a = self.ids()[0]
        visitante = self.get(f"/ata/{DATA}/daily").get_data(as_text=True)
        self.assertIn("Entrar com o meu PIN", visitante)
        self.entrar_como(a)
        logado = self.get(f"/ata/{DATA}/daily").get_data(as_text=True)
        self.assertIn("Assumir como relator desta ata", logado)
        self.post("/api/ata/assumir", {"data": DATA, "tipo": "daily"})
        relator = self.get(f"/ata/{DATA}/daily").get_data(as_text=True)
        self.assertIn('data-pode-editar="1"', relator)
        self.assertNotIn("Assumir como relator", relator)

    def test_login_volta_para_a_ata(self):
        h = self.get(f"/eu?next=/ata/{DATA}/daily").get_data(as_text=True)
        self.assertIn("destinoDepoisDoLogin", h)


if __name__ == "__main__":
    unittest.main()
