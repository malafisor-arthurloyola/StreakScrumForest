"""Gerador de QR Code em Python puro, sem biblioteca externa.

Implementa o suficiente do padrao (ISO/IEC 18004) para codificar uma URL curta:
modo byte, versoes 1 a 10, nivel de correcao de erro M, com Reed-Solomon, os padroes
fixos (finder, timing, alinhamento), informacao de formato/versao e as 8 mascaras com
escolha pela penalidade. A saida e uma matriz booleana ou um SVG.

E uma implementacao enxuta e testavel: `fazer_matriz(texto)` devolve a matriz e o
modulo `svg(texto, ...)` desenha. Usado so para o QR de presenca (texto pequeno).
"""

# ----------------------------------------------------------------- GF(256)
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_gerador(n):
    """Polinomio gerador de grau n."""
    g = [1]
    for i in range(n):
        g2 = [0] * (len(g) + 1)
        for j in range(len(g)):
            g2[j] ^= _gf_mul(g[j], 1)
            g2[j + 1] ^= _gf_mul(g[j], _EXP[i])
        g = g2
    return g


def _rs_residuo(dados, n):
    """Residuo (os n bytes de correcao) dos `dados` com o gerador de grau n."""
    gen = _rs_gerador(n)
    res = list(dados) + [0] * n
    for i in range(len(dados)):
        coef = res[i]
        if coef != 0:
            for j in range(len(gen)):
                res[i + j] ^= _gf_mul(gen[j], coef)
    return res[len(dados):]


# ------------------------------------------------- parametros por versao (nivel M)
# (version): (total_codewords, ec_per_block, [ (num_blocos, data_codewords_por_bloco), ...])
_VERSOES_M = {
    1: (26, 10, [(1, 16)]),
    2: (44, 16, [(1, 28)]),
    3: (70, 26, [(1, 44)]),
    4: (100, 18, [(2, 32)]),
    5: (134, 24, [(2, 43)]),
    6: (172, 16, [(4, 27)]),
    7: (196, 18, [(4, 31)]),
    8: (242, 22, [(2, 38), (2, 39)]),
    9: (292, 22, [(3, 36), (2, 37)]),
    10: (346, 26, [(4, 43), (1, 44)]),
}

# posicoes dos centros dos padroes de alinhamento, por versao
_ALINHAMENTO = {
    1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
    6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50],
}


def _capacidade_dados(version):
    total, ec, blocos = _VERSOES_M[version]
    return sum(nb * dc for nb, dc in blocos)


def _escolher_versao(n_bytes):
    for v in range(1, 11):
        # 4 bits de modo + contador (8 ou 16 bits) + dados
        bits_contador = 8 if v <= 9 else 16
        overhead_bytes = (4 + bits_contador + 7) // 8
        if _capacidade_dados(v) >= n_bytes + overhead_bytes:
            return v
    raise ValueError("Texto grande demais para este gerador de QR (max versao 10 nivel M).")


# ----------------------------------------------------------------- bitstream
def _codificar_dados(texto, version):
    dados = texto.encode("utf-8")
    bits = []

    def push(valor, n):
        for i in range(n - 1, -1, -1):
            bits.append((valor >> i) & 1)

    push(0b0100, 4)  # modo byte
    bits_contador = 8 if version <= 9 else 16
    push(len(dados), bits_contador)
    for b in dados:
        push(b, 8)

    cap_bytes = _capacidade_dados(version)
    cap_bits = cap_bytes * 8
    # terminador
    push(0, min(4, cap_bits - len(bits)))
    # alinha em byte
    while len(bits) % 8 != 0:
        bits.append(0)
    # preenchimento
    preenchimento = [0xEC, 0x11]
    i = 0
    while len(bits) < cap_bits:
        push(preenchimento[i % 2], 8)
        i += 1

    # bits -> codewords
    codewords = []
    for i in range(0, len(bits), 8):
        v = 0
        for b in bits[i:i + 8]:
            v = (v << 1) | b
        codewords.append(v)
    return codewords


def _montar_sequencia(codewords, version):
    """Divide em blocos, calcula EC e intercala dados e EC conforme o padrao."""
    total, ec_per, blocos = _VERSOES_M[version]
    blocos_dados = []
    blocos_ec = []
    pos = 0
    for num_blocos, dc in blocos:
        for _ in range(num_blocos):
            bloco = codewords[pos:pos + dc]
            pos += dc
            blocos_dados.append(bloco)
            blocos_ec.append(_rs_residuo(bloco, ec_per))

    seq = []
    maxd = max(len(b) for b in blocos_dados)
    for i in range(maxd):
        for b in blocos_dados:
            if i < len(b):
                seq.append(b[i])
    maxe = max(len(b) for b in blocos_ec)
    for i in range(maxe):
        for b in blocos_ec:
            if i < len(b):
                seq.append(b[i])
    return seq


# ----------------------------------------------------------------- matriz
def _tamanho(version):
    return version * 4 + 17


def _matriz_base(version):
    n = _tamanho(version)
    mod = [[None] * n for _ in range(n)]
    reservado = [[False] * n for _ in range(n)]

    def finder(r, c):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                rr, cc = r + dr, c + dc
                if 0 <= rr < n and 0 <= cc < n:
                    borda = dr in (0, 6) and 0 <= dc <= 6
                    borda = borda or (dc in (0, 6) and 0 <= dr <= 6)
                    centro = 2 <= dr <= 4 and 2 <= dc <= 4
                    mod[rr][cc] = 1 if (borda or centro) else 0
                    reservado[rr][cc] = True

    finder(0, 0)
    finder(0, n - 7)
    finder(n - 7, 0)

    # separadores ja viram 0 pelo -1..7 acima; timing patterns:
    for i in range(n):
        if mod[6][i] is None:
            mod[6][i] = 1 if i % 2 == 0 else 0
            reservado[6][i] = True
        if mod[i][6] is None:
            mod[i][6] = 1 if i % 2 == 0 else 0
            reservado[i][6] = True

    # padroes de alinhamento
    centros = _ALINHAMENTO[version]
    for r in centros:
        for c in centros:
            if reservado[r][c]:
                continue  # nao sobre finder
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    rr, cc = r + dr, c + dc
                    anel = max(abs(dr), abs(dc))
                    mod[rr][cc] = 1 if anel != 1 else 0
                    reservado[rr][cc] = True

    # modulo escuro fixo
    mod[n - 8][8] = 1
    reservado[n - 8][8] = True

    # reserva area de formato (perto dos finders)
    for i in range(9):
        if not reservado[8][i]:
            reservado[8][i] = True
        if not reservado[i][8]:
            reservado[i][8] = True
    for i in range(8):
        reservado[8][n - 1 - i] = True
        reservado[n - 1 - i][8] = True

    # reserva info de versao (>= 7)
    if version >= 7:
        for i in range(6):
            for j in range(3):
                reservado[i][n - 11 + j] = True
                reservado[n - 11 + j][i] = True

    return mod, reservado, n


def _colocar_dados(mod, reservado, n, seq):
    bits = []
    for cw in seq:
        for i in range(7, -1, -1):
            bits.append((cw >> i) & 1)
    idx = 0
    col = n - 1
    subindo = True
    while col > 0:
        if col == 6:
            col -= 1  # pula a coluna do timing
        linhas = range(n - 1, -1, -1) if subindo else range(n)
        for row in linhas:
            for dc in (0, 1):
                c = col - dc
                if not reservado[row][c]:
                    mod[row][c] = bits[idx] if idx < len(bits) else 0
                    idx += 1
        subindo = not subindo
        col -= 2


_MASCARAS = [
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
]

_FORMATO_M = 0b00  # nivel M


def _bits_formato(mascara):
    dados = (_FORMATO_M << 3) | mascara
    v = dados << 10
    g = 0b10100110111
    for i in range(14, 9, -1):
        if (v >> i) & 1:
            v ^= g << (i - 10)
    bits = ((dados << 10) | v) ^ 0b101010000010010
    return bits


def _aplicar_formato(mod, n, mascara):
    bits = _bits_formato(mascara)
    # bit 14 = MSB ... bit 0 = LSB. seq[0] e o MSB (bit 14).
    seq = [(bits >> (14 - i)) & 1 for i in range(15)]
    # Copia 1: bits 0..14 ao redor do finder superior esquerdo.
    coords1 = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
               (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    for k, (r, c) in enumerate(coords1):
        mod[r][c] = seq[k]
    # Copia 2: bits 0..6 subindo na coluna 8 (de baixo), bits 7..14 na linha 8 (da direita).
    coords2 = [(n - 1, 8), (n - 2, 8), (n - 3, 8), (n - 4, 8), (n - 5, 8), (n - 6, 8), (n - 7, 8),
               (8, n - 8), (8, n - 7), (8, n - 6), (8, n - 5), (8, n - 4), (8, n - 3), (8, n - 2), (8, n - 1)]
    for k, (r, c) in enumerate(coords2):
        mod[r][c] = seq[k]


def _penalidade(mat, n):
    p = 0
    for linha in mat:
        c = 1
        for i in range(1, n):
            if linha[i] == linha[i - 1]:
                c += 1
            else:
                if c >= 5:
                    p += 3 + (c - 5)
                c = 1
        if c >= 5:
            p += 3 + (c - 5)
    for c in range(n):
        cont = 1
        for r in range(1, n):
            if mat[r][c] == mat[r - 1][c]:
                cont += 1
            else:
                if cont >= 5:
                    p += 3 + (cont - 5)
                cont = 1
        if cont >= 5:
            p += 3 + (cont - 5)
    for r in range(n - 1):
        for c in range(n - 1):
            if mat[r][c] == mat[r][c + 1] == mat[r + 1][c] == mat[r + 1][c + 1]:
                p += 3
    escuros = sum(sum(linha) for linha in mat)
    total = n * n
    pct = escuros * 100 // total
    p += (abs(pct - 50) // 5) * 10
    return p


def fazer_matriz(texto):
    """Retorna (matriz booleana, n). True = modulo escuro."""
    dados = texto.encode("utf-8")
    version = _escolher_versao(len(dados))
    codewords = _codificar_dados(texto, version)
    seq = _montar_sequencia(codewords, version)
    mod, reservado, n = _matriz_base(version)
    _colocar_dados(mod, reservado, n, seq)

    melhor = None
    melhor_p = None
    for m in range(8):
        cand = [linha[:] for linha in mod]
        for r in range(n):
            for c in range(n):
                if not reservado[r][c] and _MASCARAS[m](r, c):
                    cand[r][c] ^= 1
        _aplicar_formato(cand, n, m)
        p = _penalidade(cand, n)
        if melhor_p is None or p < melhor_p:
            melhor_p, melhor = p, cand
    return [[bool(v) for v in linha] for linha in melhor], n


def svg(texto, modulo=8, borda=4, cor="#0b1511", fundo="#ffffff"):
    """QR como SVG inline (string). `modulo` = px por modulo; `borda` = modulos de quiet zone."""
    mat, n = fazer_matriz(texto)
    total = (n + borda * 2) * modulo
    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="{total}" '
        f'viewBox="0 0 {total} {total}" role="img" aria-label="QR de presenca" shape-rendering="crispEdges">',
        f'<rect width="{total}" height="{total}" fill="{fundo}"/>',
    ]
    for r in range(n):
        for c in range(n):
            if mat[r][c]:
                x = (c + borda) * modulo
                y = (r + borda) * modulo
                partes.append(f'<rect x="{x}" y="{y}" width="{modulo}" height="{modulo}" fill="{cor}"/>')
    partes.append("</svg>")
    return "".join(partes)
