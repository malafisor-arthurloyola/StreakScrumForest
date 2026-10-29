"""Rodada de fala para a ata de outro dia (ex.: fazer a ata de ontem com o time): o holofote guarda o dia,
o painel le e grava a ata daquele dia e escrever a fala nao marca presenca de casa."""
import sqlite3
import unittest
from datetime import date, timedelta

from test_holofote_fluxo import DB, HOJE, FluxoBase, _Celular, appmod

ONTEM = (date.fromisoformat(HOJE) - timedelta(days=1)).isoformat()
AMANHA = (date.fromisoformat(HOJE) + timedelta(days=1)).isoformat()


class TestRodadaOutroDia(FluxoBase):
    def acender(self, mid, data=None, tipo="daily", modo="celular"):
        corpo = {"member_id": mid, "modo": modo, "tipo": tipo}
        if data is not None:
            corpo["data"] = data
        return self.pc.post("/api/holofote", json=corpo)

    def test_holofote_guarda_o_dia_da_ata(self):
        self.assertEqual(self.acender(self.ana, ONTEM, "fechamento").status_code, 200)
        j = self.estado(_Celular(self.bia))
        self.assertEqual(j["data"], ONTEM)
        self.assertFalse(j["e_hoje"])
        self.assertEqual(j["tipo"], "fechamento")

    def test_sem_data_e_hoje(self):
        self.acender(self.ana)
        j = self.estado()
        self.assertEqual(j["data"], HOJE)
        self.assertTrue(j["e_hoje"])

    def test_trocar_quem_preenche_continua_no_mesmo_dia(self):
        self.acender(self.ana, ONTEM)
        self.acender(self.ana, modo="scrum")           # o painel manda sem data
        self.assertEqual(self.estado()["data"], ONTEM)

    def test_dia_futuro_ou_invalido_e_recusado(self):
        self.assertEqual(self.acender(self.ana, AMANHA).status_code, 400)
        self.assertEqual(self.acender(self.ana, "ontem").status_code, 400)
        self.assertIsNone(self.estado()["member_id"])

    def test_fala_no_celular_vai_para_a_ata_do_dia_e_nao_marca_presenca(self):
        self.acender(self.ana, ONTEM)
        r = _Celular(self.ana).post("/api/ata/minha-fala", data=ONTEM, tipo="daily", campo="feito", valor="fiz #7")
        self.assertTrue(r.get_json()["ok"])
        self.assertEqual(self.estado()["falas"]["feito"], "fiz #7")
        self.assertIsNone(self.status_no_banco(self.ana))
        con = sqlite3.connect(DB)
        n = con.execute("SELECT COUNT(*) FROM attendance WHERE member_id = ? AND event_date = ?",
                        (self.ana, ONTEM)).fetchone()[0]
        con.close()
        self.assertEqual(n, 0)

    def test_holofote_de_outro_dia_nao_marca_presenca_hoje(self):
        self.acender(self.ana, ONTEM)
        _Celular(self.ana).post("/api/ata/minha-fala", data=HOJE, tipo="daily", campo="feito", valor="hoje")
        self.assertIsNone(self.status_no_banco(self.ana))

    def test_encerrar_apaga_o_dia(self):
        self.acender(self.ana, ONTEM)
        self.pc.post("/api/holofote", json={"member_id": None})
        self.acender(self.bia)
        self.assertEqual(self.estado()["data"], HOJE)

    def test_tela_de_um_dia_passado_tem_a_rodada(self):
        dias = appmod.game.dias_letivos("2026-10-15", "2026-10-12", 10, ["2026-10-12", "2026-11-02", "2026-11-20"])
        passado = [d for d in dias if d < HOJE]
        if not passado:
            self.skipTest("sem dia letivo antes de hoje no calendario padrao")
        h = self.pc.get(f"/dia/{passado[-1]}").get_data(as_text=True)
        self.assertIn('id="rodada"', h)
        self.assertIn("da ata de", h)
        self.assertIn('data-hoje="0"', h)

    def test_tela_de_um_dia_futuro_nao_tem_a_rodada(self):
        h = self.pc.get("/dia/2026-12-18").get_data(as_text=True)
        if HOJE >= "2026-12-18":
            self.skipTest("o projeto ja acabou")
        self.assertNotIn('id="rodada"', h)


if __name__ == "__main__":
    unittest.main()
