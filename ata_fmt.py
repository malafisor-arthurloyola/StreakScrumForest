"""Formatacao da ata (texto e HTML) no modelo exato, sem Flask e sem banco.

A tela e em portugues, mas a exportacao sai em ingles por padrao (idioma_ata = 'en'),
com opcao 'pt'. Os rotulos sao fixos para bater com o modelo que a professora espera.
Funcoes puras e testaveis.
"""

import re

# rotulos por idioma e por tipo de ata (daily / fechamento)
ROTULOS = {
    "en": {
        "daily": {
            "titulo": "Daily",
            "scrum": "Scrum",
            "present": "Present",
            "excused": "Excused",
            "feito": "Done",
            "planejado": "Doing",
            "review": "Waiting review",
            "bloqueios": "Blockers",
        },
        "fechamento": {
            "titulo": "Day Closing",
            "scrum": "Scrum",
            "present": "Present",
            "excused": "Excused",
            "feito": "Completed today",
            "planejado": "Carried over",
            "bloqueios": "New blockers",
            "quadro": "Board updated",
        },
        "none": "None",
        "sim": "yes",
        "nao": "no",
    },
    "pt": {
        "daily": {
            "titulo": "Daily",
            "scrum": "Scrum",
            "present": "Presentes",
            "excused": "Justificados",
            "feito": "Feito",
            "planejado": "Fazendo",
            "review": "Em revisão",
            "bloqueios": "Impedimentos",
        },
        "fechamento": {
            "titulo": "Fechamento do dia",
            "scrum": "Scrum",
            "present": "Presentes",
            "excused": "Justificados",
            "feito": "Concluído hoje",
            "planejado": "Ficou para depois",
            "bloqueios": "Novos impedimentos",
            "quadro": "Quadro atualizado",
        },
        "none": "Nenhum",
        "sim": "sim",
        "nao": "não",
    },
}

_CARD_RE = re.compile(r"#(\d+)")


def _data_br(data_iso):
    """AAAA-MM-DD -> DD/MM."""
    try:
        _, mes, dia = data_iso.split("-")
        return f"{dia}/{mes}"
    except ValueError:
        return data_iso


def cards_no_texto(texto):
    """Lista de numeros de card (#123) citados no texto, na ordem, sem repetir."""
    vistos = []
    for n in _CARD_RE.findall(texto or ""):
        if n not in vistos:
            vistos.append(n)
    return vistos


def etiquetar_cards_html(texto, gitlab_base_url=""):
    """Escapa o texto e troca #123 por uma etiqueta. Se gitlab_base_url nao for vazio,
    a etiqueta vira link; senao, e so um <span> (sem exigir link)."""
    from html import escape
    base = (gitlab_base_url or "").rstrip("/")

    def troca(m):
        n = m.group(1)
        if base:
            return f'<a class="card-tag" href="{escape(base)}/{n}">#{n}</a>'
        return f'<span class="card-tag">#{n}</span>'

    # escapa primeiro, depois aplica a regex (o # e seguro apos escape)
    return _CARD_RE.sub(troca, escape(texto or ""))


def _linhas_falas(falas, chave):
    """falas: lista de dicts {'nome', 'feito', 'planejado'} na ordem. Retorna as linhas
    '* Nome: texto' para a coluna `chave` (feito/planejado), pulando texto vazio."""
    linhas = []
    for f in falas:
        txt = (f.get(chave) or "").strip()
        if txt:
            linhas.append(f"* {f['nome']}: {txt}")
    return linhas


def _tem_coluna(falas, chave):
    """True se alguma fala tem texto nao-vazio naquela coluna (ex.: 'review')."""
    return any((f.get(chave) or "").strip() for f in falas)


def _linhas_bloqueios(ata):
    """Linhas de impedimento combinando o bloqueio da ata (relator, do dia) com os
    impedimentos PESSOAIS nao vazios. Cada item vira 'texto' (ata) ou 'Nome: texto' (pessoa).
    Lista vazia quando ninguem tem nada -> o chamador escreve 'None'/'Nenhum' (igual ao modelo)."""
    itens = []
    geral = (ata.get("bloqueios") or "").strip()
    if geral:
        itens.append({"nome": None, "texto": geral})
    for b in (ata.get("bloqueios_pessoais") or []):
        txt = (b.get("texto") or "").strip()
        if txt:
            itens.append({"nome": b.get("nome"), "texto": txt})
    return itens


def montar_texto(ata, idioma="en"):
    """Texto puro da ata no modelo exato.

    ata = {
      'tipo': 'daily'|'fechamento', 'data': 'AAAA-MM-DD', 'relator': str|None,
      'present': [nomes], 'falas': [{'nome','feito','planejado'}],
      'bloqueios': str, 'quadro_atualizado': bool (so fechamento),
    }
    """
    idioma = idioma if idioma in ROTULOS else "en"
    r = ROTULOS[idioma]
    tipo = ata["tipo"]
    rt = r[tipo]
    linhas = []
    linhas.append(f"{rt['titulo']} — {_data_br(ata['data'])}")
    linhas.append(f"{rt['scrum']}: {ata.get('relator') or '-'}")
    linhas.append(f"{rt['present']}: {', '.join(ata.get('present') or []) or r['none']}")
    if ata.get("excused"):
        linhas.append(f"{rt['excused']}: {', '.join(ata['excused'])}")
    linhas.append("")
    linhas.append(f"{rt['feito']}:")
    linhas.extend(_linhas_falas(ata.get("falas") or [], "feito"))
    linhas.append("")
    linhas.append(f"{rt['planejado']}:")
    linhas.extend(_linhas_falas(ata.get("falas") or [], "planejado"))
    linhas.append("")
    # "Em revisao" (Waiting review): so aparece na daily E se alguem tiver texto de review.
    # Sem isso, o documento fica identico ao modelo que a professora espera.
    if rt.get("review") and _tem_coluna(ata.get("falas") or [], "review"):
        linhas.append(f"{rt['review']}:")
        linhas.extend(_linhas_falas(ata.get("falas") or [], "review"))
        linhas.append("")
    itens_bloq = _linhas_bloqueios(ata)
    if not itens_bloq:
        linhas.append(f"{rt['bloqueios']}: {r['none']}")
    elif len(itens_bloq) == 1 and itens_bloq[0]["nome"] is None:
        # so o bloqueio geral (do relator): mantem o formato de uma linha, igual ao modelo
        linhas.append(f"{rt['bloqueios']}: {itens_bloq[0]['texto']}")
    else:
        linhas.append(f"{rt['bloqueios']}:")
        for b in itens_bloq:
            prefixo = f"{b['nome']}: " if b["nome"] else ""
            linhas.append(f"* {prefixo}{b['texto']}")
    if tipo == "fechamento":
        quadro = r["sim"] if ata.get("quadro_atualizado") else r["nao"]
        linhas.append(f"{rt['quadro']}: {quadro}")
    return "\n".join(linhas)


def montar_html(ata, idioma="en", gitlab_base_url=""):
    """HTML da ata (para a area de transferencia / pagina imprimivel), mesmo modelo."""
    from html import escape
    idioma = idioma if idioma in ROTULOS else "en"
    r = ROTULOS[idioma]
    tipo = ata["tipo"]
    rt = r[tipo]

    def lista(chave):
        itens = []
        for f in (ata.get("falas") or []):
            txt = (f.get(chave) or "").strip()
            if txt:
                nome = escape(f["nome"])
                corpo = etiquetar_cards_html(txt, gitlab_base_url)
                itens.append(f"<li><b>{nome}:</b> {corpo}</li>")
        return "<ul>" + "".join(itens) + "</ul>" if itens else "<ul></ul>"

    present = ", ".join(escape(n) for n in (ata.get("present") or [])) or r["none"]
    itens_bloq = _linhas_bloqueios(ata)
    if not itens_bloq:
        bloqueios_html = f"<p><b>{rt['bloqueios']}:</b> {r['none']}</p>"
    elif len(itens_bloq) == 1 and itens_bloq[0]["nome"] is None:
        corpo = etiquetar_cards_html(itens_bloq[0]["texto"], gitlab_base_url)
        bloqueios_html = f"<p><b>{rt['bloqueios']}:</b> {corpo}</p>"
    else:
        lis = []
        for b in itens_bloq:
            prefixo = f"<b>{escape(b['nome'])}:</b> " if b["nome"] else ""
            lis.append(f"<li>{prefixo}{etiquetar_cards_html(b['texto'], gitlab_base_url)}</li>")
        bloqueios_html = f"<p><b>{rt['bloqueios']}:</b></p><ul>" + "".join(lis) + "</ul>"

    partes = [
        f"<h3>{rt['titulo']} — {_data_br(ata['data'])}</h3>",
        f"<p><b>{rt['scrum']}:</b> {escape(ata.get('relator') or '-')}</p>",
        f"<p><b>{rt['present']}:</b> {present}</p>",
        (f"<p><b>{rt['excused']}:</b> {', '.join(escape(n) for n in ata['excused'])}</p>"
         if ata.get("excused") else ""),
        f"<p><b>{rt['feito']}:</b></p>{lista('feito')}",
        f"<p><b>{rt['planejado']}:</b></p>{lista('planejado')}",
    ]
    if rt.get("review") and _tem_coluna(ata.get("falas") or [], "review"):
        partes.append(f"<p><b>{rt['review']}:</b></p>{lista('review')}")
    partes.append(bloqueios_html)
    if tipo == "fechamento":
        quadro = r["sim"] if ata.get("quadro_atualizado") else r["nao"]
        partes.append(f"<p><b>{rt['quadro']}:</b> {quadro}</p>")
    return "".join(partes)
