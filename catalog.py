"""Catalogo da loja do jardim e regras de compra/uso (funcoes puras, sem banco).

Tudo aqui e cosmetico: nada muda o crescimento real da planta. O visual de cada item
(paleta, forma da folha, desenho do companheiro) fica em static/style.css e em
templates/_planta.html, ligado pelo id do item.
"""

TIPOS = ("especie", "vaso", "companheiro", "acessorio", "slot")
RARIDADES = ("comum", "rara", "epica", "lendaria")

# onde cada tipo de item pode ser usado
SLOTS_POR_TIPO = {
    "especie": ("especie", "especie_2", "especie_3"),
    "vaso": ("vaso",),
    "companheiro": ("companheiro",),
    "acessorio": ("acessorio",),
}
# slots de planta extra exigem ter comprado o item de slot correspondente
EXIGE_SLOT = {"especie_2": "slot_2", "especie_3": "slot_3"}

ITENS = [
    # plantas (especies)
    {"id": "muda", "tipo": "especie", "nome": "Muda comum", "preco": 0, "raridade": "comum",
     "desc": "A plantinha de sempre, verde e honesta.", "padrao": True},
    {"id": "girassol", "tipo": "especie", "nome": "Girassol", "preco": 40, "raridade": "comum",
     "desc": "Pétalas amarelas e miolo escuro, sempre virado para a luz."},
    {"id": "cacto", "tipo": "especie", "nome": "Cacto", "preco": 50, "raridade": "comum",
     "desc": "Sem folhas, cheio de personalidade. Ganha braços e uma flor rosa."},
    {"id": "cogumelo", "tipo": "especie", "nome": "Cogumelo", "preco": 80, "raridade": "rara",
     "desc": "Chapéu vermelho de bolinhas que cresce a cada presença."},
    {"id": "carnivora", "tipo": "especie", "nome": "Planta carnívora", "preco": 110, "raridade": "epica",
     "desc": "Várias armadilhas de dentes que abrem e fecham devagar."},
    {"id": "jarro", "tipo": "especie", "nome": "Planta-jarro", "preco": 110, "raridade": "epica",
     "desc": "Jarros vermelhos pendurados nas pontas das folhas, como na floresta tropical."},
    {"id": "samambaia", "tipo": "especie", "nome": "Samambaia", "preco": 40, "raridade": "comum",
     "desc": "Folhas finas e fundas, de quem gosta de sombra.", "folha": "p-folha-fina"},
    {"id": "lavanda", "tipo": "especie", "nome": "Lavanda", "preco": 50, "raridade": "comum",
     "desc": "Florzinhas roxas e um cheirinho que você quase sente.", "folha": "p-folha-fina"},
    {"id": "cerejeira", "tipo": "especie", "nome": "Cerejeira", "preco": 70, "raridade": "rara",
     "desc": "Flores rosadas que parecem confete."},
    {"id": "bambu", "tipo": "especie", "nome": "Bambu", "preco": 70, "raridade": "rara",
     "desc": "Caule grosso e folhas compridas, crescimento firme.", "folha": "p-folha-fina"},
    {"id": "bonsai", "tipo": "especie", "nome": "Bonsai", "preco": 90, "raridade": "rara",
     "desc": "Folhas pequenas e redondas, paciência em forma de planta.", "folha": "p-folha-redonda"},
    {"id": "jabuticabeira", "tipo": "especie", "nome": "Jabuticabeira", "preco": 90, "raridade": "rara",
     "desc": "Flores brancas e frutos escuros que nascem no tronco.", "folha": "p-folha-redonda"},
    {"id": "ipe", "tipo": "especie", "nome": "Ipê amarelo", "preco": 120, "raridade": "epica",
     "desc": "A cara do Brasil: uma chuva de flores douradas."},
    {"id": "baoba", "tipo": "especie", "nome": "Baobá", "preco": 120, "raridade": "lendaria",
     "desc": "Só quem já viu uma planta florescer pode plantar esta.",
     "req": {"floresceu": True}},

    # vasos
    {"id": "terracota", "tipo": "vaso", "nome": "Terracota", "preco": 0, "raridade": "comum",
     "desc": "O clássico.", "padrao": True},
    {"id": "lata", "tipo": "vaso", "nome": "Lata reaproveitada", "preco": 12, "raridade": "comum",
     "desc": "Sustentável e cheia de personalidade."},
    {"id": "azul", "tipo": "vaso", "nome": "Cerâmica azul", "preco": 16, "raridade": "comum",
     "desc": "Azul de azulejo português."},
    {"id": "xicara", "tipo": "vaso", "nome": "Xícara de café", "preco": 20, "raridade": "comum",
     "desc": "Porque dev também planta no que tem à mão."},
    {"id": "pixel", "tipo": "vaso", "nome": "Vaso roxo", "preco": 24, "raridade": "rara",
     "desc": "Um respiro de cor no meio do verde."},
    {"id": "dourado", "tipo": "vaso", "nome": "Vaso dourado", "preco": 30, "raridade": "rara",
     "desc": "Para plantas que já se sentem estrelas."},

    # companheiros do vaso
    {"id": "joaninha", "tipo": "companheiro", "nome": "Joaninha", "preco": 20, "raridade": "comum",
     "desc": "Passeia pela borda do vaso."},
    {"id": "borboleta", "tipo": "companheiro", "nome": "Borboleta", "preco": 24, "raridade": "comum",
     "desc": "Voa em volta da planta o dia todo."},
    {"id": "vagalume", "tipo": "companheiro", "nome": "Vagalume", "preco": 30, "raridade": "rara",
     "desc": "Uma luzinha que rodeia a planta."},
    {"id": "passarinho", "tipo": "companheiro", "nome": "Passarinho", "preco": 40, "raridade": "rara",
     "desc": "Pousa ao lado do vaso e fica de vigia."},
    {"id": "gato", "tipo": "companheiro", "nome": "Gato dorminhoco", "preco": 50, "raridade": "epica",
     "desc": "Dorme enroladinho junto ao vaso."},

    # acessorios do vaso
    {"id": "laco", "tipo": "acessorio", "nome": "Laço", "preco": 16, "raridade": "comum",
     "desc": "Um laço rosa na borda do vaso."},
    {"id": "oculos", "tipo": "acessorio", "nome": "Óculos", "preco": 20, "raridade": "comum",
     "desc": "O vaso fica com cara de quem leu a documentação."},
    {"id": "chapeu", "tipo": "acessorio", "nome": "Chapéu de palha", "preco": 24, "raridade": "comum",
     "desc": "Proteção solar para o vaso."},

    # acessorio exclusivo: nao esta a venda; so quem foi Fundador pode usar
    {"id": "selo_fundador", "tipo": "acessorio", "nome": "Selo Fundador", "preco": 0,
     "raridade": "lendaria", "exclusivo": True,
     "desc": "Para quem esteve no jardim desde o começo. Não está à venda."},

    # plantas extras no canteiro
    {"id": "slot_2", "tipo": "slot", "nome": "Segunda plantinha", "preco": 60, "raridade": "rara",
     "desc": "Uma plantinha companheira ao lado da principal. Ela cresce junto, um pouco menor."},
    {"id": "slot_3", "tipo": "slot", "nome": "Terceira plantinha", "preco": 110, "raridade": "epica",
     "desc": "Mais uma para o canteiro.", "req": {"item": "slot_2"}},
]

_POR_ID = {i["id"]: i for i in ITENS}


def item(item_id):
    return _POR_ID.get(item_id)


def itens_por_tipo(tipo):
    return [i for i in ITENS if i["tipo"] == tipo]


def padrao(tipo):
    for i in ITENS:
        if i["tipo"] == tipo and i.get("padrao"):
            return i
    return None


def _e_padrao(item_id):
    i = item(item_id)
    return bool(i and i.get("padrao"))


def pode_comprar(item_id, saldo, possui, floresceu):
    """Retorna (ok, motivo). possui = conjunto de ids ja comprados (ativos)."""
    i = item(item_id)
    if i is None:
        return False, "Item desconhecido."
    if i.get("exclusivo"):
        return False, "Item exclusivo: não está à venda."
    if i.get("padrao") or i["preco"] == 0:
        return False, "Este item já é seu."
    if item_id in possui:
        return False, "Você já tem este item."
    req = i.get("req", {})
    if req.get("floresceu") and not floresceu:
        return False, "Só desbloqueia depois de uma planta florescer."
    exigido = req.get("item")
    if exigido and exigido not in possui:
        return False, f"Antes, compre: {item(exigido)['nome']}."
    if saldo < i["preco"]:
        falta = i["preco"] - saldo
        return False, f"Faltam {falta} sementes."
    return True, ""


def pode_equipar(item_id, slot, possui, fundador=False):
    """Retorna (ok, motivo). Itens padrao podem ser usados sempre. Itens exclusivos
    (como o Selo Fundador) so podem ser usados por quem tem direito (fundador=True)."""
    i = item(item_id)
    if i is None:
        return False, "Item desconhecido."
    slots_validos = SLOTS_POR_TIPO.get(i["tipo"])
    if not slots_validos:
        return False, "Este item não é para usar no canteiro."
    if slot not in slots_validos:
        return False, "Este item não cabe nesse lugar."
    exigido = EXIGE_SLOT.get(slot)
    if exigido and exigido not in possui:
        return False, f"Antes, compre: {item(exigido)['nome']}."
    if i.get("exclusivo"):
        if not fundador:
            return False, "Selo exclusivo de quem foi Fundador."
        return True, ""
    if not _e_padrao(item_id) and item_id not in possui:
        return False, "Você ainda não tem este item."
    return True, ""


def _folha(especie_id):
    return (item(especie_id) or {}).get("folha", "p-folha")


def _valido(item_id, slot, possui, fundador=False):
    return bool(item_id) and pode_equipar(item_id, slot, possui, fundador)[0]


def montar_visual(possui, equipados, fundador=False):
    """Resolve o que aparece no canteiro de um membro.

    Item equipado que nao e mais valido (compra desfeita, ou selo exclusivo de quem
    nao e fundador) e ignorado, voltando ao padrao do tipo.
    """
    esp = equipados.get("especie")
    if not _valido(esp, "especie", possui, fundador):
        esp = padrao("especie")["id"]
    vaso = equipados.get("vaso")
    if not _valido(vaso, "vaso", possui, fundador):
        vaso = padrao("vaso")["id"]
    comp = equipados.get("companheiro")
    if not _valido(comp, "companheiro", possui, fundador):
        comp = None
    acess = equipados.get("acessorio")
    if not _valido(acess, "acessorio", possui, fundador):
        acess = None

    extras = []
    for n in (2, 3):
        if f"slot_{n}" not in possui:
            continue
        e = equipados.get(f"especie_{n}")
        if not _valido(e, f"especie_{n}", possui, fundador):
            e = padrao("especie")["id"]
        extras.append({"slot": n, "especie": e, "folha": _folha(e)})

    # Especies compradas que nao estao no vaso principal nem nas extras: crescem soltas na terra do
    # canteiro do mapa, entao cada planta nova comprada aparece ali, mesmo sem slot.
    em_uso = {esp} | {e["especie"] for e in extras}
    colecao = [
        {"especie": i["id"], "folha": _folha(i["id"])}
        for i in ITENS
        if i["tipo"] == "especie" and i["id"] in possui and i["id"] not in em_uso and not _e_padrao(i["id"])
    ]

    return {
        "especie": esp, "folha": _folha(esp), "vaso": vaso,
        "companheiro": comp, "acessorio": acess, "extras": extras, "colecao": colecao,
    }
