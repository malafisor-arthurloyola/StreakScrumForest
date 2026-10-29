"""A fala escrita pelo QR nao se perde quando o QR muda (ele vale de 10 a 20 minutos). Era o que acontecia
na Day Closing: a pessoa lia o QR, escrevia com calma e, ao salvar, o site recusava o envio."""
import sqlite3
import time
import unittest

from test_fase5 import DB, HOJE, Fase5Base, appmod

VELHO = time.time() - 3 * appmod.JANELA_QR_SEG     # um codigo de meia hora atras: ja nao vale


class TestQrExpirado(Fase5Base):
    def setUp(self):
        super().setUp()
        self.mid = self.ids()[0]
        self.entrar_como(self.mid)

    def status(self, evento="encerramento"):
        con = sqlite3.connect(DB)
        r = con.execute("SELECT status FROM attendance WHERE member_id=? AND event_date=? AND event_type=?",
                        (self.mid, HOJE, evento)).fetchone()
        con.close()
        return r[0] if r else None

    def test_quem_ja_marcou_salva_a_fala_com_o_qr_velho(self):
        novo = appmod.codigo_do_evento(HOJE, "encerramento")
        self.assertTrue(self.post(f"/presenca/encerramento/{novo}", {}).get_json()["ok"])
        velho = appmod.codigo_do_evento(HOJE, "encerramento", agora=VELHO)
        r = self.post(f"/presenca/encerramento/{velho}", {"fala": {"feito": "fechei #12", "planejado": "testes"}})
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertTrue(j["ok"])
        self.assertTrue(j["presente"])
        self.assertFalse(j["ganhou_presenca"])
        self.assertEqual(tuple(self.fala(self.mid, "fechamento")), ("fechei #12", "testes"))

    def test_fala_com_qr_velho_salva_mas_nao_marca_presenca(self):
        velho = appmod.codigo_do_evento(HOJE, "encerramento", agora=VELHO)
        j = self.post(f"/presenca/encerramento/{velho}", {"fala": {"feito": "de casa", "planejado": ""}}).get_json()
        self.assertTrue(j["ok"])
        self.assertTrue(j["qr_expirado"])
        self.assertFalse(j["presente"])
        self.assertIsNone(self.status())
        self.assertEqual(self.fala(self.mid, "fechamento")[0], "de casa")

    def test_so_presenca_com_qr_velho_responde_json_com_o_motivo(self):
        velho = appmod.codigo_do_evento(HOJE, "encerramento", agora=VELHO)
        r = self.post(f"/presenca/encerramento/{velho}", {})
        self.assertEqual(r.status_code, 403)
        self.assertIn("QR", r.get_json()["erro"])
        self.assertIsNone(self.status())

    def test_dev_sem_ata_com_qr_velho_nao_marca(self):
        velho = appmod.codigo_do_evento(HOJE, "dev", agora=VELHO)
        r = self.post(f"/presenca/dev/{velho}", {"fala": {"feito": "x", "planejado": ""}})
        self.assertEqual(r.status_code, 403)
        self.assertIsNone(self.status("dev"))

    def test_abrir_o_qr_velho_continua_mostrando_expirado(self):
        velho = appmod.codigo_do_evento(HOJE, "encerramento", agora=VELHO)
        h = self.get(f"/presenca/encerramento/{velho}").get_data(as_text=True)
        self.assertIn("Código expirado", h)


if __name__ == "__main__":
    unittest.main()
