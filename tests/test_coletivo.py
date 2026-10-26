import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from unittest import mock

# O banco de teste e sempre um arquivo temporario; nunca o banco real.
_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "coletivo.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402

DB = str(appmod.DB_PATH)


def _dias():
    return game.dias_letivos("2026-10-15", "2026-10-12", 10,
                             {"2026-10-12", "2026-11-02", "2026-11-20"})


class ColetivoBase(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        self.client = appmod.app.test_client()
        self.dias = _dias()

    def presencas(self, member_ids, n, status="presente"):
        con = sqlite3.connect(DB)
        for mid in member_ids:
            for d in self.dias[:n]:
                con.execute(
                    "INSERT OR REPLACE INTO attendance (member_id, event_date, event_type, status) "
                    "VALUES (?,?,?,?)", (mid, d, "daily", status),
                )
        con.commit()
        con.close()

    def todos(self):
        con = sqlite3.connect(DB)
        ids = [r[0] for r in con.execute("SELECT id FROM members WHERE active = 1")]
        con.close()
        return ids

    def get(self, url):
        return self.client.get(url)

    def meta(self, **dados):
        return self.client.post("/api/metas", json=dados)


class _HojeFixo(date):
    """Fixa o 'hoje' do app na Sprint 1, para o teste nao depender do relogio."""
    @classmethod
    def today(cls):
        return date(2026, 10, 21)


class TestMetas(ColetivoBase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(appmod, "date", _HojeFixo)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_adicionar_e_remover(self):
        r = self.meta(acao="adicionar", sprint=1, tipo="presenca_pct", alvo=90)
        self.assertEqual(r.status_code, 200)
        html = self.get("/dashboard").get_data(as_text=True)
        self.assertIn("90%", html)
        mid = r.get_json()["id"]
        self.assertEqual(self.meta(acao="remover", id=mid).status_code, 200)

    def test_tipo_invalido(self):
        self.assertEqual(self.meta(acao="adicionar", sprint=1, tipo="xyz", alvo=5).status_code, 400)

    def test_alvo_invalido(self):
        self.assertEqual(self.meta(acao="adicionar", sprint=1, tipo="dias_cheios", alvo=0).status_code, 400)
        self.assertEqual(self.meta(acao="adicionar", sprint=1, tipo="presenca_pct", alvo=150).status_code, 400)

    def test_meta_cumprida_pelos_dias_cheios(self):
        self.presencas(self.todos(), 2)
        r = self.meta(acao="adicionar", sprint=1, tipo="dias_cheios", alvo=2)
        self.assertEqual(r.status_code, 200)
        html = self.get("/dashboard").get_data(as_text=True)
        self.assertIn("meta-cumprida", html)

    def test_metas_sugeridas(self):
        r = self.meta(acao="sugerir", sprint=1)
        self.assertEqual(r.status_code, 200)
        con = sqlite3.connect(DB)
        n = con.execute("SELECT COUNT(*) FROM metas_sprint WHERE sprint = 1").fetchone()[0]
        con.close()
        self.assertGreaterEqual(n, 2)
        # sugerir de novo nao duplica
        self.meta(acao="sugerir", sprint=1)
        con = sqlite3.connect(DB)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM metas_sprint WHERE sprint = 1").fetchone()[0], n)
        con.close()


class TestPaginas(ColetivoBase):
    def test_painel_tem_as_secoes_novas(self):
        html = self.get("/dashboard").get_data(as_text=True)
        for trecho in ("Metas da Sprint", "Bosque da equipe", "Trilha das semanas", "Marcos do jardim"):
            self.assertIn(trecho, html)

    def test_resumo_da_sprint(self):
        self.presencas(self.todos(), 3)
        r = self.get("/sprint/1")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Sprint 1", html)
        self.assertIn("Presença por evento", html)

    def test_sprint_inexistente(self):
        self.assertEqual(self.get("/sprint/99").status_code, 404)
        self.assertEqual(self.get("/sprint/0").status_code, 404)

    def test_perfil_do_membro(self):
        self.presencas([1], 6)
        r = self.get("/membro/1")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("Trilha das 10 semanas", html)
        self.assertIn("Calendário de presença", html)

    def test_perfil_inexistente(self):
        self.assertEqual(self.get("/membro/999").status_code, 404)

    def test_hoje_abre(self):
        self.assertEqual(self.get("/dia/2026-10-19").status_code, 200)


class TestBosqueEMarcos(ColetivoBase):
    def test_quem_floresceu_entra_no_bosque(self):
        self.presencas([1], len(self.dias))
        html = self.get("/dashboard").get_data(as_text=True)
        self.assertIn('class="arvore-bosque"', html)

    def test_sem_floresceu_bosque_vazio(self):
        html = self.get("/dashboard").get_data(as_text=True)
        self.assertNotIn('class="arvore-bosque"', html)
        self.assertIn("Ninguém floresceu ainda", html)

    def test_fonte_aparece_com_25_por_cento(self):
        self.presencas(self.todos(), 10)  # 10/36 = 28% de cada planta
        html = self.get("/dia/2026-10-19").get_data(as_text=True)
        self.assertIn('class="fonte"', html)

    def test_fonte_nao_aparece_no_comeco(self):
        html = self.get("/dia/2026-10-19").get_data(as_text=True)
        self.assertNotIn('class="fonte"', html)

    def test_arvore_do_time_com_100_por_cento(self):
        self.presencas(self.todos(), len(self.dias))
        html = self.get("/dia/2026-10-19").get_data(as_text=True)
        self.assertIn('class="arvore-time"', html)


class TestDestaquesLogica(unittest.TestCase):
    def ativos(self, *dados):
        return [
            {"name": n, "streak": st, "melhor_streak": mb, "dias_presentes": dp, "floresceu": fl}
            for n, st, mb, dp, fl in dados
        ]

    def por_id(self, destaques):
        return {d["id"]: d for d in destaques}

    def test_empate_lista_todos_os_lideres(self):
        a = self.ativos(("Ana", 3, 3, 3, False), ("Bia", 3, 3, 3, False),
                        ("Caio", 1, 1, 1, False), ("Duda", 0, 0, 0, False))
        d = self.por_id(appmod._destaques(a))
        self.assertEqual(d["melhor_sequencia"]["nomes"], ["Ana", "Bia"])
        self.assertEqual(d["melhor_sequencia"]["valor"], 3)
        self.assertEqual(d["streak_atual"]["nomes"], ["Ana", "Bia"])

    def test_lider_unico(self):
        a = self.ativos(("Ana", 5, 5, 5, False), ("Bia", 2, 2, 2, False))
        d = self.por_id(appmod._destaques(a))
        self.assertEqual(d["mais_constante"]["nomes"], ["Ana"])

    def test_ninguem_com_zero_aparece(self):
        a = self.ativos(("Ana", 0, 0, 0, False), ("Bia", 0, 0, 0, False))
        self.assertEqual(appmod._destaques(a), [])

    def test_quem_floresceu(self):
        a = self.ativos(("Ana", 1, 1, 30, True), ("Bia", 0, 0, 3, False), ("Caio", 1, 1, 36, True))
        d = self.por_id(appmod._destaques(a))
        self.assertEqual(d["floresceram"]["nomes"], ["Ana", "Caio"])
        self.assertEqual(d["floresceram"]["valor"], 2)

    def test_formatar_nomes(self):
        f = appmod.formatar_nomes
        self.assertEqual(f(["Ana"], 7), "Ana")
        self.assertEqual(f(["Ana", "Bia"], 7), "Ana e Bia")
        self.assertEqual(f(["Ana", "Bia", "Caio"], 7), "Ana, Bia e Caio")
        self.assertEqual(f(["Ana", "Bia", "Caio", "Duda", "Edu"], 7), "Ana, Bia, Caio e mais 2")
        self.assertEqual(f(["Ana", "Bia", "Caio"], 3), "Todo o time")
        self.assertEqual(f(["Ana"], 1), "Ana")


class TestDestaquesNaPagina(ColetivoBase):
    def test_empate_aparece_na_pagina(self):
        self.presencas([1, 2, 3], 3)  # Arthur, Bento e Dominique com 3 dias
        html = self.get("/dashboard").get_data(as_text=True)
        trecho = html[html.index('aria-label="Destaques"'):]
        for nome in ("Arthur", "Bento", "Dominique"):
            self.assertIn(nome, trecho)


class TestPanorama(ColetivoBase):
    def panorama(self, periodo, hoje="2026-10-21"):
        with appmod.app.test_request_context():
            db = appmod.get_db()
            ctx = appmod._base_coletivo(db)
            return appmod._panorama(db, ctx, periodo, hoje=hoje)

    def celula(self, p, data):
        for sem in p["semanas"]:
            for d in sem["dias"]:
                if d["data"] == data:
                    return d
        return None

    def test_projeto_tem_as_10_semanas_de_7_dias(self):
        p = self.panorama("projeto")
        self.assertEqual(len(p["semanas"]), 10)
        self.assertTrue(all(len(s["dias"]) == 7 for s in p["semanas"]))

    def test_sprint_tem_duas_semanas(self):
        p = self.panorama("sprint")
        self.assertEqual([s["n"] for s in p["semanas"]], [1, 2])

    def test_semana_atual_tem_uma_semana(self):
        p = self.panorama("semana")
        self.assertEqual([s["n"] for s in p["semanas"]], [2])

    def test_periodo_invalido_vira_projeto(self):
        self.assertEqual(len(self.panorama("xyz")["semanas"]), 10)

    def test_niveis_do_time_por_dia(self):
        todos = self.todos()
        self.presencas(todos, 1)            # 15/10: todo mundo
        self.presencas(todos[:1], 2)        # 16/10: so um
        p = self.panorama("projeto")
        self.assertEqual(self.celula(p, "2026-10-15")["nivel"], 4)
        self.assertEqual(self.celula(p, "2026-10-16")["nivel"], 1)

    def test_estados_especiais(self):
        p = self.panorama("projeto", hoje="2026-10-21")
        self.assertEqual(self.celula(p, "2026-10-12")["estado"], "feriado")
        self.assertEqual(self.celula(p, "2026-10-17")["estado"], "fds")
        self.assertEqual(self.celula(p, "2026-10-30")["estado"], "futuro")
        self.assertEqual(self.celula(p, "2026-10-21")["estado"], "hoje")
        self.assertEqual(self.celula(p, "2026-10-20")["estado"], "vazio")

    def test_uma_linha_por_pessoa_com_as_mesmas_semanas(self):
        p = self.panorama("projeto")
        self.assertEqual(len(p["linhas"]), len(self.todos()))
        self.assertTrue(all(len(l["semanas"]) == 10 for l in p["linhas"]))

    def test_linha_da_pessoa_reflete_a_presenca(self):
        self.presencas([1], 2)
        p = self.panorama("projeto")
        linha = next(l for l in p["linhas"] if l["id"] == 1)
        celulas = {c["data"]: c["estado"] for sem in linha["semanas"] for c in sem}
        self.assertEqual(celulas["2026-10-15"], "presente")
        self.assertEqual(celulas["2026-10-16"], "presente")
        self.assertEqual(celulas["2026-10-19"], "vazio")

    def test_resumo_do_periodo(self):
        todos = self.todos()
        self.presencas(todos, 2)
        r = self.panorama("projeto", hoje="2026-10-16")["resumo"]
        self.assertEqual(r["presenca_pct"], 100)
        self.assertEqual(r["dias_cheios"], 2)
        self.assertEqual(r["dias"], 2)

    def test_pagina_mostra_o_panorama_e_aceita_periodo(self):
        for url in ("/dia/2026-10-19", "/dia/2026-10-19?p=sprint", "/dia/2026-10-19?p=semana"):
            html = self.get(url).get_data(as_text=True)
            self.assertIn("Panorama do grupo", html, url)


if __name__ == "__main__":
    unittest.main()
