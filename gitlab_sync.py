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

# As duas colunas que nos interessam na daily.
COLUNAS = ("doing", "review")

# Rotulos padrao das labels no GitLab (podem ser trocados pelo script via variavel de
# ambiente). A comparacao e sempre sem diferenciar maiusculas/minusculas e sem espacos nas
# pontas, porque cada time escreve a label de um jeito.
LABEL_DOING_PADRAO = "Doing"
LABEL_REVIEW_PADRAO = "Waiting review"

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


def _coluna_da_issue(issue, label_doing, label_review):
    """Retorna a lista de colunas em que a issue aparece, pelas labels. Uma issue pode
    estar em 'doing' E em 'review' ao mesmo tempo (duas labels), e tudo bem."""
    alvo = {
        "doing": _norm(label_doing),
        "review": _norm(label_review),
    }
    presentes = {_norm(l) for l in _labels_da_issue(issue)}
    return [col for col in COLUNAS if alvo[col] in presentes]


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


def _corta(texto, limite):
    texto = "" if texto is None else str(texto)
    return texto[:limite]


def montar_retrato(issues, label_doing=LABEL_DOING_PADRAO, label_review=LABEL_REVIEW_PADRAO):
    """Transforma a lista de issues (formato da API do GitLab) em uma lista plana de cards.

    Entrada: `issues` e uma lista de dicts como a API devolve (campos usados: iid, title,
    web_url, labels, assignees/assignee).

    Saida: lista de dicts, um por (card, coluna, responsavel):
        {'iid': int, 'coluna': 'doing'|'review', 'usuario': str,
         'titulo': str, 'url': str, 'labels': str}

    Regras:
      - so entram cards que tenham a label de doing ou de review (comparacao sem caso);
      - uma linha por responsavel (card com 3 responsaveis vira 3 linhas por coluna);
      - card sem responsavel e ignorado (nao da para sugerir a ninguem);
      - card em doing E review gera linhas nas duas colunas;
      - sem repetir a mesma (iid, coluna, usuario).
    """
    vistos = set()
    cards = []
    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        colunas = _coluna_da_issue(issue, label_doing, label_review)
        if not colunas:
            continue
        responsaveis = _responsaveis_da_issue(issue)
        if not responsaveis:
            continue
        try:
            iid = int(issue.get("iid"))
        except (TypeError, ValueError):
            continue
        titulo = _corta(issue.get("title"), MAX_TEXTO)
        url = _corta(issue.get("web_url"), MAX_URL)
        labels = _corta(", ".join(_labels_da_issue(issue)), MAX_TEXTO)
        for coluna in colunas:
            for usuario in responsaveis:
                chave = (iid, coluna, usuario)
                if chave in vistos:
                    continue
                vistos.add(chave)
                cards.append({
                    "iid": iid,
                    "coluna": coluna,
                    "usuario": _corta(usuario, MAX_TEXTO),
                    "titulo": titulo,
                    "url": url,
                    "labels": labels,
                })
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
            raise ValueError("Card com coluna invalida (so 'doing' ou 'review').")
        try:
            iid = int(c.get("iid"))
        except (TypeError, ValueError):
            raise ValueError("Card com iid invalido (precisa ser numero).")
        usuario = (c.get("usuario") or "").strip()
        if not usuario:
            raise ValueError("Card sem responsavel.")
        titulo = c.get("titulo") or ""
        url = c.get("url") or ""
        labels = c.get("labels") or ""
        for valor, limite, nome in (
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
        })
    return limpos


def citacao(card):
    """Como o card entra no texto da fala: '#123 titulo' (titulo opcional)."""
    titulo = (card.get("titulo") or "").strip()
    return f"#{card['iid']} {titulo}".strip()


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
