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
    avaliar_meta,
    estado_ate,
    marcos_coletivos,
    meta_floracao,
    nivel_chama,
    nivel_presenca,
    periodo_do_dia,
    posicao_astro,
    progresso_estagio,
    semanas_do_projeto,
    semanas_status,
    sequencia_dias_cheios,
    sprint_da_data,
    sprints_do_projeto,
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

    def test_limiares_uniformes_meta_36(self):
        lims = [limiar_estagio(k, 36) for k in range(1, 11)]
        self.assertEqual(lims, [1, 5, 9, 13, 17, 21, 25, 29, 33, 36])

    def test_nenhum_estagio_dura_mais_que_5_dias(self):
        for meta in (36, 40, 44):
            prev = limiar_estagio(1, meta)
            for k in range(2, 11):
                lim = limiar_estagio(k, meta)
                self.assertLessEqual(lim - prev, 5, (meta, k))
                prev = lim

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


class TestProgressoEstagio(unittest.TestCase):
    META = 36

    def test_inicio_do_estagio(self):
        # estagio 2 comeca com 5 presencas; o 3 comeca com 9
        p, falta = progresso_estagio(5, self.META, 2)
        self.assertEqual(p, 0.0)
        self.assertEqual(falta, 4)

    def test_um_dia_dentro_do_estagio(self):
        p, falta = progresso_estagio(6, self.META, 2)
        self.assertAlmostEqual(p, 0.25, places=2)
        self.assertEqual(falta, 3)

    def test_ultimo_dia_antes_de_subir(self):
        p, falta = progresso_estagio(8, self.META, 2)
        self.assertAlmostEqual(p, 0.75, places=2)
        self.assertEqual(falta, 1)

    def test_semente(self):
        self.assertEqual(progresso_estagio(0, self.META, 0), (0.0, 1))

    def test_floresceu_fica_cheio(self):
        self.assertEqual(progresso_estagio(36, self.META, 10), (1.0, 0))

    def test_sempre_entre_zero_e_um(self):
        for g in range(0, self.META + 1):
            est = estagio_para_g(g, self.META)
            p, falta = progresso_estagio(g, self.META, est)
            self.assertTrue(0.0 <= p <= 1.0, (g, p))
            self.assertGreaterEqual(falta, 0)

    def test_cada_presenca_aumenta_o_progresso_ou_sobe_de_estagio(self):
        for g in range(0, self.META):
            e1 = estagio_para_g(g, self.META)
            e2 = estagio_para_g(g + 1, self.META)
            p1, _ = progresso_estagio(g, self.META, e1)
            p2, _ = progresso_estagio(g + 1, self.META, e2)
            self.assertTrue(e2 > e1 or p2 > p1, (g, e1, e2, p1, p2))


class TestNivelChama(unittest.TestCase):
    def test_faixas(self):
        casos = {0: 0, 1: 1, 2: 1, 3: 2, 6: 2, 7: 3, 13: 3, 14: 4, 40: 4}
        for streak, esperado in casos.items():
            self.assertEqual(nivel_chama(streak), esperado, streak)


class TestCenaDoDia(unittest.TestCase):
    def test_periodos(self):
        casos = {
            0: "madrugada", 4.9: "madrugada", 5: "amanhecer", 7.4: "amanhecer",
            7.5: "manha", 11.9: "manha", 12: "meiodia", 13.9: "meiodia",
            14: "tarde", 17.4: "tarde", 17.5: "entardecer", 18.9: "entardecer",
            19: "noite", 23.9: "noite",
        }
        for hora, esperado in casos.items():
            self.assertEqual(periodo_do_dia(hora), esperado, hora)

    def test_sol_no_alto_ao_meio_dia(self):
        x, y = posicao_astro(12, 5.5, 13)
        self.assertAlmostEqual(x, 50, delta=1)
        self.assertAlmostEqual(y, 10, delta=1)

    def test_astro_fora_da_janela_fica_no_horizonte(self):
        x, y = posicao_astro(23, 5.5, 13)
        self.assertEqual((x, y), (92.0, 66.0))

    def test_lua_no_alto_a_meia_noite(self):
        x, y = posicao_astro(0, 18.5, 11)
        self.assertAlmostEqual(x, 50, delta=1)
        self.assertAlmostEqual(y, 10, delta=1)


class TestSementesDiaCheio(unittest.TestCase):
    def setUp(self):
        self.dias = dias_letivos("2026-10-15", SEMANA1, NUM_SEMANAS, FERIADOS)
        self.semanas = semanas_do_projeto(SEMANA1, NUM_SEMANAS, FERIADOS)

    def test_bonus_de_dia_cheio_so_conta_se_o_membro_veio(self):
        d = self.dias
        regs = {d[0]: {"presente": True}, d[1]: {"presente": True}}
        base = calcular_sementes(d, self.semanas, regs, False)["total"]
        com = calcular_sementes(d, self.semanas, regs, False, dias_cheios={d[0], d[5]})
        self.assertEqual(com["total"], base + 1)
        self.assertEqual(com["por_dia_cheio"], 1)

    def test_sem_dias_cheios_nada_muda(self):
        d = self.dias
        regs = {d[0]: {"presente": True}}
        a = calcular_sementes(d, self.semanas, regs, False)
        b = calcular_sementes(d, self.semanas, regs, False, dias_cheios=set())
        self.assertEqual(a["total"], b["total"])

    def test_total_dedicado_em_time_perfeito(self):
        regs = {dia: {"presente": True} for dia in self.dias}
        r = calcular_sementes(self.dias, self.semanas, regs, True, dias_cheios=set(self.dias))
        self.assertGreaterEqual(r["total"], 150)
        # inclui as boas-vindas (+20) a partir da Fase 1.5
        self.assertLessEqual(r["total"], 210)

    def test_total_tipico(self):
        # ~88%: uma ausencia a cada 8 dias (2 faltas e 3 avisos), faltas espalhadas
        d = self.dias
        regs = {}
        for i, dia in enumerate(d):
            if i % 8 == 7:
                regs[dia] = {"faltou": True} if i < 20 else {"justificada": True}
            else:
                regs[dia] = {"presente": True}
        meta = meta_floracao(len(d))
        floresceu = calcular_membro(d, regs, meta)["floresceu"]
        cheios = {dia for i, dia in enumerate(d) if "presente" in regs[dia] and i % 5 < 3}
        r = calcular_sementes(d, self.semanas, regs, floresceu, dias_cheios=cheios)
        self.assertGreaterEqual(r["total"], 100)
        self.assertLessEqual(r["total"], 150)


class TestSprints(unittest.TestCase):
    def test_cinco_sprints_de_duas_semanas(self):
        sp = sprints_do_projeto("2026-10-12", 10, 2)
        self.assertEqual(len(sp), 5)
        self.assertEqual(sp[0], {"n": 1, "inicio": "2026-10-12", "fim": "2026-10-23"})
        self.assertEqual(sp[4]["fim"], "2026-12-18")

    def test_ultima_sprint_pode_ser_mais_curta(self):
        sp = sprints_do_projeto("2026-10-12", 5, 2)
        self.assertEqual(len(sp), 3)
        self.assertEqual(sp[2]["fim"], "2026-11-13")

    def test_sprint_da_data(self):
        sp = sprints_do_projeto("2026-10-12", 10, 2)
        self.assertEqual(sprint_da_data("2026-10-19", sp), 1)
        self.assertEqual(sprint_da_data("2026-10-26", sp), 2)
        self.assertEqual(sprint_da_data("2026-12-18", sp), 5)

    def test_antes_e_depois_do_projeto_ficam_nas_pontas(self):
        sp = sprints_do_projeto("2026-10-12", 10, 2)
        self.assertEqual(sprint_da_data("2026-09-01", sp), 1)
        self.assertEqual(sprint_da_data("2027-03-01", sp), 5)


class TestMetasDaSprint(unittest.TestCase):
    DIAS = ["2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20"]

    def glob(self, quem_veio):
        """quem_veio: {data: [ids presentes]}"""
        return {d: {mid: {"presente": True} for mid in ids} for d, ids in quem_veio.items()}

    def test_presenca_percentual(self):
        g = self.glob({"2026-10-15": [1, 2], "2026-10-16": [1]})
        r = avaliar_meta("presenca_pct", 75, self.DIAS, "2026-10-16", [1, 2], g, set())
        self.assertEqual(r["valor"], 75)  # 3 presencas de 4 possiveis
        self.assertTrue(r["cumprida"])

    def test_so_conta_dias_que_ja_passaram(self):
        g = self.glob({"2026-10-15": [1, 2]})
        r = avaliar_meta("presenca_pct", 90, self.DIAS, "2026-10-15", [1, 2], g, set())
        self.assertEqual(r["valor"], 100)

    def test_sem_dias_decorridos(self):
        r = avaliar_meta("presenca_pct", 90, self.DIAS, "2026-10-01", [1], {}, set())
        self.assertEqual(r["valor"], 0)
        self.assertFalse(r["cumprida"])

    def test_dias_cheios(self):
        cheios = {"2026-10-15", "2026-10-19", "2026-11-30"}
        r = avaliar_meta("dias_cheios", 2, self.DIAS, "2026-10-20", [1], {}, cheios)
        self.assertEqual(r["valor"], 2)
        self.assertTrue(r["cumprida"])
        self.assertEqual(r["pct"], 100)

    def test_sequencia_do_time(self):
        cheios = {"2026-10-15", "2026-10-16", "2026-10-20"}
        r = avaliar_meta("sequencia_time", 3, self.DIAS, "2026-10-20", [1], {}, cheios)
        self.assertEqual(r["valor"], 2)
        self.assertFalse(r["cumprida"])
        self.assertEqual(r["pct"], 67)

    def test_pct_nunca_passa_de_100(self):
        cheios = set(self.DIAS)
        r = avaliar_meta("dias_cheios", 2, self.DIAS, "2026-10-20", [1], {}, cheios)
        self.assertEqual(r["valor"], 4)
        self.assertEqual(r["pct"], 100)

    def test_tipo_desconhecido(self):
        r = avaliar_meta("xyz", 5, self.DIAS, "2026-10-20", [1], {}, set())
        self.assertEqual(r["valor"], 0)
        self.assertFalse(r["cumprida"])


class TestMarcosColetivos(unittest.TestCase):
    def test_nenhum_no_comeco(self):
        self.assertEqual([m["liberado"] for m in marcos_coletivos(0)], [False] * 4)

    def test_liberam_nos_percentuais(self):
        self.assertEqual([m["liberado"] for m in marcos_coletivos(25)], [True, False, False, False])
        self.assertEqual([m["liberado"] for m in marcos_coletivos(74)], [True, True, False, False])
        self.assertEqual([m["liberado"] for m in marcos_coletivos(100)], [True] * 4)

    def test_ids_estaveis(self):
        self.assertEqual([m["id"] for m in marcos_coletivos(0)],
                         ["fonte", "vagalumes", "petalas", "arvore_time"])


class TestSemanasStatus(unittest.TestCase):
    def setUp(self):
        self.semanas = semanas_do_projeto(SEMANA1, NUM_SEMANAS, FERIADOS)
        self.dias = dias_letivos("2026-10-15", SEMANA1, NUM_SEMANAS, FERIADOS)

    def estados(self, regs, hoje):
        return [x["estado"] for x in semanas_status(self.semanas, regs, hoje, "2026-10-15")]

    def test_semana_de_largada_nao_pune(self):
        e = self.estados({}, "2026-10-17")
        self.assertEqual(e[0], "largada")
        self.assertEqual(e[1], "futura")

    def test_semana_em_andamento(self):
        e = self.estados({}, "2026-10-21")
        self.assertEqual(e[1], "em_andamento")

    def test_semana_fechada_com_4_presencas(self):
        regs = {d: {"presente": True} for d in ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22"]}
        e = self.estados(regs, "2026-10-22")
        self.assertEqual(e[1], "fechada")

    def test_semana_passada_sem_fechar_e_apenas_aberta(self):
        regs = {"2026-10-19": {"presente": True}}
        e = self.estados(regs, "2026-10-30")
        self.assertEqual(e[1], "aberta")

    def test_semana_com_feriado_fecha_com_menos(self):
        # semana de 02/11 tem 4 dias letivos: minimo 3
        regs = {d: {"presente": True} for d in ["2026-11-03", "2026-11-04", "2026-11-05"]}
        e = self.estados(regs, "2026-11-06")
        self.assertEqual(e[3], "fechada")

    def test_dez_semanas(self):
        self.assertEqual(len(self.estados({}, "2026-10-17")), 10)


class TestEstadoAte(unittest.TestCase):
    def test_estado_em_data_passada(self):
        dias = dias_letivos("2026-10-15", SEMANA1, NUM_SEMANAS, FERIADOS)
        regs = {d: {"presente": True} for d in dias[:10]}
        meta = meta_floracao(len(dias))
        hoje = calcular_membro(dias, regs, meta)
        meio = estado_ate(dias, regs, meta, dias[4])
        self.assertEqual(meio["dias_presentes"], 5)
        self.assertLess(meio["estagio"], hoje["estagio"])

    def test_floresceu_em_vem_no_estado(self):
        dias = dias_letivos("2026-10-15", SEMANA1, NUM_SEMANAS, FERIADOS)
        regs = {d: {"presente": True} for d in dias}
        meta = meta_floracao(len(dias))
        est = calcular_membro(dias, regs, meta)
        self.assertEqual(est["floresceu_em"], dias[meta - 1])
        self.assertIsNone(calcular_membro(dias, {}, meta)["floresceu_em"])


class TestSequenciaDiasCheios(unittest.TestCase):
    DIAS = ["2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21"]

    def test_sequencia_ate_hoje(self):
        cheios = {"2026-10-15", "2026-10-16", "2026-10-19"}
        self.assertEqual(sequencia_dias_cheios(self.DIAS, cheios, set(cheios), "2026-10-19"), 3)

    def test_dia_recente_que_falhou_zera(self):
        cheios = {"2026-10-15", "2026-10-16"}
        com_registro = cheios | {"2026-10-19"}
        self.assertEqual(sequencia_dias_cheios(self.DIAS, cheios, com_registro, "2026-10-19"), 0)

    def test_hoje_ainda_sem_registro_nao_quebra(self):
        cheios = {"2026-10-15", "2026-10-16"}
        self.assertEqual(sequencia_dias_cheios(self.DIAS, cheios, set(cheios), "2026-10-19"), 2)

    def test_dia_que_falhou_no_meio_quebra(self):
        cheios = {"2026-10-15", "2026-10-16", "2026-10-20"}
        com_registro = cheios | {"2026-10-19"}
        self.assertEqual(sequencia_dias_cheios(self.DIAS, cheios, com_registro, "2026-10-20"), 1)

    def test_dias_futuros_sao_ignorados(self):
        cheios = {"2026-10-15", "2026-10-21"}
        self.assertEqual(sequencia_dias_cheios(self.DIAS, cheios, set(cheios), "2026-10-15"), 1)


class TestNivelPresenca(unittest.TestCase):
    def test_niveis(self):
        casos = [((0, 7), 0), ((1, 7), 1), ((3, 7), 1), ((4, 7), 2), ((5, 7), 3),
                 ((6, 7), 3), ((7, 7), 4)]
        for (presentes, total), esperado in casos:
            self.assertEqual(nivel_presenca(presentes, total), esperado, (presentes, total))

    def test_sem_ativos(self):
        self.assertEqual(nivel_presenca(0, 0), 0)


if __name__ == "__main__":
    unittest.main()


class TestSementesPorEvento(unittest.TestCase):
    def setUp(self):
        self.dias = dias_letivos("2026-10-15", SEMANA1, NUM_SEMANAS, FERIADOS)
        self.semanas = semanas_do_projeto(SEMANA1, NUM_SEMANAS, FERIADOS)

    def _tudo(self, eventos):
        return {d: {"presente": True, "eventos": set(eventos)} for d in self.dias}

    def test_cada_evento_vale_uma_semente(self):
        d = self.dias[:1]
        for ev, esperado in (({"daily"}, 1), ({"daily", "dev"}, 2), ({"daily", "dev", "encerramento"}, 3)):
            r = calcular_sementes(d, self.semanas, {d[0]: {"presente": True, "eventos": ev}}, False)
            self.assertEqual(r["por_presenca"], esperado)

    def test_registro_sem_detalhe_vale_um(self):
        d = self.dias[:1]
        r = calcular_sementes(d, self.semanas, {d[0]: {"presente": True}}, False)
        self.assertEqual(r["por_presenca"], 1)

    def test_dedicado_com_tres_eventos(self):
        regs = self._tudo(("daily", "dev", "encerramento"))
        r = calcular_sementes(self.dias, self.semanas, regs, True, dias_cheios=set(self.dias))
        self.assertEqual(r["por_presenca"], 135)
        # 265 das 5 fontes antigas + 20 de boas-vindas (Fase 1.5) = 285
        self.assertEqual(r["total"], 285)
        self.assertEqual(r["por_boas_vindas"], 20)

    def test_so_daily_com_boas_vindas(self):
        regs = self._tudo(("daily",))
        r = calcular_sementes(self.dias, self.semanas, regs, True, dias_cheios=set(self.dias))
        # 175 das fontes antigas + 20 de boas-vindas (Fase 1.5) = 195
        self.assertEqual(r["total"], 195)

    def test_crescimento_nao_depende_de_eventos(self):
        meta = meta_floracao(len(self.dias))
        a = calcular_membro(self.dias, self._tudo(("daily",)), meta)
        b = calcular_membro(self.dias, self._tudo(("daily", "dev", "encerramento")), meta)
        self.assertEqual(a["g"], b["g"])

