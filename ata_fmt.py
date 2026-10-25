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
    bloqueios = (ata.get("bloqueios") or "").strip()
    linhas.append(f"{rt['bloqueios']}: {bloqueios or r['none']}")
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
    bloqueios = (ata.get("bloqueios") or "").strip()
    bloqueios_html = etiquetar_cards_html(bloqueios, gitlab_base_url) if bloqueios else r["none"]

    partes = [
        f"<h3>{rt['titulo']} — {_data_br(ata['data'])}</h3>",
        f"<p><b>{rt['scrum']}:</b> {escape(ata.get('relator') or '-')}</p>",
        f"<p><b>{rt['present']}:</b> {present}</p>",
        (f"<p><b>{rt['excused']}:</b> {', '.join(escape(n) for n in ata['excused'])}</p>"
         if ata.get("excused") else ""),
        f"<p><b>{rt['feito']}:</b></p>{lista('feito')}",
        f"<p><b>{rt['planejado']}:</b></p>{lista('planejado')}",
        f"<p><b>{rt['bloqueios']}:</b> {bloqueios_html}</p>",
    ]
    if tipo == "fechamento":
        quadro = r["sim"] if ata.get("quadro_atualizado") else r["nao"]
        partes.append(f"<p><b>{rt['quadro']}:</b> {quadro}</p>")
    return "".join(partes)
