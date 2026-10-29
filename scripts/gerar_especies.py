"""Gera as espécies desenhadas em SVG de templates/_especies.html (as 8 redesenhadas a partir de
fotos de referência: girassol, cogumelo, carnívora, samambaia, cerejeira, jabuticabeira, ipê, baobá).

Uso: python scripts/gerar_especies.py

Por que existe: cada estágio (1 a 10) é uma camada <g class="cam" data-min/data-max> que o JS
(aplicarEstagio em static/app.js) só liga e desliga. Gerar por código deixa as proporções
consistentes (altura do caule, tamanho da copa, espiral de sementes) e fácil de ajustar num lugar só.
Cacto, lavanda, bambu e bonsai continuam escritos à mão no template e não são tocados.
"""
import math
import re
from pathlib import Path

ALVO = Path(__file__).resolve().parent.parent / "templates" / "_especies.html"


def f(x):
    s = f"{x:.1f}"
    return s[:-2] if s.endswith(".0") else s


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(x, a, b):
    return max(a, min(b, x))


def rng(seed):
    estado = [seed & 0xFFFFFFFF]

    def r():
        estado[0] = (estado[0] + 0x6D2B79F5) & 0xFFFFFFFF
        t = estado[0]
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    return r


def snap(k, interno):
    """Camada que só aparece exatamente no estágio k."""
    return '<g class="cam{{ \' on\' if s == %d }}" data-min="%d" data-max="%d">%s</g>\n' % (k, k, k, interno)


def acum(k, interno):
    """Camada que aparece do estágio k em diante."""
    return '<g class="cam{{ \' on\' if s >= %d }}" data-min="%d">%s</g>\n' % (k, k, interno)


def frutos(posicoes, r=2):
    itens = ""
    for i, (x, y) in enumerate(posicoes, 1):
        itens += '<circle class="fr{{ \' on\' if fr >= %d }}" data-fruto="%d" cx="%s" cy="%s" r="%s"/>' % (i, i, f(x), f(y), f(r))
    return '<g class="frutos">%s</g>\n' % itens


def pontos(lista):
    """Bolinhas (x, y, raio, cor) agrupadas por cor e tamanho em poucos <path> (ponto = 'h0' com
    traco redondo): a mesma imagem com uma fracao do HTML."""
    grupos = {}
    for x, y, r, cor in lista:
        chave = (cor, round(r * 2.5) / 2.5)
        grupos.setdefault(chave, []).append("M%s %sh0" % (f(x), f(y)))
    return "".join('<path d="%s" stroke="%s" stroke-width="%s" stroke-linecap="round" fill="none"/>' % ("".join(v), c, f(2 * r))
                   for (c, r), v in grupos.items())


def brilho(x, y, r, cls="eo"):
    return ('<path class="%s" d="M%s %sL%s %sL%s %sL%s %sL%s %sL%s %sL%s %sL%s %sZ" transform="translate(%s %s)"/>'
            % (cls, "0", f(-r), f(r * .28), f(-r * .28), f(r), "0", f(r * .28), f(r * .28), "0", f(r),
               f(-r * .28), f(r * .28), f(-r), "0", f(-r * .28), f(-r * .28), f(x), f(y)))


# ------------------------------------------------------------------ girassol
def girassol(est):
    t = est / 10
    alt = lerp(12, 70, t ** .85)
    topo = 117 - alt
    curva = lerp(0, 2.5, t)
    h = '<path d="M60 117Q%s %s 60 %s" stroke="#4b8f3f" stroke-width="%s" stroke-linecap="round" fill="none"/>' % (
        f(60 - curva), f(117 - alt / 2), f(topo), f(lerp(2.4, 3.6, t)))
    h += '<path d="M60.9 117Q%s %s 60.9 %s" stroke="#8cc472" stroke-width=".8" stroke-linecap="round" fill="none" opacity=".7"/>' % (
        f(60.9 - curva), f(117 - alt / 2), f(topo + 2))

    def folha(yrel, lado, esc, emin):
        if est < emin:
            return ""
        y = 117 - alt * yrel
        sc = esc * clamp((est - emin + 1) / 3, .35, 1)
        cab = 12 * sc
        x2, y2 = 60 + lado * cab, y - 6 * sc
        ang = -22 if lado > 0 else -158
        g = '<path d="M60 %s Q%s %s %s %s" stroke="#7fb36a" stroke-width="1.5" stroke-linecap="round" fill="none"/>' % (
            f(y), f(60 + lado * cab * .4), f(y - 8 * sc), f(x2), f(y2))
        g += ('<g transform="translate(%s %s) rotate(%d) scale(%s)">'
              '<path d="M0 0C4-12 24-13 32 0C24 12 4 11 0 0Z" fill="#5c9c46"/>'
              '<path d="M0 0C4-12 24-13 32 0C20-2 8-3 0 0Z" fill="#78b85a" opacity=".7"/>'
              '<path d="M1 0Q16-1 30 0" stroke="#3f7a35" stroke-width=".9" fill="none"/>'
              '<path d="M10 0L16-6M10 0L16 6M19 0L24-4.5M19 0L24 4.5" stroke="#3f7a35" stroke-width=".6" fill="none" opacity=".8"/></g>'
              % (f(x2), f(y2), ang, f(sc * .95)))
        return g
    h += folha(.30, -1, 1, 2) + folha(.52, 1, 1.05, 3) + folha(.70, -1, .8, 5)
    if est >= 6:
        abre = clamp((est - 6) / 4, 0, 1)
        R = lerp(6, 28, abre)
        cy = topo - R * .35
        h += '<g transform="translate(60 %s) rotate(-5)">' % f(cy)
        if est <= 7:
            h += '<ellipse rx="%s" ry="%s" fill="#5f9d44"/>' % (f(R * .95), f(R * .85))
            for i in range(9):
                h += '<path d="M0 %sL%s %sL%s %sZ" fill="#4b8a3a" transform="rotate(%d)"/>' % (
                    f(-R * .3), f(-R * .22), f(-R * 1.1), f(R * .22), f(-R * 1.1), i * 40)
            if est == 7:
                h += '<ellipse cy="%s" rx="%s" ry="%s" fill="#f6c33b"/>' % (f(-R * .9), f(R * .4), f(R * .3))
        else:
            n = 22
            passo = 360 / n
            for a in range(n):
                h += '<use href="#p-petala" fill="#f2a81d" transform="rotate(%s) scale(%s %s)"/>' % (f(a * passo), f(R * .5), f(R))
            for a in range(n):
                h += '<use href="#p-petala" fill="#fbc92e" transform="rotate(%s) scale(%s %s)"/>' % (f(a * passo + passo / 2), f(R * .46), f(R * .88))
            d = R * .5
            h += '<circle r="%s" fill="#6a3d1a"/><circle r="%s" fill="#7a4a22"/>' % (f(d), f(d * .94))
            pts = []
            for k in range(1, 70):
                rr = d * .9 * math.sqrt(k / 70)
                th = k * 2.39996
                pts.append((rr * math.cos(th), rr * math.sin(th), lerp(.5, 1.0, k / 70), "#4b2a12" if k % 3 else "#9a6a30"))
            h += pontos(pts)
            h += '<circle r="%s" fill="#8c8a2f"/><circle r="%s" fill="#a8a43a"/>' % (f(d * .3), f(d * .2))
        h += '</g>'
    if est == 10:
        h += brilho(86, 22, 4) + brilho(33, 30, 3) + brilho(80, 52, 2.4)
    return h


# ------------------------------------------------------------------ copas de flor (cerejeira e ipê)
def arvore(est, cfg):
    t = est / 10
    r = rng(cfg["seed"])
    alt = lerp(14, cfg["alt"], t ** .8)
    topo = 117 - alt
    lar = lerp(1.8, cfg["lar"], t)
    deriva = lerp(0, 3, t)
    pontas = [(60 + deriva, topo)]
    galhos = ""
    for b in cfg["ramos"]:
        if est < b["min"]:
            continue
        c = clamp((est - b["min"] + 1) / 3, .3, 1)
        x0 = 60 + 2 * math.sin(b["y"] * 4)
        y0 = 117 - alt * b["y"]
        x1, y1 = x0 + b["dx"] * c, y0 + b["dy"] * c
        galhos += '<path d="M%s %s Q%s %s %s %s" stroke="%s" stroke-width="%s" stroke-linecap="round" fill="none"/>' % (
            f(x0), f(y0), f(x0 + b["dx"] * .3 * c), f(y0 + b["dy"] * .8 * c), f(x1), f(y1), cfg["tronco"], f(lerp(1, 2.6, t)))
        pontas.append((x1, y1))
    h = ('<path d="M60 117C57 %s 63 %s %s %s" stroke="%s" stroke-width="%s" stroke-linecap="round" fill="none"/>'
         '<path d="M58.8 117C56 %s 62 %s %s %s" stroke="%s" stroke-width="%s" stroke-linecap="round" fill="none" opacity=".7"/>'
         % (f(117 - alt * .3), f(117 - alt * .6), f(60 + deriva), f(topo), cfg["tronco"], f(lar),
            f(117 - alt * .3), f(117 - alt * .6), f(59 + deriva), f(topo), cfg["tronco2"], f(lar * .3)))
    h += galhos
    dens = 0 if est <= 2 else (est - 2) / 8
    copa = []
    for i, (px, py) in enumerate(pontas):
        raio = lerp(3, cfg["raio"], dens) * (1.2 if i == 0 else 1)
        n = round(lerp(2, cfg["n"], dens))
        for _ in range(n):
            ang = r() * 6.283
            dist = r() * raio
            x = px + math.cos(ang) * dist
            y = py - raio * .2 + math.sin(ang) * dist * .7
            copa.append((x, y, lerp(1.6, cfg["bolha"], dens) * (.7 + r() * .6), cfg["paleta"][int(r() * 3)]))
    h += pontos(copa)
    if est >= 8:
        if cfg.get("tapete"):
            h = '<ellipse cx="60" cy="116" rx="23" ry="2.4" fill="%s" opacity=".85"/>' % cfg["paleta"][1] + h
        for q in range(cfg["petalas"]):
            h += ('<ellipse class="petala-cai" cx="%d" cy="%d" rx="2.2" ry="1.3" fill="%s" style="animation-delay:%ss"/>'
                  % (30 + q * 11, 30 + (q % 3) * 6, cfg["petala"], f(-q * 1.1)))
    if est == 10:
        h += brilho(92, 30, 3.6) + brilho(30, 40, 3)
    return h


CEREJEIRA = dict(
    seed=7, alt=60, lar=6.2, tronco="#3f2b22", tronco2="#5a4033", raio=25, n=18, bolha=5.4,
    paleta=["#ffd3e2", "#ffb6cf", "#f58db0", "#fff0f5"], petala="#ffc6da", petalas=6, tapete=False,
    ramos=[dict(y=.45, dx=-30, dy=-18, min=3), dict(y=.55, dx=32, dy=-22, min=3), dict(y=.72, dx=-16, dy=-16, min=5),
           dict(y=.78, dx=18, dy=-14, min=5), dict(y=.9, dx=-8, dy=-12, min=7), dict(y=.95, dx=10, dy=-10, min=7)],
)
IPE = dict(
    seed=21, alt=62, lar=5.2, tronco="#4a3526", tronco2="#6a4d38", raio=24, n=20, bolha=4.8,
    paleta=["#ffe14a", "#ffd21f", "#ffbe18", "#fff3a0"], petala="#ffd84a", petalas=4, tapete=True,
    ramos=[dict(y=.42, dx=-34, dy=-12, min=3), dict(y=.5, dx=36, dy=-14, min=3), dict(y=.66, dx=-24, dy=-14, min=5),
           dict(y=.72, dx=28, dy=-12, min=5), dict(y=.88, dx=-12, dy=-10, min=7), dict(y=.92, dx=14, dy=-10, min=7)],
)


# ------------------------------------------------------------------ cogumelo (amanita)
SPOTS = [(-.55, .5), (.1, .72), (.55, .45), (-.2, .3), (.35, .15), (-.7, .18), (.72, .2), (0, .5), (-.4, .75)]


def mini_cogumelo(x, base, alt, rx):
    ry = rx * .6
    top = base - alt
    return ('<path d="M%s %s L%s %s L%s %s L%s %s Z" fill="#f1e4cc"/>' % (f(x - 1.4), f(base), f(x - .9), f(top), f(x + .9), f(top), f(x + 1.4), f(base)) +
            '<ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="#b99aa3"/>' % (f(x), f(top), f(rx * .95), f(ry * .3)) +
            '<path d="M%s %s C%s %s %s %s %s %s Z" fill="#e5603a"/>' % (f(x - rx), f(top), f(x - rx), f(top - ry * 1.5), f(x + rx), f(top - ry * 1.5), f(x + rx), f(top)) +
            '<ellipse cx="%s" cy="%s" rx="1.1" ry=".6" fill="#fff1d6"/>' % (f(x + rx * .3), f(top - ry * .7)))


def cogumelo(est):
    t = est / 10
    if est == 1:
        return ('<ellipse cx="60" cy="111" rx="5.6" ry="7" fill="#f3ead6"/>'
                '<ellipse cx="62" cy="112" rx="3.2" ry="5.4" fill="#d9c9a6" opacity=".55"/>'
                '<ellipse cx="58" cy="108" rx="1.4" ry="2.4" fill="#fffaf0" opacity=".8"/>')
    h = lerp(9, 38, (est - 2) / 8)
    top = 117 - h
    wb, wt = lerp(3.8, 9, t), lerp(2.8, 5.6, t)
    o = ('<path d="M%s 117C%s %s %s %s %s %sL%s %sC%s %s %s %s %s 117Z" fill="#f1e4cc"/>'
         % (f(60 - wb), f(60 - wb * .9), f(117 - h * .5), f(60 - wt * 1.1), f(top + 4), f(60 - wt), f(top),
            f(60 + wt), f(top), f(60 + wt * 1.1), f(top + 4), f(60 + wb * .9), f(117 - h * .5), f(60 + wb)))
    o += ('<path d="M%s 117C%s %s %s %s %s %sL%s %sC%s %s %s %s %s 117Z" fill="#c9ae85" opacity=".4"/>'
          % (f(60 + wb * .25), f(60 + wb * .3), f(117 - h * .5), f(60 + wt * .4), f(top + 4), f(60 + wt * .3), f(top),
             f(60 + wt), f(top), f(60 + wt * 1.1), f(top + 4), f(60 + wb * .9), f(117 - h * .5), f(60 + wb)))
    o += '<path d="M%s %sL%s %s" stroke="#fffaf0" stroke-width="1" stroke-linecap="round" opacity=".6"/>' % (f(60 - wt * .5), f(top + 4), f(60 - wb * .55), f(114))
    if est >= 7:
        y = top + h * .3
        o += ('<path d="M%s %sC%s %s %s %s %s %sC%s %s %s %s %s %sZ" fill="#f8eed8"/>'
              % (f(60 - wt * 1.15), f(y), f(60 - wt * 2.1), f(y + 1), f(60 - wt * 2.3), f(y + 6), f(60 - wt * 1.5), f(y + 6.5),
                 f(60), f(y + 8), f(60 + wt * 1.4), f(y + 6.5), f(60 + wt * 1.15), f(y)))
    u = (est - 1) / 9
    rx, ry = lerp(5, 31, u), lerp(4, 17, u)
    o += '<ellipse cx="60" cy="%s" rx="%s" ry="%s" fill="#b99aa3"/>' % (f(top), f(rx * .97), f(ry * .27))
    for a in range(-6, 7):
        o += '<path d="M60 %sL%s %s" stroke="#8f6f7e" stroke-width=".4" opacity=".7"/>' % (f(top), f(60 + a * rx * .15), f(top + ry * .26 * math.sqrt(max(0, 1 - (a / 6.5) ** 2))))
    o += ('<path d="M%s %sC%s %s %s %s %s %sZ" fill="#e5483b" stroke="#a82c22" stroke-width=".9"/>'
          % (f(60 - rx), f(top), f(60 - rx), f(top - ry * 1.35), f(60 + rx), f(top - ry * 1.35), f(60 + rx), f(top)))
    o += '<ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="#f2705f" opacity=".45"/>' % (f(60 - rx * .35), f(top - ry * .75), f(rx * .38), f(ry * .2))
    if est >= 3:
        for i, (a, b) in enumerate(SPOTS[:min(9, est)]):
            o += '<ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="#fff1d6"/>' % (
                f(60 + rx * a * .8), f(top - ry * b * 1.05), f(lerp(1.3, 3.6, t)), f(lerp(.8, 1.9, t)))
    if est >= 8:
        o += mini_cogumelo(86, 115, 11, 6.5)
    if est >= 9:
        o += mini_cogumelo(34, 115, 8, 5.2)
    if est == 10:
        o += brilho(93, 44, 3.6) + brilho(27, 56, 3)
    return o


# ------------------------------------------------------------------ carnívora (jarro, Nepenthes)
FOLHAS_CARN = [(.12, 1, -16, 1, .8), (.14, -1, -164, 2, .8), (.36, 1, -30, 3, 1.0), (.38, -1, -150, 3, 1.0),
               (.62, 1, -12, 5, 1.1), (.64, -1, -168, 6, 1.1), (.86, 1, -42, 7, .95), (.88, -1, -138, 8, .95)]
JARROS = [(2, 5), (3, 7), (4, 9)]      # (indice da folha, estagio minimo)


def jarro(x, y, s):
    w, hgt = 10 * s, 24 * s
    corpo = ('M%s %sC%s %s %s %s %s %sC%s %s %s %s %s %sZ'
             % (f(x - w * .62), f(y), f(x - w * 1.15), f(y + hgt * .35), f(x - w * .95), f(y + hgt * .95), f(x), f(y + hgt),
                f(x + w * .95), f(y + hgt * .95), f(x + w * 1.15), f(y + hgt * .35), f(x + w * .62), f(y)))
    r = rng(int(x * 13 + y))
    o = '<path d="%s" fill="#a9b84e"/><path d="%s" fill="#c23a35" opacity=".6"/>' % (corpo, corpo)
    o += '<path d="M%s %sL%s %s" stroke="#e3e58a" stroke-width="%s" opacity=".6" stroke-linecap="round"/>' % (
        f(x - w * .5), f(y + hgt * .25), f(x - w * .4), f(y + hgt * .75), f(max(.8, w * .22)))
    for _ in range(6):
        o += '<circle cx="%s" cy="%s" r=".7" fill="#7a1f1f"/>' % (f(x + (r() - .3) * w * 1.1), f(y + hgt * (.25 + r() * .6)))
    o += '<ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="#7a1f1f" stroke="#d9473a" stroke-width="1.1"/>' % (f(x), f(y), f(w * .72), f(2.3 * s))
    o += '<ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="#d9473a" transform="rotate(-24 %s %s)"/>' % (f(x + w * .55), f(y - 2.6 * s), f(w * .6), f(1.8 * s), f(x + w * .55), f(y - 2.6 * s))
    return o


def carnivora(est):
    t = est / 10
    alt = lerp(10, 54, t ** .9)
    o = '<path d="M60 117Q%s %s 60 %s" stroke="#2f6f3a" stroke-width="%s" stroke-linecap="round" fill="none"/>' % (
        f(57 + 2 * t), f(117 - alt / 2), f(117 - alt), f(lerp(2, 3.2, t)))
    pontas = {}
    for i, (yf, lado, ang, emin, esc) in enumerate(FOLHAS_CARN):
        if est < emin:
            continue
        c = clamp((est - emin + 1) / 3, .35, 1)
        L = 28 * esc * c
        x0, y0 = 60 + lado * 1.2, 117 - alt * yf
        wl = L * .17
        o += ('<g transform="translate(%s %s) rotate(%d)">'
              '<path d="M0 0C%s %s %s %s %s 0C%s %s %s %s 0 0Z" fill="#2f8a4a"/>'
              '<path d="M0 0C%s %s %s %s %s 0C%s -1 %s -1 0 0Z" fill="#4bb36a" opacity=".7"/>'
              '<path d="M1 0L%s 0" stroke="#d8f0a8" stroke-width=".8" opacity=".85"/></g>'
              % (f(x0), f(y0), ang, f(L * .3), f(-wl), f(L * .75), f(-wl * 1.1), f(L), f(L * .75), f(wl * 1.1), f(L * .3), f(wl),
                 f(L * .3), f(-wl), f(L * .75), f(-wl * 1.1), f(L), f(L * .5), f(L * .2), f(L - 1)))
        pontas[i] = (x0 + L * math.cos(math.radians(ang)), y0 + L * math.sin(math.radians(ang)), c)
    for idx, emin in JARROS:
        if est >= emin and idx in pontas:
            tx, ty, _ = pontas[idx]
            sp = clamp((est - emin + 1) / 3, .45, 1)
            o += '<path d="M%s %sQ%s %s %s %s" stroke="#4a8a3a" stroke-width=".9" fill="none"/>' % (f(tx), f(ty), f(tx + 2), f(ty + 6), f(tx + 1), f(ty + 11 * sp))
            o += jarro(tx + 1, ty + 11 * sp, sp)
    if est == 10:
        o += brilho(26, 40, 3) + brilho(94, 36, 3.4)
    return o


# ------------------------------------------------------------------ samambaia (Boston, folhas arqueadas)
FRONDES = [(0, 22, 0), (-.7, 30, 6), (.7, 32, 8), (-.95, 42, 14), (.95, 44, 16), (-.4, 46, 12), (.4, 48, 12), (-1, 54, 24), (1, 56, 26), (0, 50, 10)]


def fronde(dirx, L, queda, estagio_nasc, est):
    # curva quadratica do centro do vaso para fora; cai (queda) na ponta
    x0, y0 = 60, 114
    cx, cy = 60 + dirx * L * .45, 114 - L * .85
    ex, ey = 60 + dirx * L * .95, 114 - L * .45 + queda
    o = '<path class="fronde-haste" d="M%s %sQ%s %s %s %s"/>' % (f(x0), f(y0), f(cx), f(cy), f(ex), f(ey))
    n = max(5, int(L / 3.2))
    for k in range(1, n + 1):
        u = k / n * .97
        px = (1 - u) ** 2 * x0 + 2 * (1 - u) * u * cx + u * u * ex
        py = (1 - u) ** 2 * y0 + 2 * (1 - u) * u * cy + u * u * ey
        tx = 2 * (1 - u) * (cx - x0) + 2 * u * (ex - cx)
        ty = 2 * (1 - u) * (cy - y0) + 2 * u * (ey - cy)
        ang = math.degrees(math.atan2(ty, tx))
        esc = .36 * (1 - u * .65)
        for lado, cls in ((1, "ea"), (-1, "eb")):
            o += '<use href="#p-folha" class="%s" transform="translate(%s %s) rotate(%s) scale(%s)"/>' % (
                cls, f(px), f(py), f(ang + lado * (58 - u * 18)), f(esc))
    return o


# ------------------------------------------------------------------ jabuticabeira
TRONCOS = [(60, 0, 1.0, 1, 3.4), (54, -9, .82, 3, 2.5), (66, 10, .88, 4, 2.6), (57, -17, .62, 6, 1.7), (64, 17, .66, 6, 1.7)]


def jabuticabeira(est):
    t = est / 10
    r = rng(11)
    alt = lerp(14, 66, t ** .85)
    h = ""
    dens = 0 if est <= 2 else (est - 2) / 8
    base_troncos = []
    for xb, dx, fr_, emin, w in TRONCOS:
        if est < emin:
            continue
        c = clamp((est - emin + 1) / 3, .35, 1)
        topo = 117 - alt * fr_ * c
        xt = xb + dx * c
        base_troncos.append((xb, xt, topo, w))
        h += '<path d="M%s 117Q%s %s %s %s" stroke="#b88a63" stroke-width="%s" stroke-linecap="round" fill="none"/>' % (
            f(xb), f(xb + dx * .1), f((117 + topo) / 2), f(xt), f(topo), f(w * lerp(.7, 1, t)))
        for _ in range(4):
            u = .15 + r() * .75
            px = xb + (xt - xb) * u * u
            py = 117 + (topo - 117) * u
            h += '<ellipse cx="%s" cy="%s" rx="%s" ry="%s" fill="%s" opacity=".8"/>' % (
                f(px), f(py), f(w * .45), f(w * .8), "#e2c3a0" if r() > .4 else "#8a5a3a")
    for _, xt, topo, w in base_troncos:
        n = round(lerp(2, 8, dens))
        raio = lerp(3, 12, dens)
        folhas = []
        for _ in range(n):
            ang, dist = r() * 6.283, r() * raio
            folhas.append((xt + math.cos(ang) * dist, topo - raio * .1 + math.sin(ang) * dist * .75, lerp(1.6, 4.4, dens) * (.7 + r() * .6),
                           ["#3f9f5f", "#58b872", "#2d8049"][int(r() * 3)]))
        h += pontos(folhas)
    if est in (6, 7):
        for xb, xt, topo, w in base_troncos:
            for _ in range(5):
                u = .2 + r() * .7
                px, py = xb + (xt - xb) * u * u, 117 + (topo - 117) * u
                h += '<circle cx="%s" cy="%s" r="1.3" fill="#fff"/><circle cx="%s" cy="%s" r=".5" fill="#ffe27a"/>' % (f(px + w * .4), f(py), f(px + w * .4), f(py))
    if est >= 8:
        n = round(lerp(8, 46, (est - 7) / 3))
        cor = "#6a4a82" if est == 8 else "#20122a"
        bagas, brilhos = [], []
        for _ in range(n):
            tr = base_troncos[int(r() * len(base_troncos))]
            u = .12 + r() * .8
            px, py = tr[0] + (tr[1] - tr[0]) * u * u, 117 + (tr[2] - 117) * u
            px += (r() - .5) * tr[3] * 1.4
            bagas.append((px, py, 1.9, cor))
            brilhos.append((px - .6, py - .6, .55, "#8a78b0"))
        h += pontos(bagas) + pontos(brilhos)
    if est == 10:
        h += brilho(90, 40, 3.4) + brilho(28, 52, 3)
    return h


# ------------------------------------------------------------------ baobá
def baoba_tronco(est):
    h = lerp(8, 55, min(1, est / 6))
    wb = lerp(5, 15, (est / 10) ** .8)
    wt = wb * .82
    top = 117 - h
    o = ('<path d="M%s 117C%s %s %s %s %s %sL%s %sC%s %s %s %s %s 117Z" fill="#c78f5e"/>'
         % (f(60 - wb), f(60 - wb * 1.1), f(117 - h * .35), f(60 - wt * 1.05), f(117 - h * .8), f(60 - wt), f(top),
            f(60 + wt), f(top), f(60 + wt * 1.05), f(117 - h * .8), f(60 + wb * 1.1), f(117 - h * .35), f(60 + wb)))
    o += ('<path d="M%s 117C%s %s %s %s %s %sL%s %sC%s %s %s %s %s 117Z" fill="#a56d43" opacity=".55"/>'
          % (f(60 + wb * .4), f(60 + wb * .55), f(117 - h * .35), f(60 + wt * .55), f(117 - h * .8), f(60 + wt * .4), f(top),
             f(60 + wt), f(top), f(60 + wt * 1.05), f(117 - h * .8), f(60 + wb * 1.1), f(117 - h * .35), f(60 + wb)))
    for a in (-.65, -.3, .05, .4, .7):
        o += '<path d="M%s %sL%s %s" stroke="#9a6238" stroke-width=".5" opacity=".5"/>' % (f(60 + wb * a), f(112), f(60 + wt * a), f(top + 4))
    for fr_ in (.3, .55, .8):
        yy = 117 - h * fr_
        o += '<path d="M%s %sQ60 %s %s %s" stroke="#8b5a38" stroke-width=".5" fill="none" opacity=".45"/>' % (
            f(60 - lerp(wb, wt, fr_) * .9), f(yy), f(yy + 2), f(60 + lerp(wb, wt, fr_) * .9), f(yy))
    if est >= 6:
        o += '<ellipse cx="60" cy="%s" rx="%s" ry="3" fill="#d19a68"/>' % (f(top), f(wt * 1.08))
    return o


GALHOS_BAOBA = [("M60 62Q60 54 60 42", 3.2), ("M54 62Q42 56 30 48", 2.8), ("M66 62Q78 56 90 48", 2.8)]
TWIGS_BAOBA = [("M45 57Q40 46 40 40", 1.8), ("M75 57Q80 46 80 40", 1.8), ("M60 50Q50 42 50 34", 1.6), ("M60 50Q70 42 70 34", 1.6),
               ("M30 48Q26 52 24 54", 1.5), ("M90 48Q94 52 96 54", 1.5)]
CACHOS_BAOBA = [(60, 30), (40, 40), (80, 40), (50, 34), (70, 34), (30, 48), (90, 48), (45, 46), (75, 46), (24, 54), (96, 54), (60, 42)]


def baoba_folhas(centros, seed):
    r = rng(seed)
    lista = []
    for cx, cy in centros:
        for _ in range(6):
            lista.append((cx + (r() - .5) * 15, cy + (r() - .5) * 6, 3.4 + r() * 2.2, ["#7f9f2f", "#9dbd3f", "#b4cf5a"][int(r() * 3)]))
    return pontos(lista)


# ------------------------------------------------------------------ montagem
def macro(nome, camadas, extra=""):
    return "{%% macro esp_%s(s, fr) %%}\n%s%s{%% endmacro %%}" % (nome, "".join(camadas), extra)


def montar():
    m = {}
    m["girassol"] = macro("girassol", [snap(k, girassol(k)) for k in range(1, 11)],
                          frutos([(53, 20), (67, 20), (60, 12), (50, 32), (70, 32)]))
    m["cogumelo"] = macro("cogumelo", [snap(k, cogumelo(k)) for k in range(1, 11)],
                          frutos([(44, 114), (76, 114), (52, 115), (68, 115), (60, 116)]))
    m["carnivora"] = macro("carnivora", [snap(k, carnivora(k)) for k in range(1, 11)],
                           frutos([(46, 115), (52, 116), (68, 116), (74, 115), (60, 117)], 1.4))
    cam = []
    for k, (dx, L, q) in enumerate(FRONDES, 1):
        cam.append(acum(k, fronde(dx, L, q, k, k)))
    m["samambaia"] = macro("samambaia", cam, frutos([(40, 100), (80, 100), (52, 92), (68, 92), (60, 84)], 1.6))
    m["cerejeira"] = macro("cerejeira", [snap(k, arvore(k, CEREJEIRA)) for k in range(1, 11)],
                           frutos([(40, 40), (80, 40), (52, 30), (68, 30), (60, 22)], 2.2))
    m["jabuticabeira"] = macro("jabuticabeira", [snap(k, jabuticabeira(k)) for k in range(1, 11)],
                               frutos([(54, 90), (66, 86), (58, 76), (63, 98), (57, 104)], 2.2))
    m["ipe"] = macro("ipe", [snap(k, arvore(k, IPE)) for k in range(1, 11)],
                     frutos([(36, 44), (84, 44), (50, 32), (70, 32), (60, 24)], 2))
    bao = [snap(k, baoba_tronco(k)) for k in range(1, 11)]
    bao.append(acum(6, "".join('<path d="%s" stroke="#8b5a38" stroke-width="%s" stroke-linecap="round" fill="none"/>' % g for g in GALHOS_BAOBA)))
    bao.append(acum(8, "".join('<path d="%s" stroke="#8b5a38" stroke-width="%s" stroke-linecap="round" fill="none"/>' % g for g in TWIGS_BAOBA)))
    for k, (a, b) in zip((7, 8, 9, 10), ((0, 3), (3, 6), (6, 9), (9, 12))):
        bao.append(acum(k, baoba_folhas(CACHOS_BAOBA[a:b], 30 + k)))
    bao.append(acum(9, '<circle cx="46" cy="38" r="1.5" fill="#fff"/><circle cx="72" cy="36" r="1.5" fill="#fff"/><circle cx="58" cy="30" r="1.5" fill="#fff"/>'
                       '<circle cx="86" cy="46" r="1.5" fill="#fff"/><circle cx="34" cy="46" r="1.5" fill="#fff"/>'))
    bao.append(acum(10, brilho(98, 36, 3.6) + brilho(20, 44, 3)))
    m["baoba"] = macro("baoba", bao, frutos([(48, 36), (72, 36), (36, 48), (84, 48), (60, 26)], 2))
    return m


def main():
    texto = ALVO.read_text(encoding="utf-8")
    crlf = "\r\n" in texto
    texto = texto.replace("\r\n", "\n")
    for nome, novo in montar().items():
        padrao = re.compile(r"\{%% macro esp_%s\(s, fr\) %%\}.*?\{%% endmacro %%\}" % nome, re.S)
        if not padrao.search(texto):
            raise SystemExit("macro esp_%s nao encontrada" % nome)
        texto = padrao.sub(lambda _m: novo, texto, count=1)
    if crlf:
        texto = texto.replace("\n", "\r\n")
    ALVO.write_text(texto, encoding="utf-8", newline="")
    print("ok:", ALVO)


if __name__ == "__main__":
    main()
