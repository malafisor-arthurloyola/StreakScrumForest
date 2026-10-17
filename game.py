import math
from datetime import date, timedelta


STAGE_NAMES = [
    "Semente",
    "Brotinho",
    "Muda",
    "Folhinhas",
    "Jovem",
    "Crescendo",
    "Vicosa",
    "Botoes",
    "Florindo",
    "Frutificando",
    "Floresceu",
]

VIGOR_LEVELS = [
    (0,  "murcha"),
    (1,  "verde"),
    (3,  "vicosa"),
    (5,  "florida"),
    (10, "radiante"),
]

SEED_MILESTONES = [
    (5,  3),
    (10, 5),
    (20, 10),
    (40, 20),
]


def dias_letivos(contar_a_partir_de, semana1_inicio, num_semanas, feriados):
    """Retorna lista ordenada de datas letivas (seg-sex, nao feriado, dentro do periodo)."""
    inicio = date.fromisoformat(contar_a_partir_de)
    s1 = date.fromisoformat(semana1_inicio)
    fim = s1 + timedelta(weeks=num_semanas) - timedelta(days=1)
    feriados_set = set(feriados)
    dias = []
    d = inicio
    while d <= fim:
        if d.weekday() < 5 and d.isoformat() not in feriados_set:
            dias.append(d.isoformat())
        d += timedelta(days=1)
    return dias


def semanas_do_projeto(semana1_inicio, num_semanas, feriados_set):
    """Retorna lista de semanas, cada uma com lista de datas letivas."""
    s1 = date.fromisoformat(semana1_inicio)
    semanas = []
    for i in range(num_semanas):
        inicio_sem = s1 + timedelta(weeks=i)
        dias_sem = []
        for j in range(5):
            d = inicio_sem + timedelta(days=j)
            if d.isoformat() not in feriados_set:
                dias_sem.append(d.isoformat())
        semanas.append(dias_sem)
    return semanas


def meta_floracao(d_total):
    return math.ceil(0.80 * d_total)


def limiar_estagio(k, meta):
    if k == 0:
        return 0
    if k == 1:
        return 1
    return math.ceil(k * meta / 10)


def estagio_para_g(g, meta):
    """Retorna o estagio (0-10) para um valor de G."""
    estagio = 0
    for k in range(10, 0, -1):
        if g >= limiar_estagio(k, meta):
            estagio = k
            break
    return estagio


def vigor_para_streak(streak):
    nivel = "murcha"
    for minimo, nome in VIGOR_LEVELS:
        if streak >= minimo:
            nivel = nome
    return nivel


def calcular_membro(dias_letivos_lista, registros_por_data, meta):
    """
    Calcula o estado de jogo de um membro.

    registros_por_data: dict { 'YYYY-MM-DD': {'presente': bool, 'faltou': bool, 'justificada': bool} }
    Retorna dict com G, estagio, floresceu, vigor, streak, melhor_streak, dias_presentes,
    piso, frutos, sementes_base.
    """
    g = 0
    piso = 0
    estagio_max = 0
    streak = 0
    melhor_streak = 0
    dias_presentes = 0
    sementes_base = 0
    floresceu_em = None

    for data in dias_letivos_lista:
        reg = registros_por_data.get(data, {})
        tem_presente = reg.get("presente", False)
        tem_faltou = reg.get("faltou", False)

        if tem_presente:
            g = min(g + 1, meta)
            streak += 1
            melhor_streak = max(melhor_streak, streak)
            dias_presentes += 1
            sementes_base += 1
        elif tem_faltou:
            g = max(g - 2, piso)
            streak = 0
        else:
            pass

        est = estagio_para_g(g, meta)
        if est > estagio_max:
            estagio_max = est
            piso = limiar_estagio(estagio_max, meta)

        if g >= meta and floresceu_em is None:
            floresceu_em = data

    floresceu = floresceu_em is not None
    if floresceu:
        g = max(g, meta)

    frutos = 0
    if floresceu and dias_presentes > meta:
        excedente = dias_presentes - meta
        frutos = min(excedente // 5, 5)

    estagio_final = estagio_para_g(g, meta)
    if floresceu:
        estagio_final = 10

    vigor = vigor_para_streak(streak)

    return {
        "g": g,
        "estagio": estagio_final,
        "floresceu": floresceu,
        "vigor": vigor,
        "streak": streak,
        "melhor_streak": melhor_streak,
        "dias_presentes": dias_presentes,
        "frutos": frutos,
        "sementes_base": sementes_base,
    }


def calcular_semanas_fechadas(semanas_projeto, registros_por_data):
    """
    Retorna numero de semanas fechadas (>= 4 presenças, ou >= dias_letivos_semana - 1).
    semanas_projeto: lista de listas de datas letivas por semana.
    registros_por_data: dict { 'YYYY-MM-DD': {'presente': bool, ...} }
    """
    fechadas = 0
    for dias_sem in semanas_projeto:
        if not dias_sem:
            continue
        n_letivos = len(dias_sem)
        semana_tem_feriado = n_letivos < 5
        if semana_tem_feriado:
            minimo = n_letivos - 1
        else:
            minimo = 4
        presencas = sum(
            1 for d in dias_sem if registros_por_data.get(d, {}).get("presente", False)
        )
        if presencas >= minimo:
            fechadas += 1
    return fechadas


def calcular_sementes(dias_letivos_lista, semanas_projeto, registros_por_data, floresceu):
    """
    Calcula sementes ganhas (nunca perde por falta).
    Retorna dict com total e detalhes.
    """
    dias_presentes = sum(
        1 for d in dias_letivos_lista if registros_por_data.get(d, {}).get("presente", False)
    )
    semenas_fechadas = calcular_semanas_fechadas(semanas_projeto, registros_por_data)

    streak_max = 0
    streak = 0
    for d in dias_letivos_lista:
        if registros_por_data.get(d, {}).get("presente", False):
            streak += 1
            streak_max = max(streak_max, streak)
        elif registros_por_data.get(d, {}).get("faltou", False):
            streak = 0

    marcos = 0
    for limiar, bonus in SEED_MILESTONES:
        if streak_max >= limiar:
            marcos += bonus

    bonus_floresceu = 20 if floresceu else 0

    total = dias_presentes + semenas_fechadas * 3 + marcos + bonus_floresceu
    return {
        "total": total,
        "por_presenca": dias_presentes,
        "por_semanas_fechadas": semenas_fechadas * 3,
        "por_marcos": marcos,
        "por_floresceu": bonus_floresceu,
        "semanas_fechadas": semenas_fechadas,
    }


def conquistas_membro(dias_presentes, melhor_streak, floresceu, meta):
    """Retorna lista de conquistas alcancadas."""
    lista = []
    if dias_presentes >= 1:
        lista.append("primeiro_dia")
    if melhor_streak >= 5:
        lista.append("streak_5")
    if melhor_streak >= 10:
        lista.append("streak_10")
    if melhor_streak >= 20:
        lista.append("streak_20")
    if melhor_streak >= 40:
        lista.append("streak_40")
    if dias_presentes >= math.ceil(meta / 2):
        lista.append("metade_meta")
    if floresceu:
        lista.append("floresceu")
    return lista


def dia_cheio(membros_ativos_ids, registros_globais_por_data):
    """
    Retorna set de datas em que todos os ativos tiveram pelo menos 1 presente
    e nenhum faltou.
    registros_globais_por_data: { data: { member_id: {'presente': bool, 'faltou': bool} } }
    """
    dias = set()
    if not membros_ativos_ids:
        return dias
    for data, por_membro in registros_globais_por_data.items():
        cheio = True
        for mid in membros_ativos_ids:
            reg = por_membro.get(mid, {})
            if not reg.get("presente", False) or reg.get("faltou", False):
                cheio = False
                break
        if cheio:
            dias.add(data)
    return dias
