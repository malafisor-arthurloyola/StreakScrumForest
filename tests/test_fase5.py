import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import date

_TMP = tempfile.mkdtemp()
os.environ.setdefault("STRIKES_DB", os.path.join(_TMP, "fase5.db"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as appmod  # noqa: E402
import game  # noqa: E402

DB = str(appmod.DB_PATH)
HOJE = date.today().isoformat()
DATA = "2026-10-19"  # dia letivo (segunda)
# visitante: outro aparelho (celular) falando com o servidor pela rede (nao e admin)
REMOTO = {"environ_overrides": {"REMOTE_ADDR": "192.168.0.23"}, "base_url": "http://192.168.0.10:5000"}


class Fase5Base(unittest.TestCase):
    def setUp(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(DB + ext):
                os.remove(DB + ext)
        appmod.init_db()
        os.environ.pop("ADMIN_CODE", None)
        os.environ.pop("ADMIN_LOCAL", None)
        try:
            appmod.TENTATIVAS.clear()
            appmod.PIN_TENTATIVAS.clear()
        except Exception:
            pass
        self.client = appmod.app.test_client()

    def ids(self):
        con = sqlite3.connect(DB)
        v = [r[0] for r in con.execute("SELECT id FROM members WHERE active = 1 ORDER BY id")]
        con.close()
        return v

    # visitante (celular, rede): usa host remoto para NAO virar admin de localhost
    def get(self, url, **kw):
        return self.client.get(url, **{**REMOTO, **kw})

    def post(self, url, json=None, **kw):
        return self.client.post(url, json=json or {}, **{**REMOTO, **kw})

    def entrar_como(self, mid):
        with self.client.session_transaction(base_url=REMOTO["base_url"]) as sess:
            sess["eu"] = mid

    def fala(self, mid, tipo="daily", data=None):
        con = sqlite3.connect(DB)
        r = con.execute("SELECT feito, planejado FROM ata_falas WHERE data=? AND tipo=? AND member_id=?",
                        (data or HOJE, tipo, mid)).fetchone()
        con.close()
        return r


# ---------------------------------------------------------------- 5.1 presença + fala
class TestPresencaDepoisFala(Fase5Base):
    def test_marcar_so_presenca_e_preencher_fala_depois(self):
        a = self.ids()[0]
        self.entrar_como(a)
        cod = appmod.codigo_do_evento(HOJE, "daily")
        # 1o POST: so presenca
        r = self.post(f"/presenca/daily/{cod}", {})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ganhou_presenca"])
        self.assertIsNone(self.fala(a))  # ainda sem fala
        # 2o POST: a fala, depois (grava sem problema)
        r = self.post(f"/presenca/daily/{cod}", {"fala": {"feito": "fiz #10", "planejado": "revisar"}})
        self.assertTrue(r.get_json()["ganhou_ata"])
        self.assertEqual(self.fala(a), ("fiz #10", "revisar"))

    def test_pagina_ja_presente_mantem_o_formulario(self):
        a = self.ids()[0]
        self.entrar_como(a)
        cod = appmod.codigo_do_evento(HOJE, "daily")
        self.post(f"/presenca/daily/{cod}", {})  # marca presenca
        h = self.get(f"/presenca/daily/{cod}").get_data(as_text=True)
        self.assertIn("já está registrada", h)     # mostra o estado
        self.assertIn('id="presenca-form"', h)      # e MANTEM o formulario da fala
        self.assertIn('id="pf-feito"', h)

    def test_salvar_fala_garante_presenca(self):
        a = self.ids()[0]
        self.entrar_como(a)
        cod = appmod.codigo_do_evento(HOJE, "daily")
        # sem marcar presenca antes: salvar a fala ja deve marcar presente
        self.post(f"/presenca/daily/{cod}", {"fala": {"feito": "comecei direto", "planejado": ""}})
        con = sqlite3.connect(DB)
        st = con.execute("SELECT status FROM attendance WHERE member_id=? AND event_date=? AND event_type='daily'",
                         (a, HOJE)).fetchone()
        con.close()
        self.assertEqual(st[0], "presente")


# ---------------------------------------------------------------- 5.2 própria linha na ata
class TestAtaPropriaLinha(Fase5Base):
    def test_logado_edita_a_propria_linha(self):
        a = self.ids()[0]
        self.entrar_como(a)   # logado, mas NAO relator nem admin
        r = self.post("/api/ata/minha-fala", {"data": DATA, "tipo": "daily", "campo": "feito", "valor": "minha parte"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.fala(a, data=DATA)[0], "minha parte")

    def test_nao_edita_a_linha_de_outro(self):
        a, b = self.ids()[0], self.ids()[1]
        self.entrar_como(a)
        # tentar usar o endpoint do relator para editar OUTRA pessoa -> 403
        r = self.post("/api/ata/salvar",
                      {"data": DATA, "tipo": "daily", "campo": "feito", "member_id": b, "valor": "invasao"},
                      headers={"X-Requested-With": "fetch"})
        self.assertEqual(r.status_code, 403)
        self.assertIsNone(self.fala(b, data=DATA))

    def test_pagina_so_habilita_a_propria_linha(self):
        a, b = self.ids()[0], self.ids()[1]
        self.entrar_como(a)
        h = self.get(f"/ata/{DATA}/daily").get_data(as_text=True)
        # a linha de 'a' vem habilitada (sem disabled no textarea feito dela)
        import re
        # textarea feito da propria pessoa (a) NAO deve ter disabled
        m_a = re.search(r'data-campo="feito" data-member-id="%d"[^>]*>' % a, h)
        self.assertTrue(m_a and "disabled" not in m_a.group(0))
        # textarea feito de outro (b) DEVE ter disabled
        m_b = re.search(r'data-campo="feito" data-member-id="%d"[^>]*>' % b, h)
        self.assertTrue(m_b and "disabled" in m_b.group(0))
        self.assertIn("ata-linha-minha", h)

    def test_visitante_sem_login_ve_aviso_de_pin(self):
        h = self.get(f"/ata/{DATA}/daily").get_data(as_text=True)
        self.assertIn("Entrar com o meu PIN", h)


# ---------------------------------------------------------------- 5.3 quanto rende
class TestQuantoRende(Fase5Base):
    def test_pagina_mostra_valores_das_constantes(self):
        a = self.ids()[0]
        self.entrar_como(a)
        cod = appmod.codigo_do_evento(HOJE, "daily")
        h = self.get(f"/presenca/daily/{cod}").get_data(as_text=True)
        # os valores vem das constantes de game.py (nunca fixos)
        self.assertIn("Marcar presença <b>+%d" % game.SEED_POR_EVENTO["daily"], h)
        self.assertIn("Preencher a Daily <b>+%d" % game.SEED_ATA, h)
        self.assertIn("juntos <b>+%d" % (game.SEED_POR_EVENTO["daily"] + game.SEED_ATA), h)

    def test_mudar_constante_muda_a_pagina(self):
        a = self.ids()[0]
        self.entrar_como(a)
        cod = appmod.codigo_do_evento(HOJE, "daily")
        orig = game.SEED_ATA
        try:
            game.SEED_ATA = 9
            h = self.get(f"/presenca/daily/{cod}").get_data(as_text=True)
            self.assertIn("Preencher a Daily <b>+9", h)
        finally:
            game.SEED_ATA = orig

    def test_editar_a_fala_nao_rende_de_novo(self):
        a = self.ids()[0]
        self.entrar_como(a)
        cod = appmod.codigo_do_evento(HOJE, "daily")
        r1 = self.post(f"/presenca/daily/{cod}", {"fala": {"feito": "v1", "planejado": ""}})
        self.assertTrue(r1.get_json()["ganhou_ata"])     # 1a vez: ganha
        r2 = self.post(f"/presenca/daily/{cod}", {"fala": {"feito": "v1 editado", "planejado": ""}})
        self.assertFalse(r2.get_json()["ganhou_ata"])    # editar: nao ganha de novo

    def test_por_ata_continua_um_por_ata(self):
        # a regra de game nao muda: 1 ata com fala = 1 semente, mesmo editando varias vezes
        dias = game.dias_letivos("2026-10-15", "2026-10-12", 10, {"2026-10-12"})
        sem = game.semanas_do_projeto("2026-10-12", 10, {"2026-10-12"})
        r = game.calcular_sementes(dias, sem, {dias[0]: {"presente": True}}, False, atas_com_fala=1)
        self.assertEqual(r["por_ata"], game.SEED_ATA)


if __name__ == "__main__":
    unittest.main()
