import os
import sqlite3
import sys
import tempfile
import unittest

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "metas_premio.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402

DB = str(appmod.DB_PATH)


def _meta(**kw):
    base = {"titulo": "Entregar o canvas", "prazo": "2026-10-28", "sementes": 5, "para_time": False,
            "cumprida_em": "2026-10-27", "membros": [1]}
    base.update(kw)
    return base


class TestPremiosPuro(unittest.TestCase):
    def test_no_prazo_rende_so_para_quem_foi_escolhido(self):
        m = [_meta(membros=[1, 2])]
        self.assertEqual(game.premios_de_metas(m, 1, [1, 2, 3])[0]["valor"], 5)
        self.assertEqual(game.premios_de_metas(m, 3, [1, 2, 3]), [])

    def test_meta_do_time_vale_para_toda_a_equipe(self):
        m = [_meta(para_time=True, membros=[])]
        self.assertEqual([bool(game.premios_de_metas(m, i, [1, 2, 3])) for i in (1, 2, 3)], [True] * 3)
        self.assertEqual(game.premios_de_metas(m, 9, [1, 2, 3]), [])         # convidado fica de fora

    def test_aberta_ou_fora_do_prazo_nao_rende_nada(self):
        self.assertEqual(game.premios_de_metas([_meta(cumprida_em=None)], 1, [1]), [])
        self.assertEqual(game.premios_de_metas([_meta(cumprida_em="2026-10-29")], 1, [1]), [])

    def test_no_ultimo_dia_do_prazo_ainda_rende(self):
        self.assertEqual(len(game.premios_de_metas([_meta(cumprida_em="2026-10-28")], 1, [1])), 1)

    def test_limite_por_meta(self):
        p = game.premios_de_metas([_meta(sementes=500)], 1, [1])
        self.assertEqual(p[0]["valor"], game.SEED_META_MAX)

    def test_entra_no_total_e_no_extrato(self):
        premios = game.premios_de_metas([_meta()], 1, [1])
        ganho = game.calcular_sementes([], [], {}, False, bonus_metas=sum(x["valor"] for x in premios))
        ext = game.extrato_sementes([], [], {}, 36, metas=premios)
        self.assertEqual(ganho["por_metas"], 5)
        self.assertEqual(sum(x["valor"] for x in ext), ganho["total"])
        self.assertEqual(ext[0]["fonte"], "meta")


class TestMetasPremioNoApp(unittest.TestCase):
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

    def _post(self, **dados):
        return self.client.post("/api/metas-premio", json=dados)

    def _criar(self, **kw):
        dados = {"acao": "criar", "titulo": "Entregar o canvas", "prazo": "2099-01-01", "sementes": 5,
                 "para_time": False, "membros": [self.a]}
        dados.update(kw)
        return self._post(**dados)

    def _saldo(self, mid):
        with appmod.app.test_request_context():
            return next(s for s in appmod.get_member_stats(appmod.get_db()) if s["id"] == mid)

    def _extrato(self, mid):
        with appmod.app.test_request_context():
            return appmod._contexto_sementes(appmod.get_db(), mid)["detalhe"]

    def test_criar_validacoes(self):
        self.assertEqual(self._criar(titulo="  ").status_code, 400)
        self.assertEqual(self._criar(prazo="amanha").status_code, 400)
        self.assertEqual(self._criar(sementes=0).status_code, 400)
        self.assertEqual(self._criar(sementes=game.SEED_META_MAX + 1).status_code, 400)
        self.assertEqual(self._criar(membros=[]).status_code, 400)                # ninguem escolhido
        self.assertEqual(self._criar(para_time=True, membros=[]).status_code, 200)

    def test_meta_aberta_nao_da_sementes(self):
        self._criar()
        self.assertEqual(self._saldo(self.a)["sementes_ganhas"], 0)

    def test_cumprir_no_prazo_da_sementes_so_a_quem_foi_escolhido(self):
        mid = self._criar(prazo="2099-01-01", membros=[self.a, self.b]).get_json()["id"]
        self.assertEqual(self._post(acao="cumprir", id=mid, data="2026-10-27").status_code, 200)
        self.assertEqual(self._saldo(self.a)["sementes_ganhas"], 5)
        self.assertEqual(self._saldo(self.b)["sementes_ganhas"], 5)
        self.assertEqual(self._saldo(self.c)["sementes_ganhas"], 0)

    def test_meta_do_time_da_para_todos_da_equipe(self):
        mid = self._criar(para_time=True, membros=[], sementes=7).get_json()["id"]
        self._post(acao="cumprir", id=mid)
        self.assertTrue(all(self._saldo(i)["sementes_ganhas"] == 7 for i in self.ids))

    def test_fora_do_prazo_nao_da_nada_e_reabrir_limpa(self):
        mid = self._criar(prazo="2020-01-01").get_json()["id"]
        self._post(acao="cumprir", id=mid)                      # hoje e depois do prazo
        self.assertEqual(self._saldo(self.a)["sementes_ganhas"], 0)
        self._post(acao="cumprir", id=mid, data="2019-12-31")
        self.assertEqual(self._saldo(self.a)["sementes_ganhas"], 5)
        self._post(acao="reabrir", id=mid)
        self.assertEqual(self._saldo(self.a)["sementes_ganhas"], 0)

    def test_extrato_mostra_a_meta_e_fecha_com_o_saldo(self):
        mid = self._criar().get_json()["id"]
        self._post(acao="cumprir", id=mid, data="2026-10-27")
        det = self._extrato(self.a)
        metas = [x for x in det["extrato"]["linhas"] if x["fonte"] == "meta"]
        self.assertEqual([(x["valor"], x["detalhe"]) for x in metas], [(5, "Entregar o canvas")])
        self.assertEqual(det["extrato"]["ganho"], self._saldo(self.a)["sementes_ganhas"])
        self.assertEqual(det["ganho"]["por_metas"], 5)

    def test_remover(self):
        mid = self._criar().get_json()["id"]
        self._post(acao="cumprir", id=mid, data="2026-10-27")
        self.assertEqual(self._post(acao="remover", id=mid).status_code, 200)
        self.assertEqual(self._saldo(self.a)["sementes_ganhas"], 0)
        self.assertEqual(self._post(acao="remover", id=mid).status_code, 404)

    def test_so_o_admin_mexe(self):
        os.environ["ADMIN_LOCAL"] = "0"
        try:
            r = self.client.post("/api/metas-premio", json={"acao": "criar"})
            self.assertEqual(r.status_code, 403)
        finally:
            os.environ.pop("ADMIN_LOCAL", None)

    def test_dashboard_mostra_a_secao(self):
        self._criar(titulo="Entregar o backlog")
        h = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn("Metas com recompensa", h)
        self.assertIn("Entregar o backlog", h)

    def test_a_pagina_de_sementes_lista_a_fonte(self):
        h = self.client.get(f"/sementes?m={self.a}").get_data(as_text=True)
        self.assertIn("Metas personalizadas cumpridas", h)


if __name__ == "__main__":
    unittest.main()
