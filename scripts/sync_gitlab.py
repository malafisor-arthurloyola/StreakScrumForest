"""Le o quadro do GitLab (SO LEITURA) e empurra um retrato para o Jardim da Equipe.

Roda no COMPUTADOR DO DONO (ou de quem tiver acesso ao GitLab da faculdade), nunca no
servidor. O servidor (PythonAnywhere gratuito) nao alcanca a rede da faculdade, entao este
script faz a ponte: le as issues com o SEU token pessoal do GitLab e envia so o resultado
pronto para o site, autenticando com o SYNC_TOKEN (um segredo combinado entre o script e o
servidor).

So usa a biblioteca padrao do Python (urllib) - nada para instalar.

O que ele manda: para cada card nas colunas "Doing" e "Waiting review", o numero (#iid), o
titulo, o link e o(s) responsavel(is). Nada mais. Nunca escreve no GitLab.

------------------------------------------------------------------- Como configurar (uma vez)
O jeito mais confortavel e criar um arquivo .env na pasta do projeto (copie o .env.exemplo),
com uma variavel por linha. O script le esse .env sozinho; o que ja estiver no ambiente tem
prioridade. O .env fica so no seu computador e NUNCA e versionado (esta no .gitignore).

    .env (exemplo de conteudo):
        GITLAB_URL=https://git.inteli.edu.br
        GITLAB_PROJECT=graduacao/2026-2b/t24/g01
        GITLAB_TOKEN=glpat-xxxxxxxx
        SITE_URL=https://suaconta.pythonanywhere.com
        SITE_SYNC_TOKEN=um-segredo-forte

Se preferir, da para definir as variaveis direto no terminal, sem .env:

    PowerShell (Windows):
        $env:GITLAB_URL   = "https://gitlab.suafaculdade.br"
        $env:GITLAB_PROJECT = "123"                 # o Project ID
        $env:GITLAB_TOKEN = "glpat-xxxxxxxx"        # seu token pessoal (read_api)
        $env:SITE_URL     = "https://suaconta.pythonanywhere.com"
        $env:SITE_SYNC_TOKEN = "um-segredo-forte"   # o MESMO SYNC_TOKEN do servidor

    cmd:
        set GITLAB_URL=...   (e assim por diante)

Destinos (onde enviar). Defina o(s) que usa:
        SITE_URL_PRODUCAO=https://suaconta.pythonanywhere.com
        SITE_URL_LOCAL=http://localhost:5000
        SITE_URL=...                    # (antigo) usado quando nenhum dos dois acima existir
    O segredo e o mesmo SITE_SYNC_TOKEN para todos (cada servidor tem o seu SYNC_TOKEN igual a ele);
    se o do local for diferente, use SITE_SYNC_TOKEN_LOCAL (e SITE_SYNC_TOKEN_PRODUCAO).

Rodar:
    python scripts/sync_gitlab.py                 # le o GitLab e empurra para o destino padrao
    python scripts/sync_gitlab.py --destino producao   # so para o site publicado
    python scripts/sync_gitlab.py --destino local      # so para o site no seu computador
    python scripts/sync_gitlab.py --destino ambos      # para os dois
    python scripts/sync_gitlab.py --simular       # le e MOSTRA o que enviaria (nao envia)
    python scripts/sync_gitlab.py --listar-usuarios  # lista os responsaveis (para mapear no site)
    python scripts/sync_gitlab.py --arquivo q.json   # le de um arquivo em vez do GitLab (teste)

As labels podem ser trocadas (o padrao e "Doing" e "Waiting review"), sem diferenciar
maiusculas/minusculas:
    $env:GITLAB_LABEL_DOING  = "Doing"
    $env:GITLAB_LABEL_REVIEW = "Waiting review"

SEGURANCA: o token do GitLab e o SYNC_TOKEN NUNCA aparecem em mensagens nem no site. Se algo
falhar, a mensagem de erro nao mostra segredos.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# deixa importar o modulo puro de montagem, que fica na raiz do projeto
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
import gitlab_sync  # noqa: E402

TIMEOUT = 20
POR_PAGINA = 100
MAX_PAGINAS = 50          # trava de seguranca (ate 5000 issues)


def _env(nome, padrao=None, obrigatorio=False):
    valor = os.environ.get(nome, padrao)
    if obrigatorio and not valor:
        _sair(f"Falta a variavel {nome}. Defina no arquivo .env (veja .env.exemplo) ou como variavel de ambiente.")
    return valor


def carregar_dotenv(caminho=None):
    """Le um arquivo .env (se existir) e preenche as variaveis que ainda nao estao definidas.

    Formato simples: uma linha por variavel, NOME=valor. Linhas em branco e as que comecam
    com '#' sao ignoradas. Aspas simples/duplas em volta do valor sao removidas. O que ja
    estiver no ambiente TEM PRIORIDADE (nao sobrescrevemos), para dar para testar mudando so
    uma variavel na hora. So biblioteca padrao: nada para instalar.

    O .env fica no seu computador e NUNCA e versionado (esta no .gitignore).
    """
    if caminho is None:
        caminho = os.path.join(RAIZ, ".env")
    if not os.path.isfile(caminho):
        return False
    with open(caminho, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            nome, _, valor = linha.partition("=")
            nome = nome.strip()
            valor = valor.strip()
            if (len(valor) >= 2) and valor[0] == valor[-1] and valor[0] in ("'", '"'):
                valor = valor[1:-1]
            if nome and nome not in os.environ:
                os.environ[nome] = valor
    return True


def _sair(msg, codigo=1):
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(codigo)


def _get_json(url, headers):
    """GET que devolve (dados_json, cabecalhos). Sem imprimir segredos em caso de erro."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            corpo = resp.read().decode("utf-8")
            return json.loads(corpo), dict(resp.headers)
    except urllib.error.HTTPError as e:
        _sair(f"O GitLab respondeu {e.code} ao ler as issues. Verifique a URL, o Project ID e o token.")
    except urllib.error.URLError as e:
        _sair(f"Nao consegui falar com o GitLab ({e.reason}). Voce esta na rede certa?")
    except (ValueError, json.JSONDecodeError):
        _sair("O GitLab devolveu algo que nao e JSON. Verifique a URL.")


def ler_issues_do_gitlab(base, projeto, token):
    """Le TODAS as issues abertas do projeto, paginando. Devolve a lista crua (formato da API)."""
    base = base.rstrip("/")
    projeto_cod = urllib.parse.quote(str(projeto), safe="")
    headers = {"PRIVATE-TOKEN": token, "Accept": "application/json"}
    issues = []
    for pagina in range(1, MAX_PAGINAS + 1):
        params = urllib.parse.urlencode({
            "state": "opened", "per_page": POR_PAGINA, "page": pagina,
            "with_labels_details": "false",
        })
        url = f"{base}/api/v4/projects/{projeto_cod}/issues?{params}"
        lote, cabecalhos = _get_json(url, headers)
        if not isinstance(lote, list) or not lote:
            break
        issues.extend(lote)
        proxima = cabecalhos.get("X-Next-Page") or cabecalhos.get("x-next-page") or ""
        if not str(proxima).strip():
            break
    return issues


def _carregar_de_arquivo(caminho):
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError) as e:
        _sair(f"Nao consegui ler o arquivo {caminho}: {e}")
    if not isinstance(dados, list):
        _sair("O arquivo precisa conter uma lista de issues (formato da API do GitLab).")
    return dados


class ErroEnvio(Exception):
    """Falha ao enviar para UM destino (a mensagem nunca traz segredos)."""


def enviar_snapshot(site_url, sync_token, cards, base_url, usuarios=None):
    """Faz POST /api/gitlab/snapshot com Bearer SYNC_TOKEN. Devolve o dict de resposta."""
    url = site_url.rstrip("/") + "/api/gitlab/snapshot"
    corpo = json.dumps({"cards": cards, "base_url": base_url, "usuarios": usuarios or []}).encode("utf-8")
    req = urllib.request.Request(url, data=corpo, method="POST", headers={
        "Authorization": f"Bearer {sync_token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise ErroEnvio("o site recusou a autorizacao (SYNC_TOKEN nao confere com o do servidor).")
        if e.code == 404:
            raise ErroEnvio("o site nao tem a sincronizacao ligada (defina SYNC_TOKEN no servidor e de Reload).")
        raise ErroEnvio(f"o site respondeu {e.code} ao receber o retrato.")
    except urllib.error.URLError as e:
        raise ErroEnvio(f"nao consegui falar com o site ({e.reason}).")
    except (ValueError, json.JSONDecodeError):
        raise ErroEnvio("o site devolveu algo que nao e JSON.")


def ler_membros_do_projeto(base, projeto, token):
    """Le os membros do projeto (usuario e nome) para casar com as pessoas do site.
    Se o token nao puder listar membros, devolve None (o resto continua funcionando)."""
    base = base.rstrip("/")
    projeto_cod = urllib.parse.quote(str(projeto), safe="")
    headers = {"PRIVATE-TOKEN": token, "Accept": "application/json"}
    membros = []
    for pagina in range(1, MAX_PAGINAS + 1):
        params = urllib.parse.urlencode({"per_page": POR_PAGINA, "page": pagina})
        url = f"{base}/api/v4/projects/{projeto_cod}/members/all?{params}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                lote = json.loads(resp.read().decode("utf-8"))
                proxima = resp.headers.get("X-Next-Page") or ""
        except (urllib.error.URLError, ValueError):
            return None
        if not isinstance(lote, list) or not lote:
            break
        membros.extend(lote)
        if not str(proxima).strip():
            break
    return gitlab_sync.montar_usuarios(membros)


def escolher_destinos(destino):
    """Devolve a lista de (nome, url, token) onde enviar, conforme --destino e o .env."""
    url_prod = os.environ.get("SITE_URL_PRODUCAO", "").strip()
    url_local = os.environ.get("SITE_URL_LOCAL", "").strip()
    url_antiga = os.environ.get("SITE_URL", "").strip()
    token_base = os.environ.get("SITE_SYNC_TOKEN", "").strip()
    token_prod = os.environ.get("SITE_SYNC_TOKEN_PRODUCAO", "").strip() or token_base
    token_local = os.environ.get("SITE_SYNC_TOKEN_LOCAL", "").strip() or token_base

    disponiveis = {}
    if url_prod:
        disponiveis["producao"] = (url_prod, token_prod)
    if url_local:
        disponiveis["local"] = (url_local, token_local)
    if url_antiga and not disponiveis:
        disponiveis["padrao"] = (url_antiga, token_base)

    if not disponiveis:
        _sair("Nenhum destino configurado. Defina SITE_URL_PRODUCAO e/ou SITE_URL_LOCAL no .env (veja .env.exemplo).")
    if destino in (None, ""):
        # sem --destino: o que existir (se so houver um); se houver os dois, o publicado
        escolhidos = ["producao"] if "producao" in disponiveis else list(disponiveis)
    elif destino == "ambos":
        escolhidos = [n for n in ("producao", "local") if n in disponiveis]
    else:
        if destino not in disponiveis:
            _sair(f"O destino '{destino}' nao esta configurado no .env (SITE_URL_{destino.upper()}).")
        escolhidos = [destino]
    saida = []
    for nome in escolhidos:
        url, token = disponiveis[nome]
        if not token:
            _sair(f"Falta o token de envio para '{nome}' (SITE_SYNC_TOKEN no .env).")
        saida.append((nome, url, token))
    return saida


def _base_url_cards(gitlab_url, projeto):
    """URL base para os links dos cards (#123 -> essa base + /123)."""
    return f"{gitlab_url.rstrip('/')}/-/issues" if gitlab_url else ""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Le o quadro do GitLab e empurra para o Jardim da Equipe.")
    ap.add_argument("--simular", action="store_true",
                    help="le e mostra o que seria enviado, sem enviar nada")
    ap.add_argument("--listar-usuarios", action="store_true",
                    help="mostra os responsaveis encontrados (para mapear no site) e sai")
    ap.add_argument("--arquivo", metavar="JSON",
                    help="le as issues de um arquivo JSON em vez do GitLab (para testar)")
    ap.add_argument("--destino", choices=("producao", "local", "ambos"),
                    help="para onde enviar: o site publicado, o local ou os dois (veja o .env)")
    args = ap.parse_args(argv)

    carregar_dotenv()        # le o .env (se existir); variaveis do ambiente tem prioridade

    label_doing = _env("GITLAB_LABEL_DOING", gitlab_sync.LABEL_DOING_PADRAO)
    label_review = _env("GITLAB_LABEL_REVIEW", gitlab_sync.LABEL_REVIEW_PADRAO)
    gitlab_url = _env("GITLAB_URL", "")

    usuarios = []
    if args.arquivo:
        issues = _carregar_de_arquivo(args.arquivo)
    else:
        base = _env("GITLAB_URL", obrigatorio=True)
        projeto = _env("GITLAB_PROJECT", obrigatorio=True)
        token = _env("GITLAB_TOKEN", obrigatorio=True)
        issues = ler_issues_do_gitlab(base, projeto, token)
        lidos = ler_membros_do_projeto(base, projeto, token)
        if lidos is None:
            print("Aviso: nao consegui listar os membros do projeto; o usuario de cada pessoa tera de ser "
                  "preenchido na tela Membros.")
        else:
            usuarios = lidos

    cards = gitlab_sync.montar_retrato(issues, label_doing, label_review)

    if args.listar_usuarios:
        responsaveis = sorted({c["usuario"] for c in cards})
        print(f"{len(responsaveis)} responsavel(is) com cards em {label_doing}/{label_review}:")
        for u in responsaveis:
            print(f"  {u}")
        if usuarios:
            print(f"{len(usuarios)} membro(s) do projeto (usuario | nome):")
            for u in usuarios:
                print(f"  {u['username']} | {u['nome']}")
        return 0

    base_cards = _base_url_cards(gitlab_url, _env("GITLAB_PROJECT", ""))
    doing = sum(1 for c in cards if c["coluna"] == "doing")
    review = sum(1 for c in cards if c["coluna"] == "review")
    print(f"Retrato montado: {len(cards)} linha(s) ({doing} em {label_doing}, {review} em {label_review}).")

    if args.simular:
        print("--simular: nao vou enviar nada. Amostra do que seria enviado:")
        for c in cards[:10]:
            print(f"  [{c['coluna']}] {c['usuario']}: {gitlab_sync.citacao(c)}")
        if len(cards) > 10:
            print(f"  ... e mais {len(cards) - 10}.")
        return 0

    if usuarios:
        print(f"Membros do projeto lidos: {len(usuarios)} (o site casa sozinho com as pessoas pelo nome).")
    falhas = 0
    for nome, site_url, sync_token in escolher_destinos(args.destino):
        try:
            resposta = enviar_snapshot(site_url, sync_token, cards, base_cards, usuarios)
        except ErroEnvio as e:
            falhas += 1
            print(f"[{nome}] FALHOU: {e}", file=sys.stderr)
            continue
        extra = ""
        if resposta.get("mapeados"):
            extra = f" e ligou {resposta['mapeados']} pessoa(s) ao usuario do GitLab"
        print(f"[{nome}] Enviado. O site guardou {resposta.get('cards', '?')} card(s){extra}.")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
