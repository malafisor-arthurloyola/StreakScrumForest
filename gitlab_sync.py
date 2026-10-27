"""Monta o 'retrato' do quadro do GitLab (apenas leitura) de forma pura e testavel.

A faculdade hospeda o GitLab e o site roda no PythonAnywhere gratuito, que NAO alcanca
a rede da faculdade. Por isso a integracao e por SNAPSHOT EMPURRADO: um script no PC do
dono le o GitLab (com um token pessoal) e envia um retrato pronto para o site. Este modulo
tem a parte que nao depende de rede nem de banco: transformar as issues (no formato da API
do GitLab) em uma lista simples de cards, e validar um retrato recebido.

Sem Flask, sem banco, sem bibliotecas externas: so a biblioteca padrao. Assim da para testar
tudo com fixtures em JSON, sem tocar na rede.

Escopo: SOMENTE LEITURA. Nunca escreve no GitLab. Cards nao rendem semente (isso e decidido
no app; aqui so montamos os dados).
"""

# Colunas internas do retrato. Mantemos 'doing' e 'review' (= "Waiting review") com o mesmo
# significado de antes (dados antigos e testes continuam validos) e acrescentamos:
#   'em_revisao' = a coluna "Review" do quadro (quem esta revisando);
#   'backlog'    = a coluna "Backlog" (cards ainda nao comecados, inclusive sem responsavel);
#   'done'       = cards FECHADOS recentemente (issues state=closed na janela de dias).
COLUNAS = ("doing", "review", "em_revisao", "backlog", "done")

# Colunas em que guardamos tambem cards SEM responsavel (usuario=''): o Backlog (qualquer um
# pode puxar) e as colunas de revisao (o "Vou revisar" e do quadro inteiro, pois quem revisa
# nao e o responsavel do card). Em 'doing' e 'done' exigimos responsavel (sao pessoais).
COLUNAS_SEM_DONO = ("backlog", "review", "em_revisao")

# Rotulos padrao das labels no GitLab (podem ser trocados pelo script via variavel de
# ambiente). A comparacao e sempre sem diferenciar maiusculas/minusculas e sem espacos nas
# pontas, porque cada time escreve a label de um jeito.
LABEL_DOING_PADRAO = "Doing"
LABEL_REVIEW_PADRAO = "Waiting review"      # coluna interna 'review'
LABEL_EM_REVISAO_PADRAO = "Review"          # coluna interna 'em_revisao'
LABEL_BACKLOG_PADRAO = "Backlog"            # coluna interna 'backlog'

# Limites defensivos para o retrato (o site valida de novo ao receber).
MAX_CARDS = 2000
MAX_TEXTO = 300          # titulo / usuario / labels: corta com folga
MAX_URL = 500


def _norm(texto):
    """Normaliza uma label para comparar: sem espacos nas pontas, minuscula."""
    return (texto or "").strip().casefold()


def _labels_da_issue(issue):
    """Lista de labels da issue (a API devolve em 'labels'). Sempre uma lista de str."""
    labels = issue.get("labels") or []
    return [str(x) for x in labels if str(x).strip()]


def _colunas_da_issue(issue, labels_por_coluna):
    """Colunas internas em que a issue aparece, pelas labels. labels_por_coluna e um dict
    {coluna_interna: label_do_quadro}. Uma issue pode estar em mais de uma (duas labels)."""
    presentes = {_norm(l) for l in _labels_da_issue(issue)}
    saida = []
    for coluna in COLUNAS:
        label = labels_por_coluna.get(coluna)
        if label and _norm(label) in presentes:
            saida.append(coluna)
    return saida


def _responsaveis_da_issue(issue):
    """Usernames dos responsaveis. A API do GitLab traz 'assignees' (lista) e, as vezes,
    so 'assignee' (um). Juntamos os dois, sem repetir, ignorando vazios."""
    nomes = []
    for a in (issue.get("assignees") or []):
        u = (a or {}).get("username")
        if u and u not in nomes:
            nomes.append(u)
    a1 = issue.get("assignee") or {}
    u1 = a1.get("username")
    if u1 and u1 not in nomes:
        nomes.append(u1)
    return nomes


def _milestone_da_issue(issue):
    """(titulo, inicio, fim) da milestone da issue (formato da API: issue['milestone']).
    Datas em AAAA-MM-DD; vazio quando a issue nao tem milestone ou a data."""
    ms = issue.get("milestone")
    if not isinstance(ms, dict):
        return "", "", ""
    titulo = _corta(ms.get("title"), MAX_TEXTO)
    inicio = (ms.get("start_date") or "")[:10]
    fim = (ms.get("due_date") or "")[:10]
    return titulo, inicio, fim


def _corta(texto, limite):
    texto = "" if texto is None else str(texto)
    return texto[:limite]


def montar_retrato(issues, label_doing=LABEL_DOING_PADRAO, label_review=LABEL_REVIEW_PADRAO,
                   label_em_revisao=LABEL_EM_REVISAO_PADRAO, label_backlog=LABEL_BACKLOG_PADRAO,
                   fechadas=None):
    """Transforma as issues (formato da API do GitLab) em uma lista plana de cards.

    `issues`: issues ABERTAS (state=opened); a coluna vem das labels (Doing, Waiting review,
    Review, Backlog). `fechadas`: issues FECHADAS recentes (state=closed) -> coluna 'done'
    (o script ja filtrou pela janela de dias; aqui so marcamos). As duas listas aceitam o
    mesmo formato (iid, title, web_url, labels, assignees/assignee).

    Saida: lista de dicts, um por (card, coluna, responsavel):
        {'iid', 'coluna', 'usuario', 'titulo', 'url', 'labels'}

    Regras:
      - a coluna sai das labels (sem diferenciar maiuscula/minuscula);
      - uma linha por responsavel; card em duas colunas gera linhas nas duas;
      - em 'doing' e 'done' o card sem responsavel e ignorado (nao da para sugerir a ninguem);
      - em 'backlog', 'review' e 'em_revisao' guardamos tambem sem responsavel (usuario=''),
        porque a busca no Backlog e o "Vou revisar" sao do quadro inteiro;
      - sem repetir a mesma (iid, coluna, usuario).
    """
    labels_por_coluna = {
        "doing": label_doing,
        "review": label_review,
        "em_revisao": label_em_revisao,
        "backlog": label_backlog,
    }
    vistos = set()
    cards = []

    def _adicionar(issue, coluna):
        try:
            iid = int(issue.get("iid"))
        except (TypeError, ValueError):
            return
        responsaveis = _responsaveis_da_issue(issue)
        if not responsaveis:
            if coluna not in COLUNAS_SEM_DONO:
                return
            responsaveis = [""]       # guarda sem dono, oferecido ao quadro todo
        titulo = _corta(issue.get("title"), MAX_TEXTO)
        url = _corta(issue.get("web_url"), MAX_URL)
        labels = _corta(", ".join(_labels_da_issue(issue)), MAX_TEXTO)
        ms_titulo, ms_inicio, ms_fim = _milestone_da_issue(issue)
        for usuario in responsaveis:
            chave = (iid, coluna, usuario)
            if chave in vistos:
                continue
            vistos.add(chave)
            cards.append({
                "iid": iid, "coluna": coluna, "usuario": _corta(usuario, MAX_TEXTO),
                "titulo": titulo, "url": url, "labels": labels,
                "milestone": ms_titulo, "milestone_inicio": ms_inicio, "milestone_fim": ms_fim,
            })

    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        for coluna in _colunas_da_issue(issue, labels_por_coluna):
            _adicionar(issue, coluna)
    for issue in fechadas or []:
        if isinstance(issue, dict):
            _adicionar(issue, "done")
    return cards


def validar_cards(cards):
    """Valida e normaliza uma lista de cards recebida no snapshot. Devolve a lista limpa.

    Levanta ValueError (com mensagem amigavel, SEM dados sensiveis) se algo estiver fora do
    formato: nao e lista, excede MAX_CARDS, coluna invalida, iid nao inteiro, ou campos de
    texto grandes demais. Nao confia no cliente: o site chama isto antes de gravar.
    """
    if not isinstance(cards, list):
        raise ValueError("O retrato precisa ser uma lista de cards.")
    if len(cards) > MAX_CARDS:
        raise ValueError(f"Retrato grande demais (mais de {MAX_CARDS} cards).")
    limpos = []
    vistos = set()
    for c in cards:
        if not isinstance(c, dict):
            raise ValueError("Cada card precisa ser um objeto.")
        coluna = c.get("coluna")
        if coluna not in COLUNAS:
            raise ValueError("Card com coluna invalida.")
        try:
            iid = int(c.get("iid"))
        except (TypeError, ValueError):
            raise ValueError("Card com iid invalido (precisa ser numero).")
        usuario = (c.get("usuario") or "").strip()
        if not usuario and coluna not in COLUNAS_SEM_DONO:
            raise ValueError("Card sem responsavel.")
        titulo = c.get("titulo") or ""
        url = c.get("url") or ""
        labels = c.get("labels") or ""
        milestone = c.get("milestone") or ""
        ms_inicio = c.get("milestone_inicio") or ""
        ms_fim = c.get("milestone_fim") or ""
        for valor, limite, nome in (
            (milestone, MAX_TEXTO, "milestone"),
            (ms_inicio, 10, "milestone_inicio"),
            (ms_fim, 10, "milestone_fim"),
            (usuario, MAX_TEXTO, "usuario"),
            (titulo, MAX_TEXTO, "titulo"),
            (url, MAX_URL, "url"),
            (labels, MAX_TEXTO, "labels"),
        ):
            if not isinstance(valor, str):
                raise ValueError(f"Campo '{nome}' precisa ser texto.")
            if len(valor) > limite:
                raise ValueError(f"Campo '{nome}' grande demais.")
        chave = (iid, coluna, usuario)
        if chave in vistos:
            continue
        vistos.add(chave)
        limpos.append({
            "iid": iid,
            "coluna": coluna,
            "usuario": usuario,
            "titulo": titulo,
            "url": url,
            "labels": labels,
            "milestone": milestone,
            "milestone_inicio": ms_inicio,
            "milestone_fim": ms_fim,
        })
    return limpos


def citacao(card):
    """Como o card entra no texto da fala: '#123 titulo' (titulo opcional)."""
    titulo = (card.get("titulo") or "").strip()
    return f"#{card['iid']} {titulo}".strip()


def buscar_cards(cards, colunas, consulta, limite=20):
    """Busca por numero (#123 ou 123) ou trecho do titulo (sem diferenciar maiuscula/minuscula)
    nos cards das `colunas` indicadas. Devolve [{iid, titulo, url, responsaveis:[...]}], sem
    repetir o mesmo card (varios responsaveis viram um unico item com a lista), ate `limite`.
    Consulta vazia devolve os primeiros (na ordem recebida)."""
    q = (consulta or "").strip().lstrip("#").casefold()
    agrupados = {}
    ordem = []
    for c in cards or []:
        if c.get("coluna") not in colunas:
            continue
        iid = c["iid"]
        if iid not in agrupados:
            agrupados[iid] = {"iid": iid, "titulo": c.get("titulo", ""),
                              "url": c.get("url", ""), "responsaveis": []}
            ordem.append(iid)
        usuario = (c.get("usuario") or "").strip()
        if usuario and usuario not in agrupados[iid]["responsaveis"]:
            agrupados[iid]["responsaveis"].append(usuario)
    if not q:
        return [agrupados[i] for i in ordem][:limite]
    # o numero exato vem primeiro; depois quem tem o texto no titulo
    exatos = [agrupados[i] for i in ordem if q.isdigit() and str(i) == q]
    por_titulo = [agrupados[i] for i in ordem
                  if not (q.isdigit() and str(i) == q) and q in (agrupados[i]["titulo"] or "").casefold()]
    return (exatos + por_titulo)[:limite]


def busca_backlog(cards, consulta, limite=20):
    """Busca no Backlog (so os cards de coluna 'backlog'). Veja buscar_cards."""
    return buscar_cards(cards, ("backlog",), consulta, limite)


# ------------------------------------------------------------------ usuarios do projeto
MAX_USUARIOS = 500


def _chave(texto):
    """Minusculas, sem acentos e so letras/numeros: 'Joao  Silva' -> 'joaosilva'."""
    import unicodedata
    sem = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return "".join(ch for ch in sem.lower() if ch.isalnum())


def _tokens(texto):
    """Palavras normalizadas do nome: 'Ana Maria' -> ['ana', 'maria']."""
    import unicodedata
    sem = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    out, atual = [], ""
    for ch in sem.lower():
        if ch.isalnum():
            atual += ch
        else:
            if atual:
                out.append(atual)
            atual = ""
    if atual:
        out.append(atual)
    return out


def validar_usuarios(usuarios):
    """Valida a lista [{username, nome}] dos membros do projeto (opcional no retrato)."""
    if usuarios is None:
        return []
    if not isinstance(usuarios, list):
        raise ValueError("A lista de usuarios precisa ser uma lista.")
    if len(usuarios) > MAX_USUARIOS:
        raise ValueError(f"Usuarios demais (mais de {MAX_USUARIOS}).")
    limpos, vistos = [], set()
    for u in usuarios:
        if not isinstance(u, dict):
            raise ValueError("Cada usuario precisa ser um objeto.")
        username = u.get("username")
        nome = u.get("nome") or ""
        if not isinstance(username, str) or not username.strip():
            raise ValueError("Usuario sem username.")
        if not isinstance(nome, str):
            raise ValueError("Nome de usuario precisa ser texto.")
        username = username.strip()
        if len(username) > MAX_TEXTO or len(nome) > MAX_TEXTO:
            raise ValueError("Usuario com texto grande demais.")
        if username in vistos:
            continue
        vistos.add(username)
        limpos.append({"username": username, "nome": nome.strip()})
    return limpos


def montar_usuarios(membros_api):
    """Da lista crua de /projects/:id/members/all (formato da API) para [{username, nome}].
    Ignora bloqueados/inativos e contas de bot."""
    out = []
    for m in membros_api or []:
        if not isinstance(m, dict):
            continue
        username = (m.get("username") or "").strip()
        if not username or (m.get("state") and m.get("state") != "active"):
            continue
        if username.endswith("_bot") or "_bot_" in username or username.startswith("project_") and "_bot" in username:
            continue
        out.append({"username": username, "nome": (m.get("name") or "").strip()})
    return out


def sugerir_mapeamento(membros, usuarios):
    """Casa pessoas do site com usuarios do GitLab, sem adivinhar quando houver duvida.

    membros: [{'id', 'name'}] (so quem ainda NAO tem usuario do GitLab definido).
    usuarios: [{'username', 'nome'}] (membros do projeto).
    Devolve {member_id: username}.

    Regras, em ordem (para na primeira que der EXATAMENTE um candidato):
      1. nome completo igual (ignorando acentos/caixa);
      2. todas as palavras do nome da pessoa estao no nome do GitLab ('Ana' em 'Ana Souza');
      3. o username e o nome da pessoa batem ('ana' = 'ana', ou 'ana.souza' contem 'ana').
    Um usuario do GitLab nunca e dado a duas pessoas: se duas pessoas disputam o mesmo
    usuario, nenhuma das duas e mapeada (o admin escolhe na tela Membros).
    """
    candidatos = {}
    for m in membros:
        chave_m = _chave(m["name"])
        toks_m = _tokens(m["name"])
        if not chave_m:
            continue
        niveis = ([], [], [])
        for u in usuarios:
            nome_u = u.get("nome") or ""
            toks_u = set(_tokens(nome_u))
            chave_user = _chave(u["username"])
            if _chave(nome_u) == chave_m:
                niveis[0].append(u["username"])
            if toks_m and all(t in toks_u for t in toks_m):
                niveis[1].append(u["username"])
            if len(chave_m) >= 3 and (chave_user == chave_m or chave_m in chave_user):
                niveis[2].append(u["username"])
        for nivel in niveis:
            unicos = sorted(set(nivel))
            if len(unicos) == 1:
                candidatos[m["id"]] = unicos[0]
                break
            if len(unicos) > 1:
                break           # ambiguo neste nivel: nao tenta niveis mais frouxos
    # um usuario so para uma pessoa
    contagem = {}
    for username in candidatos.values():
        contagem[username] = contagem.get(username, 0) + 1
    return {mid: u for mid, u in candidatos.items() if contagem[u] == 1}


# ------------------------------------------------------------------ milestone (sprint) atual
# So estas colunas respeitam a milestone: o que esta em revisao ou foi fechado na sprint ATUAL.
# Doing e Backlog continuam mostrando tudo (o que a pessoa vai fazer / pegar nao depende da sprint).
COLUNAS_DA_SPRINT = ("review", "em_revisao", "done")


def _numero(texto):
    """Primeiro numero do texto: 'Sprint 02' -> 2; sem numero -> None."""
    import re
    m = re.search(r"\d+", texto or "")
    return int(m.group()) if m else None


def milestone_atual(milestones, hoje, sprint_n=None):
    """Descobre qual milestone e a da sprint de hoje, sem configurar nada.

    milestones: lista de (titulo, inicio, fim) (datas AAAA-MM-DD ou ''), as que aparecem nos
    cards. hoje: AAAA-MM-DD. sprint_n: numero da sprint de hoje no calendario do site (opcional).

    Regras, na ordem:
      1. a milestone cujo periodo contem hoje (inicio <= hoje <= fim);
      2. se nenhuma contem (ex.: fim de semana entre duas sprints), a que comecou mais
         recentemente antes de hoje; se ainda nao comecou nenhuma, a mais proxima no futuro;
      3. sem datas nenhuma: a milestone cujo titulo tem o mesmo numero da sprint de hoje
         ('Sprint 02' = sprint 2).
    Devolve o titulo, ou None se nao houver como saber (aí nada e filtrado).
    """
    unicas = []
    vistos = set()
    for t, i, f in milestones:
        if t and (t, i, f) not in vistos:
            vistos.add((t, i, f))
            unicas.append((t, i or "", f or ""))
    if not unicas:
        return None
    com_data = [m for m in unicas if m[1] and m[2]]
    for t, i, f in com_data:
        if i <= hoje <= f:
            return t
    if com_data:
        passadas = sorted((m for m in com_data if m[1] <= hoje), key=lambda m: m[1])
        if passadas:
            return passadas[-1][0]
        futuras = sorted(com_data, key=lambda m: m[1])
        return futuras[0][0]
    if sprint_n is not None:
        for t, _i, _f in unicas:
            if _numero(t) == sprint_n:
                return t
    return None
