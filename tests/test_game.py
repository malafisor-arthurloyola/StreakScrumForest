import math
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from game import (
    SEED_MILESTONES,
    calcular_membro,
    calcular_semanas_fechadas,
    calcular_sementes,
    conquistas_membro,
    dia_cheio,
    dias_letivos,
    estagio_para_g,
    limiar_estagio,
    meta_floracao,
    semanas_do_projeto,
    vigor_para_streak,
)

SEMANA1 = "2026-10-12"
NUM_SEMANAS = 10
FERIADOS = {"2026-10-12", "2026-11-02", "2026-11-20"}
CONTAR_DE = "2026-10-15"

D45 = dias_letivos(CONTAR_DE, SEMANA1, NUM_SEMANAS, FERIADOS)
META45 = meta_floracao(len(D45))


def _reg(datas_presente=None, datas_faltou=None, datas_justificada=None, justificada=None):
    r = {}
    for d in (datas_presente or []):
        r.setdefault(d, {})["presente"] = True
    for d in (datas_faltou or []):
        r.setdefault(d, {})["faltou"] = True
    for d in (datas_justificada or justificada or []):
        r.setdefault(d, {})["justificada"] = True
    return r


class TestDiasLetivos(unittest.TestCase):
    def test_d45_tem_45_dias(self):
        self.assertEqual(len(D45), 45)

    def test_nenhum_feriado_na_lista(self):
        for f in FERIADOS:
            self.assertNotIn(f, D45)

    def test_sem_fim_de_semana(self):
        from datetime import date
        for d in D45:
            self.assertLess(date.fromisoformat(d).weekday(), 5)

    def test_comeca_em_contar_a_partir_de(self):
        self.assertGreaterEqual(D45[0], CONTAR_DE)

    def test_outros_d_funcionam(self):
        d = dias_letivos("2026-01-05", "2026-01-05", 4, set())
        self.assertEqual(len(d), 20)


class TestMetaEEstagios(unittest.TestCase):
    def test_meta_d45(self):
        self.assertEqual(META45, 36)

    def test_meta_outros(self):
        self.assertEqual(meta_floracao(50), 40)
        self.assertEqual(meta_floracao(45), 36)
        self.assertEqual(meta_floracao(10), 8)

    def test_limiar_estagio_1(self):
        self.assertEqual(limiar_estagio(1, 36), 1)

    def test_limiar_estagio_10(self):
        self.assertEqual(limiar_estagio(10, 36), 36)

    def test_estagio_0_sem_g(self):
        self.assertEqual(estagio_para_g(0, 36), 0)

    def test_estagio_1_com_g1(self):
        self.assertEqual(estagio_para_g(1, 36), 1)

    def test_estagio_10_com_meta(self):
        self.assertEqual(estagio_para_g(36, 36), 10)

    def test_limiares_crescentes(self):
        meta = 36
        prev = 0
        for k in range(1, 11):
            lim = limiar_estagio(k, meta)
            self.assertGreaterEqual(lim, prev)
            prev = lim


class TestVigor(unittest.TestCase):
    def test_murcha_streak_0(self):
        self.assertEqual(vigor_para_streak(0), "murcha")

    def test_verde_streak_1(self):
        self.assertEqual(vigor_para_streak(1), "verde")

    def test_verde_streak_2(self):
        self.assertEqual(vigor_para_streak(2), "verde")

    def test_vicosa_streak_3(self):
        self.assertEqual(vigor_para_streak(3), "vicosa")

    def test_florida_streak_5(self):
        self.assertEqual(vigor_para_streak(5), "florida")

    def test_radiante_streak_10(self):
        self.assertEqual(vigor_para_streak(10), "radiante")


class TestCalcularMembro(unittest.TestCase):
    def test_sem_registros(self):
        r = calcular_membro(D45, {}, META45)
        self.assertEqual(r["g"], 0)
        self.assertEqual(r["estagio"], 0)
        self.assertFalse(r["floresceu"])
        self.assertEqual(r["vigor"], "murcha")

    def test_um_presente_estagio_1(self):
        reg = _reg([D45[0]])
        r = calcular_membro(D45, reg, META45)
        self.assertEqual(r["estagio"], 1)
        self.assertEqual(r["streak"], 1)

    def test_falta_diminui_g_dois(self):
        reg = _reg([D45[0], D45[1], D45[2]], [D45[3]])
        r = calcular_membro(D45, reg, META45)
        self.assertEqual(r["g"], 1)

    def test_piso_protege_estagio(self):
        reg = _reg([D45[0]], [D45[1], D45[2]])
        r = calcular_membro(D45, reg, META45)
        self.assertGreaterEqual(r["g"], 1)

    def test_g_nao_ultrapassa_meta(self):
        reg = _reg(D45)
        r = calcular_membro(D45, reg, META45)
        self.assertEqual(r["g"], META45)

    def test_presenca_e_falta_mesmo_dia_conta_como_presenca(self):
        d = D45[0]
        reg = {d: {"presente": True, "faltou": True}}
        r = calcular_membro([d], reg, META45)
        self.assertEqual(r["g"], 1)
        self.assertEqual(r["streak"], 1)

    def test_justificada_neutra(self):
        reg = _reg(justificada=[D45[0], D45[1], D45[2]])
        r = calcular_membro(D45, reg, META45)
        self.assertEqual(r["g"], 0)
        self.assertEqual(r["streak"], 0)

    def test_floresceu_permanente(self):
        reg = _reg(D45[:META45])
        r = calcular_membro(D45, reg, META45)
        self.assertTrue(r["floresceu"])
        self.assertEqual(r["estagio"], 10)

    def test_floresceu_nao_perde_com_faltas_depois(self):
        presentes = D45[:META45]
        faltas = D45[META45:]
        reg = _reg(presentes, faltas)
        r = calcular_membro(D45, reg, META45)
        self.assertTrue(r["floresceu"])

    def test_frutos_pos_floracao(self):
        reg = _reg(D45[:META45 + 5])
        r = calcular_membro(D45, reg, META45)
        self.assertGreaterEqual(r["frutos"], 1)

    def test_frutos_maximo_5(self):
        reg = _reg(D45)
        r = calcular_membro(D45, reg, META45)
        self.assertLessEqual(r["frutos"], 5)

    def test_dia_nao_letivo_ignorado(self):
        fora = "2026-10-12"
        reg = {fora: {"presente": True}}
        r = calcular_membro(D45, reg, META45)
        self.assertEqual(r["g"], 0)

    def test_streak_quebrado_por_falta(self):
        reg = _reg([D45[0], D45[1]], [D45[2]])
        r = calcular_membro(D45, reg, META45)
        self.assertEqual(r["streak"], 0)


class TestPerfisDedicadoETipico(unittest.TestCase):
    def test_dedicado_floresce(self):
        reg = _reg(D45)
        r = calcular_membro(D45, reg, META45)
        self.assertTrue(r["floresceu"])
        indice = sum(1 for d in D45 if r["floresceu"] and d <= D45[35])
        self.assertGreaterEqual(r["dias_presentes"], META45)

    def test_tipico_floresce(self):
        presentes = D45[:40]
        justificadas = D45[40:43]
        faltas = D45[43:]
        reg = _reg(presentes, faltas, justificadas)
        r = calcular_membro(D45, reg, META45)
        self.assertTrue(r["floresceu"])

    def test_dedicado_sementes_esperadas(self):
        semanas = semanas_do_projeto(SEMANA1, NUM_SEMANAS, FERIADOS)
        reg = _reg(D45)
        r = calcular_membro(D45, reg, META45)
        s = calcular_sementes(D45, semanas, reg, r["floresceu"])
        self.assertGreaterEqual(s["total"], 100)

    def test_tipico_sementes_esperadas(self):
        semanas = semanas_do_projeto(SEMANA1, NUM_SEMANAS, FERIADOS)
        presentes = D45[:40]
        justificadas = D45[40:43]
        faltas = D45[43:]
        reg = _reg(presentes, faltas, justificadas)
        r = calcular_membro(D45, reg, META45)
        s = calcular_sementes(D45, semanas, reg, r["floresceu"])
        self.assertGreaterEqual(s["total"], 60)

    def test_tres_faltas_seguidas_custo_estagio(self):
        presentes = D45[:18]
        faltas = D45[18:21]
        reg = _reg(presentes, faltas)
        r_antes = calcular_membro(D45[:18], _reg(D45[:18]), META45)
        r_depois = calcular_membro(D45[:21], reg, META45)
        self.assertLessEqual(r_depois["estagio"], r_antes["estagio"])


class TestSemanasFechadas(unittest.TestCase):
    def test_semana_com_4_presencas_fechada(self):
        semanas = semanas_do_projeto(SEMANA1, NUM_SEMANAS, FERIADOS)
        sem1 = semanas[1]
        reg = _reg(sem1[:4])
        resultado = calcular_semanas_fechadas([sem1], reg)
        self.assertEqual(resultado, 1)

    def test_semana_com_3_presencas_nao_fechada(self):
        semanas = semanas_do_projeto(SEMANA1, NUM_SEMANAS, FERIADOS)
        sem1 = semanas[1]
        reg = _reg(sem1[:3])
        resultado = calcular_semanas_fechadas([sem1], reg)
        self.assertEqual(resultado, 0)

    def test_semana_com_feriado_exige_menos(self):
        dias_com_feriado = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06"]
        reg = _reg(dias_com_feriado[:3])
        resultado = calcular_semanas_fechadas([dias_com_feriado], reg)
        self.assertEqual(resultado, 1)


class TestConquistas(unittest.TestCase):
    def test_primeiro_dia(self):
        c = conquistas_membro(1, 1, False, META45)
        self.assertIn("primeiro_dia", c)

    def test_sem_conquistas(self):
        c = conquistas_membro(0, 0, False, META45)
        self.assertEqual(c, [])

    def test_floresceu(self):
        c = conquistas_membro(META45, META45, True, META45)
        self.assertIn("floresceu", c)

    def test_streak_5(self):
        c = conquistas_membro(10, 5, False, META45)
        self.assertIn("streak_5", c)
        self.assertNotIn("streak_10", c)

    def test_metade_meta(self):
        c = conquistas_membro(math.ceil(META45 / 2), 0, False, META45)
        self.assertIn("metade_meta", c)


class TestDiaCheio(unittest.TestCase):
    def test_dia_cheio_todos_presentes(self):
        regs = {
            "2026-10-15": {10: {"presente": True}, 11: {"presente": True}},
        }
        result = dia_cheio([10, 11], regs)
        self.assertIn("2026-10-15", result)

    def test_dia_nao_cheio_um_faltou(self):
        regs = {
            "2026-10-15": {10: {"presente": True}, 11: {"faltou": True}},
        }
        result = dia_cheio([10, 11], regs)
        self.assertNotIn("2026-10-15", result)

    def test_sem_ativos(self):
        result = dia_cheio([], {})
        self.assertEqual(result, set())


if __name__ == "__main__":
    unittest.main()
