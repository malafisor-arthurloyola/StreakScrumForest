"""Ordem da rodada de fala guardada no servidor: todas as telas veem quem vem a seguir e outro
aparelho do Scrum continua a mesma rodada."""
import sqlite3
import unittest

from test_holofote_fluxo import DB, FluxoBase, _Celular


class TestOrdemDaRodada(FluxoBase):
    def acender(self, mid, ordem=None, **extra):
        corpo = {"member_id": mid, "modo": "celular", "tipo": "daily"}
        if ordem is not None:
            corpo["ordem"] = ordem
        corpo.update(extra)
        return self.pc.post("/api/holofote", json=corpo)

    def test_ordem_e_posicao_aparecem_para_todos(self):
        ordem = [self.bia, self.ana, self.caio]
        self.assertEqual(self.acender(self.ana, ordem).status_code, 200)
        for cliente in (None, _Celular(self.caio), _Celular()):
            j = self.estado(cliente)
            self.assertEqual([p["id"] for p in j["ordem"]], ordem)
            self.assertEqual(j["pos"], 1)
            self.assertTrue(all(p["nome"] for p in j["ordem"]))

    def test_pedido_sem_ordem_mantem_a_ordem_gravada(self):
        ordem = [self.ana, self.bia, self.caio]
        self.acender(self.ana, ordem)
        self.acender(self.bia)                       # ex.: o painel troca quem preenche
        j = self.estado()
        self.assertEqual([p["id"] for p in j["ordem"]], ordem)
        self.assertEqual(j["pos"], 1)

    def test_encerrar_apaga_a_ordem(self):
        self.acender(self.ana, [self.ana, self.bia])
        self.pc.post("/api/holofote", json={"member_id": None})
        self.acender(self.bia)
        j = self.estado()
        self.assertEqual(j["ordem"], [])
        self.assertIsNone(j["pos"])

    def test_sem_holofote_nao_ha_ordem(self):
        j = self.estado()
        self.assertIsNone(j["member_id"])
        self.assertEqual(j["ordem"], [])
        self.assertIsNone(j["pos"])

    def test_ordem_invalida_e_recusada(self):
        for ordem in ([], [self.bia, self.caio], [self.ana, self.ana], [self.ana, 99999], "1,2", [self.ana, "x"]):
            r = self.acender(self.ana, ordem)
            self.assertEqual(r.status_code, 400, ordem)
        self.assertIsNone(self.estado()["member_id"])

    def test_visitante_nao_grava_ordem(self):
        r = _Celular(self.ana).post("/api/holofote", member_id=self.ana, ordem=[self.ana, self.bia])
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.estado()["ordem"], [])

    def test_pessoa_excluida_some_da_ordem(self):
        self.acender(self.bia, [self.ana, self.bia, self.caio])
        con = sqlite3.connect(DB)
        con.execute("DELETE FROM members WHERE id = ?", (self.ana,))
        con.commit()
        con.close()
        j = self.estado()
        self.assertEqual([p["id"] for p in j["ordem"]], [self.bia, self.caio])
        self.assertEqual(j["pos"], 0)


if __name__ == "__main__":
    unittest.main()
