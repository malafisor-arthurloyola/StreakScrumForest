import math
from datetime import date, timedelta


STAGE_NAMES = [
    "Semente",
    "Brotinho",
    "Muda",
    "Folhinhas",
    "Jovem",
    "Crescendo",
    "Viçosa",
    "Botões",
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

# sementes por evento com presenca (um dia com os tres eventos rende 3)
SEED_POR_EVENTO = {"daily": 1, "dev": 1, "encerramento": 1}

# bonus fixos (fonte unica de verdade: usados em calcular_sementes e na aba /sementes)
SEED_SEMANA_FECHADA = 3   # por semana fechada
SEED_DIA_CHEIO = 1        # por dia cheio do time, para cada presente
SEED_FLORESCEU = 20       # ao florescer (bonus unico)
SEED_BOAS_VINDAS = 20     # ao registrar a 1a presenca (bonus unico)
SEED_ATA = 1              # por ata (daily/fechamento) com a fala da pessoa preenchida
SEED_RELATOR = 1          # por fala de OUTRA pessoa que o relator (Scrum) preencheu na ata
SEED_RELATOR_MAX_POR_ATA = 3   # limite do bonus do relator por ata (Daily ou Day Closing)

# minigames do celular (aba Meu jardim). Rendem por FAZER, nunca pelo conteudo, e so em dia
# letivo com presenca. O servidor so grava a jogada quando a regra foi cumprida (ex.: fala pronta
# antes da vez da pessoa na rodada); aqui so se conta o que foi gravado.
SEED_FALA_PRONTA = 5          # fala da daily pronta antes da sua vez na rodada
SEED_FECHAMENTO_PRONTO = 3    # Day Closing preenchido no proprio dia
SEED_CUIDAR = 3               # regar, adubar e carinho, depois do fechamento pronto
SEED_FIGURINHA = 10           # semana do Album da estacao revelada
SEED_ESTACAO_COMPLETA = 10    # todas as semanas de uma sprint reveladas (figurinha dourada)
FIGURINHA_MIN_FALAS = 3       # falas prontas na semana para revelar a figurinha
CUIDADOS = ("regar", "adubar", "carinho")
MINIJOGOS = {
    "fala_pronta": (SEED_FALA_PRONTA, "Fala pronta"),
    "fechamento_pronto": (SEED_FECHAMENTO_PRONTO, "Fechamento pronto"),
    "cuidar": (SEED_CUIDAR, "Cuidou da planta"),
}

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
    # espaca os estagios 2 a 10 de forma uniforme entre o primeiro dia e a meta,
    # para a planta mudar a cada ~4 dias (inclusive na primeira semana)
    return 1 + math.ceil((k - 1) * (meta - 1) / 9)


def estagio_para_g(g, meta):
    """Retorna o estagio (0-10) para um valor de G."""
    estagio = 0
    for k in range(10, 0, -1):
        if g >= limiar_estagio(k, meta):
            estagio = k
            break
    return estagio


def progresso_estagio(g, meta, estagio):
    """Quanto do caminho ate o proximo estagio ja foi feito (0..1) e quantas
    presencas faltam. E isso que faz a planta crescer um pouco a cada dia."""
    if estagio >= 10:
        return 1.0, 0
    ini = limiar_estagio(estagio, meta)
    fim = limiar_estagio(estagio + 1, meta)
    if fim <= ini:
        return 1.0, 0
    p = (g - ini) / (fim - ini)
    return round(min(max(p, 0.0), 1.0), 2), max(fim - g, 0)


def nivel_chama(streak):
    """Nivel do foguinho: 0 apagado, 1 a 4 conforme a sequencia cresce."""
    if streak <= 0:
        return 0
    if streak < 3:
        return 1
    if streak < 7:
        return 2
    if streak < 14:
        return 3
    return 4


def periodo_do_dia(hora):
    """hora em decimal (ex.: 14.5 = 14h30). Mesma regra de atualizarCena() em app.js.
    Os estagios seguem as aulas: 8h manha, 14h tarde, 15h45 entardecer (encerramento)."""
    if hora < 5:
        return "madrugada"
    if hora < 8:
        return "amanhecer"
    if hora < 12:
        return "manha"          # 8h: comeca a manha (a daily)
    if hora < 14:
        return "meiodia"
    if hora < 15.75:
        return "tarde"          # 14h: comeca a tarde
    if hora < 18.5:
        return "entardecer"     # 15h45: "mais tarde", o horario do encerramento
    return "noite"


def posicao_astro(hora, inicio, duracao):
    """Posicao (x%, y%) de sol/lua em arco. Fora da janela fica no horizonte."""
    t = ((hora - inicio) % 24) / duracao
    t = min(max(t, 0.0), 1.0)
    return round(8 + 84 * t, 1), round(66 - 56 * math.sin(math.pi * t), 1)


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
        "floresceu_em": floresceu_em,
    }


def _minimo_semana(n_letivos):
    """Presencas para fechar a semana: 4, ou (dias letivos - 1) em semana com feriado."""
    return n_letivos - 1 if n_letivos < 5 else 4


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
        minimo = _minimo_semana(len(dias_sem))
        presencas = sum(
            1 for d in dias_sem if registros_por_data.get(d, {}).get("presente", False)
        )
        if presencas >= minimo:
            fechadas += 1
    return fechadas


def calcular_sementes(dias_letivos_lista, semanas_projeto, registros_por_data, floresceu,
                      dias_cheios=None, atas_com_fala=0, falas_relatadas=0, bonus_metas=0,
                      minijogos=()):
    """
    Calcula sementes ganhas (nunca perde por falta).
    Retorna dict com total e detalhes.

    atas_com_fala: numero de atas (daily/fechamento) em que a pessoa deixou a fala
    preenchida (feito OU planejado nao vazio) -> +SEED_ATA cada (adubo).
    falas_relatadas: numero de falas de OUTRAS pessoas que ela preencheu como relator (uma por
    pessoa e por ata) -> +SEED_RELATOR cada. A fala dela mesma rende o +SEED_ATA normal.
    Impedimentos nunca entram aqui (nao rendem semente).
    """
    dias_presentes = sum(
        1 for d in dias_letivos_lista if registros_por_data.get(d, {}).get("presente", False)
    )
    por_evento = {e: 0 for e in SEED_POR_EVENTO}
    for d in dias_letivos_lista:
        reg = registros_por_data.get(d, {})
        if not reg.get("presente", False):
            continue
        eventos = reg.get("eventos")
        if eventos is None:  # registro sem detalhe por evento: vale como um evento
            por_evento["daily"] += 1
        else:
            for e in eventos:
                if e in por_evento:
                    por_evento[e] += 1
    seeds_eventos = sum(por_evento[e] * SEED_POR_EVENTO[e] for e in por_evento)
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

    bonus_floresceu = SEED_FLORESCEU if floresceu else 0

    # boas-vindas: bonus unico para quem ja registrou pelo menos uma presenca
    por_boas_vindas = SEED_BOAS_VINDAS if dias_presentes > 0 else 0

    # dia cheio do time: +1 para quem veio nesse dia
    por_dia_cheio = SEED_DIA_CHEIO * sum(
        1 for d in (dias_cheios or ())
        if registros_por_data.get(d, {}).get("presente", False)
    )

    # atas (Fase 4): adubo fixo, sem avaliar conteudo. Impedimentos nao entram.
    por_ata = SEED_ATA * max(0, int(atas_com_fala))
    por_relator = SEED_RELATOR * max(0, int(falas_relatadas))
    por_metas = max(0, int(bonus_metas))
    por_minijogos = sum(p["valor"] for p in minijogos)   # premios_minijogos(...)

    total = (seeds_eventos + semenas_fechadas * SEED_SEMANA_FECHADA + marcos + bonus_floresceu
             + por_dia_cheio + por_boas_vindas + por_ata + por_relator + por_metas + por_minijogos)
    return {
        "total": total,
        "por_presenca": seeds_eventos,
        "por_evento": por_evento,
        "por_semanas_fechadas": semenas_fechadas * SEED_SEMANA_FECHADA,
        "por_marcos": marcos,
        "por_floresceu": bonus_floresceu,
        "por_dia_cheio": por_dia_cheio,
        "por_boas_vindas": por_boas_vindas,
        "por_ata": por_ata,
        "por_relator": por_relator,
        "por_metas": por_metas,
        "por_minijogos": por_minijogos,
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


def proximo_marco(streak_atual):
    """Proximo marco de sequencia a alcancar, a partir da sequencia atual.

    Retorna dict com alvo (dias do proximo marco), bonus (sementes), faltam (dias
    que faltam) e feito (bool se ja passou do ultimo marco). Se nao ha mais marcos,
    alvo/bonus/faltam ficam em None e feito=True. Funcao pura, sem banco.
    """
    for limiar, bonus in SEED_MILESTONES:
        if streak_atual < limiar:
            return {
                "alvo": limiar,
                "bonus": bonus,
                "faltam": limiar - streak_atual,
                "feito": False,
            }
    return {"alvo": None, "bonus": None, "faltam": None, "feito": True}


def e_fundador(registros_por_data, fundador_ate):
    """True se a pessoa teve presenca em qualquer dia ate (inclusive) fundador_ate.
    Funcao pura. fundador_ate e uma string AAAA-MM-DD; vazio/None -> ninguem e fundador."""
    if not fundador_ate:
        return False
    for data, reg in registros_por_data.items():
        if data <= fundador_ate and reg.get("presente", False):
            return True
    return False


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


def estado_ate(dias_letivos_lista, registros_por_data, meta, data):
    """Estado do membro como estava no fim de `data` (usado em resumos de sprint/semana)."""
    return calcular_membro([d for d in dias_letivos_lista if d <= data], registros_por_data, meta)


# ---------------------------------------------------------------- sprints e metas

def sprints_do_projeto(semana1_inicio, num_semanas, sprint_semanas):
    """[{'n', 'inicio', 'fim'}]; o fim e a sexta da ultima semana da sprint."""
    s1 = date.fromisoformat(semana1_inicio)
    lista = []
    sem = 0
    n = 1
    while sem < num_semanas:
        na_sprint = min(sprint_semanas, num_semanas - sem)
        inicio = s1 + timedelta(weeks=sem)
        fim = inicio + timedelta(weeks=na_sprint) - timedelta(days=3)
        lista.append({"n": n, "inicio": inicio.isoformat(), "fim": fim.isoformat()})
        sem += na_sprint
        n += 1
    return lista


def sprint_da_data(data_str, sprints):
    """Numero da sprint de uma data (antes do projeto = 1; depois = a ultima)."""
    atual = sprints[0]["n"]
    for sp in sprints:
        if sp["inicio"] <= data_str:
            atual = sp["n"]
    return atual


def avaliar_meta(tipo, alvo, dias_sprint, hoje_str, ativos_ids, registros_globais, dias_cheios):
    """Progresso de uma meta da sprint, sempre derivado da presenca.

    Tipos: presenca_pct (% de presencas do time), dias_cheios (quantidade de dias com todo
    mundo presente) e sequencia_time (maior sequencia de dias cheios seguidos).
    Considera so os dias da sprint que ja passaram (ate hoje).
    """
    decorridos = [d for d in dias_sprint if d <= hoje_str]
    valor = 0
    if tipo == "presenca_pct":
        possiveis = len(decorridos) * len(ativos_ids)
        if possiveis:
            presentes = sum(
                1 for d in decorridos for mid in ativos_ids
                if registros_globais.get(d, {}).get(mid, {}).get("presente", False)
            )
            valor = round(100 * presentes / possiveis)
    elif tipo == "dias_cheios":
        valor = sum(1 for d in decorridos if d in dias_cheios)
    elif tipo == "sequencia_time":
        atual = 0
        for d in decorridos:
            atual = atual + 1 if d in dias_cheios else 0
            valor = max(valor, atual)
    pct = min(100, round(100 * valor / alvo)) if alvo > 0 else 0
    return {"valor": valor, "alvo": alvo, "pct": pct, "cumprida": alvo > 0 and valor >= alvo}


MARCOS_COLETIVOS = [
    (25, "fonte", "Fonte do jardim", "Uma fonte aparece no canteiro."),
    (50, "vagalumes", "Vagalumes extras", "Mais luzinhas passeiam pelo jardim."),
    (75, "petalas", "Chuva de pétalas", "Pétalas caem devagar sobre o canteiro."),
    (100, "arvore_time", "Árvore do time", "Uma árvore grande cresce no fundo do jardim."),
]


def marcos_coletivos(progresso_pct):
    """Desbloqueios gratuitos para todo mundo conforme o jardim coletivo cresce."""
    return [
        {"pct": pct, "id": mid, "nome": nome, "desc": desc, "liberado": progresso_pct >= pct}
        for pct, mid, nome, desc in MARCOS_COLETIVOS
    ]


def semanas_status(semanas_projeto, registros_por_data, hoje_str, contar_a_partir_de):
    """Trilha de semanas de um membro.

    Estados: fechada, em_andamento, futura, aberta (passou sem fechar, sem punicao),
    largada (semana de inicio em que nao da para fechar) e folga (so feriados).
    """
    trilha = []
    for i, dias_sem in enumerate(semanas_projeto, 1):
        if not dias_sem:
            trilha.append({"n": i, "estado": "folga", "presencas": 0, "minimo": 0})
            continue
        n = len(dias_sem)
        minimo = n - 1 if n < 5 else 4
        contaveis = [d for d in dias_sem if d >= contar_a_partir_de]
        presencas = sum(1 for d in dias_sem if registros_por_data.get(d, {}).get("presente", False))
        if presencas >= minimo:
            estado = "fechada"
        elif len(contaveis) < minimo:
            estado = "largada"
        elif dias_sem[-1] < hoje_str:
            estado = "aberta"
        elif dias_sem[0] <= hoje_str:
            estado = "em_andamento"
        else:
            estado = "futura"
        trilha.append({"n": i, "estado": estado, "presencas": presencas, "minimo": minimo})
    return trilha


def sequencia_dias_cheios(dias_letivos_lista, cheios, dias_com_registro, hoje_str):
    """Dias cheios seguidos ate hoje. Dia sem nenhum registro nao quebra (esquecer de
    marcar nao pune); dia com registro em que alguem nao veio quebra."""
    seq = 0
    for d in reversed([d for d in dias_letivos_lista if d <= hoje_str]):
        if d in cheios:
            seq += 1
        elif d in dias_com_registro:
            break
    return seq


def nivel_presenca(presentes, total):
    """Intensidade (0 a 4) de um dia no panorama do time, estilo mapa de contribuicoes."""
    if total <= 0 or presentes <= 0:
        return 0
    if presentes >= total:
        return 4
    razao = presentes / total
    if razao >= 0.7:
        return 3
    if razao >= 0.5:
        return 2
    return 1


# ---------------------------------------------------------------- extrato de sementes
ROTULO_ATA = {"daily": "Daily", "fechamento": "Day Closing"}
ROTULO_EVENTO = {"daily": "Daily", "dev": "Dev", "encerramento": "Encerramento"}


def extrato_sementes(dias_letivos_lista, semanas_projeto, registros_por_data, meta,
                     dias_cheios=None, falas=(), relatadas=None, metas=(), minijogos=()):
    """Lista cada ganho de sementes, com data e motivo: o "extrato" da pessoa.

    A soma dos valores e IGUAL a calcular_sementes(...)["total"] com os mesmos dados (ha teste
    para isso): o extrato so conta a historia, nao muda nenhuma regra.

    falas: [(data, tipo)] das atas em que a pessoa deixou a fala preenchida (+SEED_ATA cada).
    relatadas: {(data, tipo): [nomes]} das falas de OUTRAS pessoas que ela preencheu como relator
    (+SEED_RELATOR cada, no maximo SEED_RELATOR_MAX_POR_ATA por ata).
    metas: premios de metas personalizadas, da funcao premios_de_metas.
    Cada item: {'data', 'fonte', 'rotulo', 'valor', 'detalhe'}.
    """
    dias = list(dias_letivos_lista)
    dias_set = set(dias)
    linhas = []

    def _add(data, fonte, rotulo, valor, detalhe=""):
        if valor:
            linhas.append({"data": data, "fonte": fonte, "rotulo": rotulo, "valor": valor, "detalhe": detalhe})

    # presenca nos eventos (um item por dia)
    primeira_presenca = None
    for d in dias:
        reg = registros_por_data.get(d, {})
        if not reg.get("presente", False):
            continue
        if primeira_presenca is None:
            primeira_presenca = d
        eventos = reg.get("eventos")
        if eventos is None:
            eventos = {"daily"}
        validos = [e for e in SEED_POR_EVENTO if e in eventos]
        _add(d, "eventos", "Presença", sum(SEED_POR_EVENTO[e] for e in validos),
             " + ".join(ROTULO_EVENTO[e] for e in validos))

    # boas-vindas: no dia da primeira presenca
    if primeira_presenca:
        _add(primeira_presenca, "boas_vindas", "Boas-vindas", SEED_BOAS_VINDAS, "primeira presença registrada")

    # semana fechada: no dia em que as presencas da semana atingiram o minimo
    for dias_sem in semanas_projeto:
        if not dias_sem:
            continue
        minimo = _minimo_semana(len(dias_sem))
        feitas = 0
        for d in dias_sem:
            if registros_por_data.get(d, {}).get("presente", False):
                feitas += 1
                if feitas == minimo:
                    _add(d, "semanas", "Semana fechada", SEED_SEMANA_FECHADA,
                         f"{minimo} presenças na semana de {dias_sem[0][8:10]}/{dias_sem[0][5:7]}")
                    break

    # marcos de sequencia: no dia em que a sequencia chegou ao limiar (uma vez cada)
    streak = 0
    atingidos = set()
    for d in dias:
        reg = registros_por_data.get(d, {})
        if reg.get("presente", False):
            streak += 1
            for limiar, bonus in SEED_MILESTONES:
                if streak >= limiar and limiar not in atingidos:
                    atingidos.add(limiar)
                    _add(d, "marcos", "Marco de sequência", bonus, f"{limiar} dias seguidos")
        elif reg.get("faltou", False):
            streak = 0

    # dia cheio do time
    for d in sorted(dias_cheios or ()):
        if d in dias_set and registros_por_data.get(d, {}).get("presente", False):
            _add(d, "dia_cheio", "Dia cheio do time", SEED_DIA_CHEIO, "todo o time presente")

    # floresceu: no primeiro dia em que a planta chegou ao ultimo estagio
    for i, d in enumerate(dias):
        if calcular_membro(dias[: i + 1], registros_por_data, meta)["floresceu"]:
            _add(d, "floresceu", "Floresceu", SEED_FLORESCEU, "a planta chegou ao último estágio")
            break

    # atas preenchidas (adubo)
    for data, tipo in sorted(set(falas)):
        if data in dias_set:
            _add(data, "ata", f"{ROTULO_ATA.get(tipo, tipo)} preenchida", SEED_ATA, "sua fala está na ata")

    # bonus do relator: por fala de outra pessoa que ele preencheu, com limite por ata
    for (data, tipo), nomes in sorted((relatadas or {}).items()):
        if data not in dias_set or not nomes:
            continue
        n = min(len(nomes), SEED_RELATOR_MAX_POR_ATA)
        detalhe = ", ".join(nomes[:n])
        if len(nomes) > n:
            detalhe += f" (limite de {SEED_RELATOR_MAX_POR_ATA} por ata; {len(nomes) - n} sem bônus)"
        _add(data, "relator", f"Scrum: preencheu a {ROTULO_ATA.get(tipo, tipo)} de colegas", SEED_RELATOR * n, detalhe)

    for p in metas:
        _add(p["data"], "meta", "Meta cumprida", p["valor"], p["titulo"])

    for p in minijogos:
        _add(p["data"], "minijogo", p["rotulo"], p["valor"], p["detalhe"])

    linhas.sort(key=lambda x: (x["data"], x["fonte"]))
    return linhas


# ---------------------------------------------------------------- metas personalizadas
SEED_META_MAX = 30


def premios_de_metas(metas, member_id, equipe_ids):
    """Sementes que as metas personalizadas rendem a uma pessoa.

    metas: [{'titulo', 'prazo', 'sementes', 'para_time', 'cumprida_em', 'membros': [ids]}].
    Rende quando a meta foi marcada como cumprida ate o prazo (inclusive); fora do prazo ou
    ainda aberta nao rende nada e nao tira nada de ninguem. Meta do time vale para todos da
    equipe; as demais, so para quem foi escolhido. Cada meta rende no maximo SEED_META_MAX.
    Retorna [{'data', 'titulo', 'valor'}].
    """
    premios = []
    for m in metas:
        feita = m.get("cumprida_em")
        if not feita or feita > m["prazo"]:
            continue
        alvo = set(equipe_ids) if m.get("para_time") else set(m.get("membros") or ())
        if member_id not in alvo:
            continue
        valor = max(0, min(int(m["sementes"]), SEED_META_MAX))
        if valor:
            premios.append({"data": feita, "titulo": m["titulo"], "valor": valor})
    return premios


# ---------------------------------------------------------------- minigames (aba Meu jardim)
def album_estacao(datas_fala_pronta, semanas_projeto, sprint_semanas=2):
    """Album da estacao: uma figurinha por semana do projeto.

    A figurinha se revela quando a semana tem FIGURINHA_MIN_FALAS falas prontas (ou todos os dias
    letivos dela, se a semana tiver menos dias por causa de feriado). Semana sem dia letivo e folga.
    Quando todas as semanas com aula de uma sprint estao reveladas, a ultima delas vira dourada.
    Perder uma semana nao apaga nada. Retorna [{'n', 'sprint', 'falas', 'minimo', 'revelada',
    'data', 'dourada', 'folga'}], na ordem das semanas.
    """
    feitas = set(datas_fala_pronta)
    album = []
    for i, dias_sem in enumerate(semanas_projeto):
        minimo = min(FIGURINHA_MIN_FALAS, len(dias_sem))
        datas = sorted(d for d in dias_sem if d in feitas)
        revelada = minimo > 0 and len(datas) >= minimo
        album.append({
            "n": i + 1, "sprint": i // max(sprint_semanas, 1) + 1, "falas": len(datas),
            "minimo": minimo, "revelada": revelada, "data": datas[minimo - 1] if revelada else None,
            "dourada": False, "folga": minimo == 0,
        })
    por_sprint = {}
    for f in album:
        por_sprint.setdefault(f["sprint"], []).append(f)
    for semanas in por_sprint.values():
        com_aula = [f for f in semanas if not f["folga"]]
        if com_aula and all(f["revelada"] for f in com_aula):
            max(com_aula, key=lambda f: f["data"])["dourada"] = True
    return album


def premios_minijogos(jogadas, semanas_projeto, registros_por_data, sprint_semanas=2):
    """Sementes dos minigames de uma pessoa, uma linha de extrato por premio.

    jogadas: [(data, jogo)] gravadas pelo servidor (jogo em MINIJOGOS; outras marcas, como as
    acoes do cuidado, sao ignoradas). So vale em dia letivo com presenca. Uma por dia e jogo.
    Retorna [{'data', 'rotulo', 'valor', 'detalhe'}].
    """
    letivos = {d for sem in semanas_projeto for d in sem}
    validas = sorted({
        (d, j) for d, j in jogadas
        if j in MINIJOGOS and d in letivos and registros_por_data.get(d, {}).get("presente", False)
    })
    premios = []
    detalhes = {"fala_pronta": "a fala da daily estava pronta antes da sua vez",
                "fechamento_pronto": "o Day Closing ficou preenchido", "cuidar": "regou, adubou e fez carinho"}
    for d, j in validas:
        valor, rotulo = MINIJOGOS[j]
        premios.append({"data": d, "rotulo": rotulo, "valor": valor, "detalhe": detalhes[j]})
    falas = [d for d, j in validas if j == "fala_pronta"]
    for f in album_estacao(falas, semanas_projeto, sprint_semanas):
        if f["revelada"]:
            premios.append({"data": f["data"], "rotulo": "Figurinha do Álbum da estação", "valor": SEED_FIGURINHA,
                            "detalhe": f"semana {f['n']} com {FIGURINHA_MIN_FALAS} falas prontas"})
        if f["dourada"]:
            premios.append({"data": f["data"], "rotulo": "Figurinha dourada", "valor": SEED_ESTACAO_COMPLETA,
                            "detalhe": f"todas as semanas da Sprint {f['sprint']} no álbum"})
    return premios
