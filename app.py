import hashlib
import hmac
import io
import math
import os
import shutil
import sqlite3
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import (
    Flask, abort, g, jsonify, redirect, render_template, request, send_file, session, url_for,
)

import catalog
import game

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("STRIKES_DB", BASE_DIR / "data" / "strikes.db"))
BACKUP_DIR = DB_PATH.parent / "backups"

EVENTS = [
    ("daily", "Daily"),
    ("dev", "Presença no Dev"),
    ("encerramento", "Encerramento"),
]
EVENT_KEYS = [chave for chave, _ in EVENTS]

DEFAULT_MEMBERS = [
    "Arthur", "Bento", "Dominique", "Vitor", "Tiago",
    "Rafael", "Alexandre", "Heloisa", "Joao",
]

DEFAULT_CONFIG = {
    "semana1_inicio": "2026-10-12",
    "num_semanas": "10",
    "sprint_semanas": "2",
    "contar_a_partir_de": "2026-10-15",
}

DEFAULT_FERIADOS = [
    ("2026-10-12", "N. Sra. Aparecida"),
    ("2026-11-02", "Finados"),
    ("2026-11-20", "Consciência Negra"),
]

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # em producao (HTTPS) defina COOKIE_SECURE=1; em http://localhost isso quebraria o login
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)


# ------------------------------------------------------------ codigo de acesso
# Sem ACCESS_CODE (uso local) nada muda. Com ele, todas as paginas e a API exigem o codigo.
# O codigo e o SECRET_KEY ficam em variaveis de ambiente no servidor, nunca no repositorio.

MAX_ERROS = 5
BLOQUEIO_SEG = 600
TENTATIVAS = {}


def _codigo():
    return os.environ.get("ACCESS_CODE") or None


def _segredo():
    chave = os.environ.get("SECRET_KEY")
    if chave:
        return chave
    return hashlib.sha256(("jardim|" + (_codigo() or "")).encode("utf-8")).hexdigest()


def _assinatura():
    """Muda quando o codigo muda, derrubando as sessoes antigas."""
    return hashlib.sha256((_codigo() or "").encode("utf-8")).hexdigest()[:16]


def _ip():
    encaminhado = request.headers.get("X-Forwarded-For", "")
    return encaminhado.split(",")[0].strip() or request.remote_addr or "?"


def _destino_seguro(destino):
    if destino and destino.startswith("/") and not destino.startswith("//"):
        return destino
    return "/"


@app.before_request
def guarda_de_acesso():
    if not _codigo():
        return None
    app.secret_key = _segredo()
    if request.endpoint in ("entrar", "static"):
        return None
    if session.get("auth") != _assinatura():
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "erro": "Acesso negado."}), 401
        return redirect(url_for("entrar", next=request.full_path.rstrip("?")))
    if request.method == "POST" and request.path.startswith("/api/") \
            and request.headers.get("X-Requested-With") != "fetch":
        return jsonify({"ok": False, "erro": "Pedido inválido."}), 403
    return None


@app.route("/entrar", methods=["GET", "POST"])
def entrar():
    if not _codigo():
        return redirect(url_for("home"))
    ip = _ip()
    agora = time.time()
    estado = TENTATIVAS.get(ip, {"erros": 0, "bloqueado_ate": 0})
    destino = _destino_seguro(request.values.get("next"))
    erro, status = None, 200

    if request.method == "POST":
        if estado["bloqueado_ate"] > agora:
            erro, status = "Muitas tentativas. Tente de novo em alguns minutos.", 429
        else:
            tentativa = (request.form.get("codigo") or "").encode("utf-8")
            if hmac.compare_digest(tentativa, _codigo().encode("utf-8")):
                TENTATIVAS.pop(ip, None)
                session["auth"] = _assinatura()
                session.permanent = True
                return redirect(destino)
            estado["erros"] += 1
            if estado["erros"] >= MAX_ERROS:
                estado["erros"] = 0
                estado["bloqueado_ate"] = agora + BLOQUEIO_SEG
                erro, status = "Muitas tentativas. Tente de novo em alguns minutos.", 429
            else:
                erro, status = "Código incorreto.", 401
            TENTATIVAS[ip] = estado
    return render_template("entrar.html", erro=erro, destino=destino), status


@app.route("/sair")
def sair():
    session.clear()
    return redirect(url_for("entrar") if _codigo() else url_for("home"))


@app.route("/admin/baixar-banco")
def baixar_banco():
    """Copia consistente do banco, so quando o codigo de acesso esta ativo."""
    if not _codigo():
        abort(404)
    pasta = tempfile.mkdtemp()
    try:
        destino = os.path.join(pasta, "copia.db")
        src = sqlite3.connect(str(DB_PATH))
        dst = sqlite3.connect(destino)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        with open(destino, "rb") as f:
            dados = f.read()
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
    return send_file(
        io.BytesIO(dados), mimetype="application/octet-stream", as_attachment=True,
        download_name=f"strikes-{date.today().isoformat()}.db",
    )


def get_db():
    if "db" not in g:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def backup_db_if_needed(suffix=""):
    if not DB_PATH.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    nome = f"strikes{suffix}-{date.today().isoformat()}.db"
    destino = BACKUP_DIR / nome
    if not destino.exists():
        shutil.copy2(str(DB_PATH), str(destino))
    return destino


def _migrar_attendance_justificada(db):
    """Migra attendance para incluir 'justificada' no CHECK de status."""
    schema_row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='attendance'"
    ).fetchone()
    if schema_row is None:
        return
    if "justificada" in schema_row["sql"]:
        return

    backup_db_if_needed("-pre-migracao")

    antes_att = db.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    antes_mem = db.execute("SELECT COUNT(*) FROM members").fetchone()[0]

    db.executescript("""
        BEGIN;
        CREATE TABLE attendance_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id),
            event_date TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN ('daily', 'dev', 'encerramento')),
            status TEXT NOT NULL CHECK (status IN ('presente', 'faltou', 'justificada')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (member_id, event_date, event_type)
        );
        INSERT INTO attendance_new SELECT id, member_id, event_date, event_type, status, updated_at FROM attendance;
        DROP TABLE attendance;
        ALTER TABLE attendance_new RENAME TO attendance;
        COMMIT;
    """)

    depois_att = db.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    depois_mem = db.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    integ = db.execute("PRAGMA integrity_check").fetchone()[0]

    assert depois_att == antes_att, f"attendance perdeu linhas: {antes_att} -> {depois_att}"
    assert depois_mem == antes_mem, f"members perdeu linhas: {antes_mem} -> {depois_mem}"
    assert integ == "ok", f"integrity_check falhou: {integ}"


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    _migrar_attendance_justificada(db)

    db.executescript("""
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            reset_cursor INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id),
            event_date TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN ('daily', 'dev', 'encerramento')),
            status TEXT NOT NULL CHECK (status IN ('presente', 'faltou', 'justificada')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE (member_id, event_date, event_type)
        );

        CREATE TABLE IF NOT EXISTS prenda_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id),
            paid_at TEXT NOT NULL DEFAULT (datetime('now')),
            cursor_id INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS feriados (
            data TEXT PRIMARY KEY,
            nome TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id),
            item_id TEXT NOT NULL,
            custo INTEGER NOT NULL,
            comprado_em TEXT NOT NULL DEFAULT (datetime('now')),
            desfeita_em TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_compras_ativa
            ON compras (member_id, item_id) WHERE desfeita_em IS NULL;

        CREATE TABLE IF NOT EXISTS equipados (
            member_id INTEGER NOT NULL REFERENCES members(id),
            slot TEXT NOT NULL,
            item_id TEXT NOT NULL,
            PRIMARY KEY (member_id, slot)
        );

        CREATE TABLE IF NOT EXISTS metas_sprint (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sprint INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('presenca_pct', 'dias_cheios', 'sequencia_time')),
            alvo INTEGER NOT NULL,
            criada_em TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    db.commit()

    total_membros = db.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    if total_membros == 0:
        db.executemany(
            "INSERT INTO members (name) VALUES (?)",
            [(nome,) for nome in DEFAULT_MEMBERS],
        )

    for chave, valor in DEFAULT_CONFIG.items():
        db.execute(
            "INSERT OR IGNORE INTO config (chave, valor) VALUES (?, ?)",
            (chave, valor),
        )

    total_feriados = db.execute("SELECT COUNT(*) FROM feriados").fetchone()[0]
    if total_feriados == 0:
        db.executemany(
            "INSERT OR IGNORE INTO feriados (data, nome) VALUES (?, ?)",
            DEFAULT_FERIADOS,
        )

    db.commit()
    db.close()


def _get_config(db):
    rows = db.execute("SELECT chave, valor FROM config").fetchall()
    cfg = {r["chave"]: r["valor"] for r in rows}
    return cfg


def _get_feriados(db):
    rows = db.execute("SELECT data FROM feriados").fetchall()
    return {r["data"] for r in rows}


def _get_feriados_lista(db):
    rows = db.execute("SELECT data, nome FROM feriados ORDER BY data").fetchall()
    return [dict(r) for r in rows]


def _dias_letivos(db):
    cfg = _get_config(db)
    feriados = _get_feriados(db)
    return game.dias_letivos(
        cfg.get("contar_a_partir_de", "2026-10-15"),
        cfg.get("semana1_inicio", "2026-10-12"),
        int(cfg.get("num_semanas", "10")),
        feriados,
    )


def _semanas_projeto(db):
    cfg = _get_config(db)
    feriados = _get_feriados(db)
    return game.semanas_do_projeto(
        cfg.get("semana1_inicio", "2026-10-12"),
        int(cfg.get("num_semanas", "10")),
        feriados,
    )


def _registros_membro(db, member_id):
    rows = db.execute(
        "SELECT event_date, event_type, status FROM attendance WHERE member_id = ?",
        (member_id,),
    ).fetchall()
    by_date = {}
    for r in rows:
        by_date.setdefault(r["event_date"], {})
        if r["status"] == "presente":
            by_date[r["event_date"]]["presente"] = True
        elif r["status"] == "faltou":
            by_date[r["event_date"]]["faltou"] = True
        elif r["status"] == "justificada":
            by_date[r["event_date"]]["justificada"] = True
    return by_date


def _estado_jogo_membro(db, member_id, dias_letivos_lista):
    meta = game.meta_floracao(len(dias_letivos_lista))
    reg = _registros_membro(db, member_id)
    return game.calcular_membro(dias_letivos_lista, reg, meta)


def _registros_globais(db):
    """{data: {member_id: {'presente': True, ...}}} em uma unica consulta."""
    glob = {}
    for r in db.execute("SELECT member_id, event_date, status FROM attendance").fetchall():
        glob.setdefault(r["event_date"], {}).setdefault(r["member_id"], {})[r["status"]] = True
    return glob


def _gastos_por_membro(db):
    rows = db.execute(
        "SELECT member_id, SUM(custo) AS total FROM compras "
        "WHERE desfeita_em IS NULL GROUP BY member_id"
    ).fetchall()
    return {r["member_id"]: r["total"] or 0 for r in rows}


def _posses_e_equipados(db):
    posses, equip = {}, {}
    for r in db.execute(
        "SELECT member_id, item_id FROM compras WHERE desfeita_em IS NULL"
    ).fetchall():
        posses.setdefault(r["member_id"], set()).add(r["item_id"])
    for r in db.execute("SELECT member_id, slot, item_id FROM equipados").fetchall():
        equip.setdefault(r["member_id"], {})[r["slot"]] = r["item_id"]
    return posses, equip


def get_member_stats(db, dias_letivos_lista=None):
    if dias_letivos_lista is None:
        dias_letivos_lista = _dias_letivos(db)
    meta = game.meta_floracao(len(dias_letivos_lista))
    semanas = _semanas_projeto(db)
    dias_set = set(dias_letivos_lista)
    membros = db.execute(
        "SELECT * FROM members ORDER BY active DESC, name COLLATE NOCASE"
    ).fetchall()
    glob = _registros_globais(db)
    ativos_ids = [m["id"] for m in membros if m["active"]]
    cheios = game.dia_cheio(ativos_ids, {d: v for d, v in glob.items() if d in dias_set})
    gastos = _gastos_por_membro(db)
    posses, equip = _posses_e_equipados(db)

    resultado = []
    for m in membros:
        reg = {d: v[m["id"]] for d, v in glob.items() if m["id"] in v}
        estado = game.calcular_membro(dias_letivos_lista, reg, meta)
        progresso, dias_ate_proximo = game.progresso_estagio(
            estado["g"], meta, estado["estagio"]
        )
        ganho = game.calcular_sementes(
            dias_letivos_lista, semanas, reg, estado["floresceu"], dias_cheios=cheios
        )
        gasto = gastos.get(m["id"], 0)
        resultado.append({
            "sementes": max(ganho["total"] - gasto, 0),
            "sementes_ganhas": ganho["total"],
            "sementes_gastas": gasto,
            "visual": catalog.montar_visual(posses.get(m["id"], set()), equip.get(m["id"], {})),
            "progresso": progresso,
            "dias_ate_proximo": dias_ate_proximo,
            "chama": game.nivel_chama(estado["streak"]),
            "id": m["id"],
            "name": m["name"],
            "active": bool(m["active"]),
            "estagio": estado["estagio"],
            "estagio_nome": game.STAGE_NAMES[estado["estagio"]],
            "floresceu": estado["floresceu"],
            "floresceu_em": estado["floresceu_em"],
            "vigor": estado["vigor"],
            "streak": estado["streak"],
            "melhor_streak": estado["melhor_streak"],
            "dias_presentes": estado["dias_presentes"],
            "frutos": estado["frutos"],
            "g": estado["g"],
            "meta": meta,
            "conquistas": game.conquistas_membro(
                estado["dias_presentes"], estado["melhor_streak"],
                estado["floresceu"], meta
            ),
        })
    return resultado


NOMES_SEMANA = ["seg", "ter", "qua", "qui", "sex"]


def _estado_dia(reg_dia, data_str, hoje_str, dias_set):
    """Mesma prioridade do game.calcular_membro: presente > faltou > justificada."""
    if data_str not in dias_set:
        return "folga"
    if reg_dia.get("presente"):
        return "presente"
    if reg_dia.get("faltou"):
        return "faltou"
    if reg_dia.get("justificada"):
        return "justificada"
    if data_str > hoje_str:
        return "futuro"
    if data_str == hoje_str:
        return "hoje"
    return "vazio"


def _extras_dia(db, ids, data_str, dias_set):
    """Por membro: faixa seg-sex da semana vista, estado do dia, balao da planta e chama."""
    if not ids:
        return {}
    hoje_str = date.today().isoformat()
    d = date.fromisoformat(data_str)
    seg = d - timedelta(days=d.weekday())
    datas = [seg + timedelta(days=i) for i in range(5)]
    marcadores = ",".join("?" * len(ids))
    rows = db.execute(
        f"SELECT member_id, event_date, status FROM attendance "
        f"WHERE member_id IN ({marcadores}) AND event_date BETWEEN ? AND ?",
        (*ids, datas[0].isoformat(), datas[-1].isoformat()),
    ).fetchall()
    regs = {}
    for r in rows:
        regs.setdefault(r["member_id"], {}).setdefault(r["event_date"], {})[r["status"]] = True

    resultado = {}
    for mid in ids:
        semana = []
        for i, dd in enumerate(datas):
            ds = dd.isoformat()
            estado = _estado_dia(regs.get(mid, {}).get(ds, {}), ds, hoje_str, dias_set)
            semana.append({
                "data": ds,
                "rotulo": f"{NOMES_SEMANA[i]} {dd.day:02d}/{dd.month:02d}",
                "estado": estado,
            })
        estado_visto = next((x["estado"] for x in semana if x["data"] == data_str), "folga")
        dia_status = {"presente": "regada", "justificada": "avisou", "folga": "folga"}.get(
            estado_visto, "sede"
        )
        resultado[mid] = {
            "semana": semana,
            "dia_estado": estado_visto,
            "dia_status": dia_status,
            "aceso": not (data_str == hoje_str and dia_status == "sede"),
        }
    return resultado


def _enriquecer_jardim(db, itens, data_str, dias_set):
    extras = _extras_dia(db, [m["id"] for m in itens], data_str, dias_set)
    for m in itens:
        m.update(extras[m["id"]])
    return itens


@app.context_processor
def cena_contexto():
    agora = datetime.now()
    hora = agora.hour + agora.minute / 60
    sx, sy = game.posicao_astro(hora, 5.5, 13)
    lx, ly = game.posicao_astro(hora, 18.5, 11)
    return {
        "cena_periodo": game.periodo_do_dia(hora),
        "cena_vars": f"--sx:{sx}%;--sy:{sy}%;--lx:{lx}%;--ly:{ly}%",
    }


def get_overall_trend(db, dias=14):
    linhas = db.execute(
        """
        SELECT event_date,
               SUM(CASE WHEN status = 'presente' THEN 1 ELSE 0 END) AS presentes,
               SUM(CASE WHEN status = 'faltou' THEN 1 ELSE 0 END) AS faltas,
               COUNT(*) as total_reg
        FROM attendance
        GROUP BY event_date
        ORDER BY event_date DESC
        LIMIT ?
        """,
        (dias,),
    ).fetchall()
    linhas = list(reversed(linhas))
    serie = []
    for r in linhas:
        total = r["presentes"] + r["faltas"]
        taxa = round((r["presentes"] / total) * 100) if total else 0
        serie.append({"data": r["event_date"], "taxa": taxa, "total": total})
    return serie


def build_line_chart(serie, width=600, height=160, pad_x=24, pad_y=20):
    if not serie:
        return {"points": "", "dots": [], "width": width, "height": height}
    n = len(serie)
    if n == 1:
        xs = [width / 2]
    else:
        step = (width - 2 * pad_x) / (n - 1)
        xs = [pad_x + i * step for i in range(n)]
    dots = []
    for x, item in zip(xs, serie):
        y = pad_y + (100 - item["taxa"]) / 100 * (height - 2 * pad_y)
        dots.append({"x": round(x, 1), "y": round(y, 1), "data": item["data"], "taxa": item["taxa"]})
    points = " ".join(f"{d['x']},{d['y']}" for d in dots)
    return {"points": points, "dots": dots, "width": width, "height": height}


def get_presencas_por_membro(db):
    linhas = db.execute(
        """
        SELECT m.id, m.name,
               SUM(CASE WHEN a.status = 'presente' THEN 1 ELSE 0 END) AS presentes,
               SUM(CASE WHEN a.status = 'justificada' THEN 1 ELSE 0 END) AS justificadas,
               SUM(CASE WHEN a.status = 'faltou' THEN 1 ELSE 0 END) AS faltas
        FROM members m
        LEFT JOIN attendance a ON a.member_id = m.id
        WHERE m.active = 1
        GROUP BY m.id
        ORDER BY presentes DESC
        """
    ).fetchall()
    maior = max((r["presentes"] for r in linhas), default=1) or 1
    dados = []
    for r in linhas:
        pct = round(r["presentes"] / maior * 100, 1)
        total = (r["presentes"] or 0) + (r["faltas"] or 0) + (r["justificadas"] or 0)
        taxa = round((r["presentes"] / total) * 100) if total else None
        dados.append({
            "id": r["id"],
            "name": r["name"],
            "presentes": r["presentes"] or 0,
            "justificadas": r["justificadas"] or 0,
            "faltas": r["faltas"] or 0,
            "pct": pct,
            "taxa_presenca": taxa,
        })
    return dados


def _cfg_sprints(db):
    cfg = _get_config(db)
    return game.sprints_do_projeto(
        cfg.get("semana1_inicio", "2026-10-12"),
        int(cfg.get("num_semanas", "10")),
        int(cfg.get("sprint_semanas", "2")),
    )


def _sprint_atual(db):
    return game.sprint_da_data(date.today().isoformat(), _cfg_sprints(db))


def _e_dia_letivo(data_str, db):
    dias = _dias_letivos(db)
    return data_str in dias


SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


def _data_extenso(d):
    return f"{SEMANA[d.weekday()]}, {d.day} de {MESES[d.month - 1]}"


@app.route("/")
def home():
    return redirect(url_for("dia", data_str=date.today().isoformat()))


@app.route("/dia/<data_str>")
def dia(data_str):
    try:
        data_atual = date.fromisoformat(data_str)
    except ValueError:
        abort(404)

    db = get_db()
    dias_letivos_lista = _dias_letivos(db)
    e_letivo = data_str in dias_letivos_lista

    cfg = _get_config(db)
    feriados = _get_feriados(db)
    motivo_nao_letivo = None
    if not e_letivo:
        if data_str in feriados:
            nome = db.execute("SELECT nome FROM feriados WHERE data = ?", (data_str,)).fetchone()
            motivo_nao_letivo = f"Feriado: {nome['nome']}" if nome else "Feriado"
        elif data_atual.weekday() >= 5:
            motivo_nao_letivo = "Fim de semana"
        else:
            motivo_nao_letivo = "Fora do periodo do projeto"

    membros = db.execute(
        "SELECT * FROM members WHERE active = 1 ORDER BY name COLLATE NOCASE"
    ).fetchall()
    registros = db.execute(
        "SELECT member_id, event_type, status FROM attendance WHERE event_date = ?",
        (data_str,),
    ).fetchall()
    status_map = {(r["member_id"], r["event_type"]): r["status"] for r in registros}
    stats_list = get_member_stats(db, dias_letivos_lista)
    stats_by_id = {s["id"]: s for s in stats_list}

    linhas = []
    for m in membros:
        celulas = {ev: status_map.get((m["id"], ev)) for ev in EVENT_KEYS}
        linhas.append({"member": m, "cells": celulas, "stats": stats_by_id.get(m["id"])})

    dia_anterior = (data_atual - timedelta(days=1)).isoformat()
    dia_seguinte = (data_atual + timedelta(days=1)).isoformat()

    jardim = _enriquecer_jardim(
        db, [s for s in stats_list if s["active"]], data_str, set(dias_letivos_lista)
    )

    return render_template(
        "dia.html",
        data_str=data_str,
        linhas=linhas,
        events=EVENTS,
        hoje=date.today().isoformat(),
        dia_anterior=dia_anterior,
        dia_seguinte=dia_seguinte,
        e_letivo=e_letivo,
        motivo_nao_letivo=motivo_nao_letivo,
        jardim=jardim,
        data_extenso=_data_extenso(data_atual),
        dia_n=dias_letivos_lista.index(data_str) + 1 if e_letivo else None,
        dias_total=len(dias_letivos_lista),
        marcos_ids=_marcos_liberados(stats_list, game.meta_floracao(len(dias_letivos_lista))),
        panorama=_panorama(db, _base_coletivo(db), request.args.get("p", "projeto")),
    )


TIPOS_META = {
    "presenca_pct": {"max": 100, "titulo": lambda a: f"{a}% de presença do time"},
    "dias_cheios": {"max": 60, "titulo": lambda a: f"{a} {'dia cheio' if a == 1 else 'dias cheios'}"},
    "sequencia_time": {
        "max": 60,
        "titulo": lambda a: f"Sequência de {a} {'dia cheio' if a == 1 else 'dias cheios'} seguidos",
    },
}
METAS_SUGERIDAS = [("presenca_pct", 90), ("dias_cheios", 5)]

CONQUISTAS = [
    ("primeiro_dia", "Primeiro dia", "Marcou a primeira presença."),
    ("streak_5", "5 dias seguidos", "Uma semana inteira de chama acesa."),
    ("streak_10", "10 dias seguidos", "Duas semanas sem apagar o foguinho."),
    ("streak_20", "20 dias seguidos", "Um mês de constância."),
    ("streak_40", "40 dias seguidos", "Constância de campeão."),
    ("metade_meta", "Metade do caminho", "Chegou à metade da meta de floração."),
    ("floresceu", "Floresceu", "A planta chegou ao fim do caminho."),
]


def _reg_membro(glob, member_id):
    return {d: v[member_id] for d, v in glob.items() if member_id in v}


def _base_coletivo(db):
    dias = _dias_letivos(db)
    dias_set = set(dias)
    membros = get_member_stats(db, dias)
    ativos = [m for m in membros if m["active"]]
    ativos_ids = [m["id"] for m in ativos]
    glob = _registros_globais(db)
    cheios = game.dia_cheio(ativos_ids, {d: v for d, v in glob.items() if d in dias_set})
    return {
        "dias": dias, "dias_set": dias_set, "meta": game.meta_floracao(len(dias)),
        "membros": membros, "ativos": ativos, "ativos_ids": ativos_ids,
        "glob": glob, "cheios": cheios, "sprints": _cfg_sprints(db),
        "hoje": date.today().isoformat(),
    }


def _progresso_coletivo(ativos, meta):
    if not ativos or meta <= 0:
        return 0
    return round(sum(m["g"] for m in ativos) / (len(ativos) * meta) * 100)


def _marcos_liberados(stats_list, meta):
    ativos = [s for s in stats_list if s["active"]]
    return [m["id"] for m in game.marcos_coletivos(_progresso_coletivo(ativos, meta)) if m["liberado"]]


def _dias_da_sprint(ctx, n):
    sp = ctx["sprints"][n - 1]
    return sp, [d for d in ctx["dias"] if sp["inicio"] <= d <= sp["fim"]]


def _metas_da_sprint(db, ctx, n):
    _, dias_sp = _dias_da_sprint(ctx, n)
    metas = []
    for r in db.execute("SELECT * FROM metas_sprint WHERE sprint = ? ORDER BY id", (n,)).fetchall():
        av = game.avaliar_meta(
            r["tipo"], r["alvo"], dias_sp, ctx["hoje"], ctx["ativos_ids"], ctx["glob"], ctx["cheios"]
        )
        metas.append({**dict(r), **av})
    return metas


def _resumo_semana(db, ctx):
    semanas = _semanas_projeto(db)
    hoje = ctx["hoje"]
    idx = None
    for i, dias_sem in enumerate(semanas):
        if dias_sem and dias_sem[0] <= hoje:
            idx = i
    if idx is None:
        return None
    decorridos = [d for d in semanas[idx] if d <= hoje and d in ctx["dias_set"]]
    if not decorridos or not ctx["ativos_ids"]:
        return None

    possiveis = len(decorridos) * len(ctx["ativos_ids"])
    presentes = sum(
        1 for d in decorridos for mid in ctx["ativos_ids"]
        if ctx["glob"].get(d, {}).get(mid, {}).get("presente", False)
    )
    antes = [d for d in ctx["dias"] if d < decorridos[0]]
    data_antes = antes[-1] if antes else "0000-00-00"
    subiram = 0
    for m in ctx["ativos"]:
        reg = _reg_membro(ctx["glob"], m["id"])
        ini = game.estado_ate(ctx["dias"], reg, ctx["meta"], data_antes)["estagio"]
        fim = game.estado_ate(ctx["dias"], reg, ctx["meta"], decorridos[-1])["estagio"]
        if fim > ini:
            subiram += 1
    return {
        "n": idx + 1,
        "dias": len(decorridos),
        "presenca_pct": round(100 * presentes / possiveis),
        "dias_cheios": sum(1 for d in decorridos if d in ctx["cheios"]),
        "subiram": subiram,
        "total": len(ctx["ativos"]),
    }


PERIODOS_PANORAMA = ("projeto", "sprint", "semana")


def _panorama(db, ctx, periodo="projeto", hoje=None):
    """Panorama do grupo, estilo mapa de contribuicoes do GitHub: o time dia a dia e
    cada pessoa em uma linha, para o projeto todo, a sprint atual ou a semana atual."""
    hoje = hoje or ctx["hoje"]
    if periodo not in PERIODOS_PANORAMA:
        periodo = "projeto"
    cfg = _get_config(db)
    s1 = date.fromisoformat(cfg.get("semana1_inicio", "2026-10-12"))
    n_sem = int(cfg.get("num_semanas", "10"))
    sprint_n = game.sprint_da_data(hoje, ctx["sprints"])

    indices = list(range(n_sem))
    if periodo == "sprint":
        sp = ctx["sprints"][sprint_n - 1]
        indices = [i for i in indices
                   if sp["inicio"] <= (s1 + timedelta(weeks=i)).isoformat() <= sp["fim"]]
    elif periodo == "semana":
        indices = [max(0, min(n_sem - 1, (date.fromisoformat(hoje) - s1).days // 7))]

    ativos = ctx["ativos"]
    total = len(ativos)
    regs = {m["id"]: _reg_membro(ctx["glob"], m["id"]) for m in ativos}
    semanas = []
    linhas = {m["id"]: [] for m in ativos}
    dias_do_periodo = []

    for i in indices:
        seg = s1 + timedelta(weeks=i)
        dias_time = []
        por_pessoa = {m["id"]: [] for m in ativos}
        for j in range(5):
            dd = seg + timedelta(days=j)
            ds = dd.isoformat()
            rotulo = f"{NOMES_SEMANA[j]} {dd.day:02d}/{dd.month:02d}"
            letivo = ds in ctx["dias_set"]
            presentes = sum(
                1 for m in ativos if ctx["glob"].get(ds, {}).get(m["id"], {}).get("presente")
            )
            if letivo and ds <= hoje:
                dias_do_periodo.append(ds)
            if not letivo:
                estado = "folga"
            elif ds > hoje:
                estado = "futuro"
            elif presentes == 0:
                estado = "hoje" if ds == hoje else "vazio"
            else:
                estado = "dia"
            dias_time.append({
                "data": ds, "rotulo": rotulo, "estado": estado,
                "nivel": game.nivel_presenca(presentes, total) if estado in ("dia", "hoje", "vazio") else 0,
                "presentes": presentes, "total": total, "e_hoje": ds == hoje,
            })
            for m in ativos:
                por_pessoa[m["id"]].append({
                    "data": ds, "rotulo": rotulo,
                    "estado": _estado_dia(regs[m["id"]].get(ds, {}), ds, hoje, ctx["dias_set"]),
                })
        semanas.append({"n": i + 1, "dias": dias_time,
                        "sprint": game.sprint_da_data(seg.isoformat(), ctx["sprints"])})
        for m in ativos:
            linhas[m["id"]].append(por_pessoa[m["id"]])

    grupos = []
    for k, sem in enumerate(semanas):
        if grupos and semanas[grupos[-1][0]]["sprint"] == sem["sprint"]:
            grupos[-1].append(k)
        else:
            grupos.append([k])
    grupos = [{"sprint": semanas[g[0]]["sprint"], "idx": g} for g in grupos]

    possiveis = len(dias_do_periodo) * total
    presentes_total = sum(
        1 for d in dias_do_periodo for m in ativos
        if ctx["glob"].get(d, {}).get(m["id"], {}).get("presente")
    )
    resumo = {
        "dias": len(dias_do_periodo),
        "presenca_pct": round(100 * presentes_total / possiveis) if possiveis else 0,
        "dias_cheios": sum(1 for d in dias_do_periodo if d in ctx["cheios"]),
        "maior_sequencia": game.avaliar_meta(
            "sequencia_time", 1, dias_do_periodo, hoje, ctx["ativos_ids"], ctx["glob"], ctx["cheios"]
        )["valor"],
    }
    return {
        "periodo": periodo,
        "opcoes": [
            {"id": "projeto", "nome": "Projeto todo"},
            {"id": "sprint", "nome": f"Sprint {sprint_n}"},
            {"id": "semana", "nome": "Esta semana"},
        ],
        "semanas": semanas,
        "grupos": grupos,
        "linhas": [{"id": m["id"], "name": m["name"], "semanas": linhas[m["id"]]} for m in ativos],
        "resumo": resumo,
        "total": total,
    }


def formatar_nomes(nomes, total):
    """'Ana', 'Ana e Bia', 'Ana, Bia e Caio', 'Ana, Bia, Caio e mais 2' ou 'Todo o time'."""
    if total > 1 and len(nomes) >= total:
        return "Todo o time"
    if len(nomes) <= 1:
        return nomes[0] if nomes else ""
    if len(nomes) <= 3:
        return ", ".join(nomes[:-1]) + " e " + nomes[-1]
    return ", ".join(nomes[:3]) + f" e mais {len(nomes) - 3}"


def _lideres(ativos, chave):
    if not ativos:
        return 0, []
    maior = max(m[chave] for m in ativos)
    return maior, sorted(m["name"] for m in ativos if m[chave] == maior)


def _destaques(ativos):
    """Destaques positivos do time. Em empate, aparecem todos os lideres."""
    itens = []
    for ident, rotulo, chave in (
        ("streak_atual", "Chama mais alta agora", "streak"),
        ("melhor_sequencia", "Maior sequência", "melhor_streak"),
        ("mais_constante", "Mais constante", "dias_presentes"),
    ):
        valor, nomes = _lideres(ativos, chave)
        if valor > 0:
            itens.append({"id": ident, "rotulo": rotulo, "valor": valor, "nomes": nomes,
                          "texto": formatar_nomes(nomes, len(ativos))})
    flores = sorted(m["name"] for m in ativos if m["floresceu"])
    if flores:
        itens.append({"id": "floresceram", "rotulo": "Já floresceram", "valor": len(flores),
                      "nomes": flores, "texto": formatar_nomes(flores, len(ativos))})
    return itens


def _painel_coletivo(db, ctx):
    hoje = ctx["hoje"]
    n = game.sprint_da_data(hoje, ctx["sprints"])
    progresso = _progresso_coletivo(ctx["ativos"], ctx["meta"])
    cfg = _get_config(db)
    semanas = _semanas_projeto(db)
    trilhas = []
    for m in ctx["ativos"]:
        reg = _reg_membro(ctx["glob"], m["id"])
        trilha = game.semanas_status(semanas, reg, hoje, cfg.get("contar_a_partir_de", "2026-10-15"))
        trilhas.append({
            "id": m["id"], "name": m["name"], "semanas": trilha,
            "fechadas": sum(1 for t in trilha if t["estado"] == "fechada"),
        })
    com_registro = {d for d, v in ctx["glob"].items() if v}
    seq = game.sequencia_dias_cheios(ctx["dias"], ctx["cheios"], com_registro, hoje)
    return {
        "progresso_coletivo": progresso,
        "marcos": game.marcos_coletivos(progresso),
        "marcos_ids": _marcos_liberados(ctx["membros"], ctx["meta"]),
        "dias_cheios_seq": seq,
        "chama_time": game.nivel_chama(seq),
        "sprint_atual": n,
        "total_sprints": len(ctx["sprints"]),
        "sprint_info": ctx["sprints"][n - 1],
        "metas": _metas_da_sprint(db, ctx, n),
        "tipos_meta": TIPOS_META,
        "bosque": sorted(
            [m for m in ctx["ativos"] if m["floresceu"]], key=lambda m: m["floresceu_em"] or ""
        ),
        "trilhas": trilhas,
        "resumo_semana": _resumo_semana(db, ctx),
        "destaques": _destaques(ctx["ativos"]),
    }


@app.route("/dashboard")
def dashboard():
    db = get_db()
    ctx = _base_coletivo(db)
    _enriquecer_jardim(db, ctx["ativos"], ctx["hoje"], ctx["dias_set"])
    tendencia = get_overall_trend(db, dias=14)
    return render_template(
        "dashboard.html",
        membros=ctx["membros"],
        grafico_linha=build_line_chart(tendencia),
        tem_tendencia=len(tendencia) >= 2,
        presencas=get_presencas_por_membro(db),
        meta=ctx["meta"],
        total_dias=len(ctx["dias"]),
        stage_names=game.STAGE_NAMES,
        **_painel_coletivo(db, ctx),
    )


def _int_ou_none(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


@app.route("/api/metas", methods=["POST"])
def api_metas():
    p = request.get_json(force=True, silent=True) or {}
    acao = p.get("acao")
    db = get_db()
    total_sprints = len(_cfg_sprints(db))

    if acao == "remover":
        mid = _int_ou_none(p.get("id"))
        if mid is None:
            abort(400)
        db.execute("DELETE FROM metas_sprint WHERE id = ?", (mid,))
        db.commit()
        return jsonify({"ok": True})

    sprint = _int_ou_none(p.get("sprint"))
    if sprint is None or not 1 <= sprint <= total_sprints:
        return _erro("Sprint inválida.")

    if acao == "sugerir":
        for tipo, alvo in METAS_SUGERIDAS:
            existe = db.execute(
                "SELECT 1 FROM metas_sprint WHERE sprint = ? AND tipo = ? AND alvo = ?",
                (sprint, tipo, alvo),
            ).fetchone()
            if not existe:
                db.execute(
                    "INSERT INTO metas_sprint (sprint, titulo, tipo, alvo) VALUES (?, ?, ?, ?)",
                    (sprint, TIPOS_META[tipo]["titulo"](alvo), tipo, alvo),
                )
        db.commit()
        return jsonify({"ok": True})

    if acao == "adicionar":
        tipo = p.get("tipo")
        alvo = _int_ou_none(p.get("alvo"))
        if tipo not in TIPOS_META:
            return _erro("Tipo de meta inválido.")
        if alvo is None or not 1 <= alvo <= TIPOS_META[tipo]["max"]:
            return _erro("Valor da meta inválido.")
        titulo = (p.get("titulo") or "").strip() or TIPOS_META[tipo]["titulo"](alvo)
        cur = db.execute(
            "INSERT INTO metas_sprint (sprint, titulo, tipo, alvo) VALUES (?, ?, ?, ?)",
            (sprint, titulo[:80], tipo, alvo),
        )
        db.commit()
        return jsonify({"ok": True, "id": cur.lastrowid})

    abort(400)


def _presenca_por_evento(db, decorridos, ativos_ids):
    if not decorridos or not ativos_ids:
        return [{"chave": k, "nome": nome, "pct": 0} for k, nome in EVENTS]
    ph_d = ",".join("?" * len(decorridos))
    ph_m = ",".join("?" * len(ativos_ids))
    rows = db.execute(
        f"SELECT event_type, COUNT(*) AS c FROM attendance WHERE status = 'presente' "
        f"AND event_date IN ({ph_d}) AND member_id IN ({ph_m}) GROUP BY event_type",
        (*decorridos, *ativos_ids),
    ).fetchall()
    cont = {r["event_type"]: r["c"] for r in rows}
    possiveis = len(decorridos) * len(ativos_ids)
    return [
        {"chave": k, "nome": nome, "pct": round(100 * cont.get(k, 0) / possiveis)}
        for k, nome in EVENTS
    ]


def _resumo_sprint(db, ctx, n):
    sp, dias_sp = _dias_da_sprint(ctx, n)
    hoje = ctx["hoje"]
    decorridos = [d for d in dias_sp if d <= hoje]
    ativos = ctx["ativos"]

    def meta_valor(tipo):
        return game.avaliar_meta(
            tipo, 1, dias_sp, hoje, ctx["ativos_ids"], ctx["glob"], ctx["cheios"]
        )["valor"]

    antes = [d for d in ctx["dias"] if d < sp["inicio"]]
    data_antes = antes[-1] if antes else "0000-00-00"
    data_fim = decorridos[-1] if decorridos else data_antes

    evolucao, destaques = [], []
    for m in ativos:
        reg = _reg_membro(ctx["glob"], m["id"])
        e0 = game.estado_ate(ctx["dias"], reg, ctx["meta"], data_antes)
        e1 = game.estado_ate(ctx["dias"], reg, ctx["meta"], data_fim)
        evolucao.append({
            "name": m["name"], "de": game.STAGE_NAMES[e0["estagio"]],
            "para": game.STAGE_NAMES[e1["estagio"]], "subiu": e1["estagio"] - e0["estagio"],
            "visual": m["visual"],
        })
        na_sprint = game.calcular_membro(dias_sp, reg, ctx["meta"])
        destaques.append({"name": m["name"], "sequencia": na_sprint["melhor_streak"],
                          "presencas": na_sprint["dias_presentes"]})

    serie = []
    for d in decorridos:
        por_membro = ctx["glob"].get(d)
        if not por_membro or not ativos:
            continue
        presentes = sum(1 for mid in ctx["ativos_ids"] if por_membro.get(mid, {}).get("presente"))
        serie.append({"data": d, "taxa": round(100 * presentes / len(ativos)), "total": len(ativos)})

    metas = _metas_da_sprint(db, ctx, n)
    com_seq = sorted((x for x in destaques if x["sequencia"] > 0),
                     key=lambda x: (-x["sequencia"], x["name"]))
    corte = com_seq[min(2, len(com_seq) - 1)]["sequencia"] if com_seq else 0
    destaques_seq = [x for x in com_seq if x["sequencia"] >= corte]  # empates nao ficam de fora
    return {
        "sprint": sp, "n": n, "total_sprints": len(ctx["sprints"]),
        "dias_total": len(dias_sp), "dias_decorridos": len(decorridos),
        "encerrada": sp["fim"] < hoje,
        "presenca_pct": meta_valor("presenca_pct"),
        "dias_cheios": meta_valor("dias_cheios"),
        "maior_sequencia_time": meta_valor("sequencia_time"),
        "por_evento": _presenca_por_evento(db, decorridos, ctx["ativos_ids"]),
        "evolucao": sorted(evolucao, key=lambda x: (-x["subiu"], x["name"])),
        "subiram": sum(1 for x in evolucao if x["subiu"] > 0),
        "destaques_seq": destaques_seq,
        "floresceram": [m["name"] for m in ativos
                        if m["floresceu_em"] and sp["inicio"] <= m["floresceu_em"] <= sp["fim"]],
        "metas": metas,
        "metas_cumpridas": sum(1 for m in metas if m["cumprida"]),
        "grafico": build_line_chart(serie), "tem_grafico": len(serie) >= 2,
        "tipos_meta": TIPOS_META,
    }


@app.route("/sprint/<int:n>")
def sprint_page(n):
    db = get_db()
    ctx = _base_coletivo(db)
    if not 1 <= n <= len(ctx["sprints"]):
        abort(404)
    return render_template("sprint.html", **_resumo_sprint(db, ctx, n))


def _calendario_membro(db, ctx, member_id):
    cfg = _get_config(db)
    s1 = date.fromisoformat(cfg.get("semana1_inicio", "2026-10-12"))
    reg = _reg_membro(ctx["glob"], member_id)
    semanas = []
    for i in range(int(cfg.get("num_semanas", "10"))):
        seg = s1 + timedelta(weeks=i)
        dias = []
        for j in range(5):
            dd = seg + timedelta(days=j)
            ds = dd.isoformat()
            dias.append({
                "data": ds, "dia": dd.day,
                "estado": _estado_dia(reg.get(ds, {}), ds, ctx["hoje"], ctx["dias_set"]),
                "rotulo": f"{NOMES_SEMANA[j]} {dd.day:02d}/{dd.month:02d}",
            })
        semanas.append({"n": i + 1, "dias": dias})
    return semanas


@app.route("/membro/<int:member_id>")
def membro_page(member_id):
    db = get_db()
    ctx = _base_coletivo(db)
    stats = next((m for m in ctx["membros"] if m["id"] == member_id), None)
    if stats is None:
        abort(404)
    if stats["active"]:
        _enriquecer_jardim(db, [stats], ctx["hoje"], ctx["dias_set"])
    cfg = _get_config(db)
    reg = _reg_membro(ctx["glob"], member_id)
    trilha = game.semanas_status(
        _semanas_projeto(db), reg, ctx["hoje"], cfg.get("contar_a_partir_de", "2026-10-15")
    )
    ganhas = set(stats["conquistas"])
    return render_template(
        "membro.html",
        m=stats,
        trilha=trilha,
        fechadas=sum(1 for t in trilha if t["estado"] == "fechada"),
        calendario=_calendario_membro(db, ctx, member_id),
        conquistas=[
            {"id": cid, "nome": nome, "desc": desc, "ganha": cid in ganhas}
            for cid, nome, desc in CONQUISTAS
        ],
    )


@app.route("/historico")
def historico():
    db = get_db()
    dias = db.execute(
        """
        SELECT
            event_date,
            COUNT(*) FILTER (WHERE status = 'presente') AS presentes,
            COUNT(*) FILTER (WHERE status = 'faltou') AS faltas,
            COUNT(*) FILTER (WHERE status = 'justificada') AS justificadas,
            COUNT(DISTINCT member_id) AS membros_registrados
        FROM attendance
        GROUP BY event_date
        ORDER BY event_date DESC
        """
    ).fetchall()
    dias = [
        {**dict(d), "rotulo": _data_extenso(date.fromisoformat(d["event_date"]))}
        for d in dias
    ]
    return render_template("historico.html", dias=dias, hoje=date.today().isoformat())


@app.route("/membros")
def membros_page():
    db = get_db()
    dias_letivos_lista = _dias_letivos(db)
    membros = get_member_stats(db, dias_letivos_lista)
    return render_template("membros.html", membros=membros)


@app.route("/calendario")
def calendario_page():
    db = get_db()
    cfg = _get_config(db)
    feriados = _get_feriados_lista(db)
    dias_letivos_lista = _dias_letivos(db)
    return render_template(
        "calendario.html",
        cfg=cfg,
        feriados=feriados,
        total_dias=len(dias_letivos_lista),
        meta=game.meta_floracao(len(dias_letivos_lista)),
    )


@app.route("/api/calendario", methods=["POST"])
def api_calendario():
    payload = request.get_json(force=True, silent=True) or {}
    db = get_db()
    campos_validos = {"semana1_inicio", "num_semanas", "sprint_semanas", "contar_a_partir_de"}
    for chave, valor in payload.items():
        if chave in campos_validos:
            db.execute(
                "INSERT OR REPLACE INTO config (chave, valor) VALUES (?, ?)",
                (chave, str(valor)),
            )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/feriados", methods=["POST"])
def api_feriados():
    payload = request.get_json(force=True, silent=True) or {}
    acao = payload.get("acao")
    db = get_db()
    if acao == "adicionar":
        data_f = payload.get("data", "").strip()
        nome_f = payload.get("nome", "").strip()
        if not data_f or not nome_f:
            abort(400)
        try:
            date.fromisoformat(data_f)
        except ValueError:
            abort(400)
        db.execute(
            "INSERT OR REPLACE INTO feriados (data, nome) VALUES (?, ?)",
            (data_f, nome_f),
        )
        db.commit()
        return jsonify({"ok": True})
    elif acao == "remover":
        data_f = payload.get("data", "").strip()
        db.execute("DELETE FROM feriados WHERE data = ?", (data_f,))
        db.commit()
        return jsonify({"ok": True})
    abort(400)


@app.route("/api/attendance", methods=["POST"])
def api_attendance():
    payload = request.get_json(force=True, silent=True) or {}
    try:
        member_id = int(payload["member_id"])
        event_date = payload["event_date"]
        event_type = payload["event_type"]
    except (KeyError, TypeError, ValueError):
        abort(400)
    status = payload.get("status")

    try:
        date.fromisoformat(event_date)
    except ValueError:
        abort(400)
    if event_type not in EVENT_KEYS:
        abort(400)
    if status not in (None, "presente", "faltou", "justificada"):
        abort(400)

    db = get_db()
    membro = db.execute("SELECT id FROM members WHERE id = ?", (member_id,)).fetchone()
    if membro is None:
        abort(404)

    if status is None:
        db.execute(
            "DELETE FROM attendance WHERE member_id = ? AND event_date = ? AND event_type = ?",
            (member_id, event_date, event_type),
        )
    else:
        db.execute(
            """
            INSERT INTO attendance (member_id, event_date, event_type, status, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT (member_id, event_date, event_type)
            DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
            """,
            (member_id, event_date, event_type, status),
        )
    db.commit()

    dias_letivos_lista = _dias_letivos(db)
    estado = _estado_jogo_membro(db, member_id, dias_letivos_lista)
    meta = game.meta_floracao(len(dias_letivos_lista))

    progresso, dias_ate_proximo = game.progresso_estagio(
        estado["g"], meta, estado["estagio"]
    )
    extras = _extras_dia(db, [member_id], event_date, set(dias_letivos_lista))[member_id]
    stats = _stats_membro(db, member_id, dias_letivos_lista)

    return jsonify({
        "ok": True,
        "jogo": {
            "id": member_id,
            "sementes": stats["sementes"],
            "g": estado["g"],
            "meta": meta,
            "estagio": estado["estagio"],
            "estagio_nome": game.STAGE_NAMES[estado["estagio"]],
            "vigor": estado["vigor"],
            "streak": estado["streak"],
            "chama": game.nivel_chama(estado["streak"]),
            "floresceu": estado["floresceu"],
            "frutos": estado["frutos"],
            "progresso": progresso,
            "dias_ate_proximo": dias_ate_proximo,
            "data": event_date,
            "dia_estado": extras["dia_estado"],
            "dia_status": extras["dia_status"],
            "aceso": extras["aceso"],
        },
    })


@app.route("/api/attendance/marcar_todos", methods=["POST"])
def api_marcar_todos():
    payload = request.get_json(force=True, silent=True) or {}
    event_date = payload.get("event_date")
    event_type = payload.get("event_type")
    status = payload.get("status", "presente")

    try:
        date.fromisoformat(event_date)
    except (TypeError, ValueError):
        abort(400)
    if event_type not in EVENT_KEYS:
        abort(400)
    if status not in ("presente", "faltou", "justificada"):
        abort(400)

    db = get_db()
    membros_ativos = db.execute("SELECT id FROM members WHERE active = 1").fetchall()
    for m in membros_ativos:
        db.execute(
            """
            INSERT INTO attendance (member_id, event_date, event_type, status, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT (member_id, event_date, event_type)
            DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
            """,
            (m["id"], event_date, event_type, status),
        )
    db.commit()

    dias_letivos_lista = _dias_letivos(db)
    membros = get_member_stats(db, dias_letivos_lista)
    return jsonify({"ok": True, "membros": membros})


@app.route("/api/membros", methods=["POST"])
def api_add_membro():
    payload = request.get_json(force=True, silent=True) or {}
    nome = (payload.get("name") or "").strip()
    if not nome:
        abort(400)
    db = get_db()
    db.execute("INSERT INTO members (name) VALUES (?)", (nome,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/membros/<int:member_id>", methods=["POST"])
def api_editar_membro(member_id):
    payload = request.get_json(force=True, silent=True) or {}
    db = get_db()
    membro = db.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    if membro is None:
        abort(404)
    if "name" in payload:
        nome = (payload.get("name") or "").strip()
        if nome:
            db.execute("UPDATE members SET name = ? WHERE id = ?", (nome, member_id))
    if "active" in payload:
        db.execute(
            "UPDATE members SET active = ? WHERE id = ?",
            (1 if payload.get("active") else 0, member_id),
        )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/membros/<int:member_id>/excluir", methods=["POST"])
def api_excluir_membro(member_id):
    payload = request.get_json(force=True, silent=True) or {}
    confirmar_nome = (payload.get("confirmar_nome") or "").strip()

    db = get_db()
    membro = db.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    if membro is None:
        abort(404)

    if confirmar_nome.lower() != membro["name"].lower():
        return jsonify({"ok": False, "erro": "Nome incorreto"}), 400

    backup_db_if_needed("-pre-exclusao")

    db.execute("DELETE FROM attendance WHERE member_id = ?", (member_id,))
    db.execute("DELETE FROM prenda_payments WHERE member_id = ?", (member_id,))
    db.execute("DELETE FROM compras WHERE member_id = ?", (member_id,))
    db.execute("DELETE FROM equipados WHERE member_id = ?", (member_id,))
    db.execute("DELETE FROM members WHERE id = ?", (member_id,))
    db.commit()

    return jsonify({"ok": True})


# ---------------------------------------------------------------- loja e album

SLOTS_EQUIPAVEIS = ("especie", "especie_2", "especie_3", "vaso", "companheiro", "acessorio")
GRUPOS_LOJA = [
    ("especie", "Plantas"),
    ("slot", "Canteiro"),
    ("vaso", "Vasos"),
    ("companheiro", "Companheiros"),
    ("acessorio", "Acessórios"),
]
PREVIEW_BASE = {
    "id": 0, "name": "", "estagio": 8, "estagio_nome": "Florindo", "vigor": "florida",
    "floresceu": False, "frutos": 0, "progresso": 0.5, "dia_status": "folga",
}


def _stats_membro(db, member_id, dias_letivos_lista=None):
    return next(
        (s for s in get_member_stats(db, dias_letivos_lista) if s["id"] == member_id), None
    )


def _posses_membro(db, member_id):
    rows = db.execute(
        "SELECT item_id FROM compras WHERE member_id = ? AND desfeita_em IS NULL", (member_id,)
    ).fetchall()
    return {r["item_id"] for r in rows}


def _membro_ou_404(db, member_id):
    if db.execute("SELECT 1 FROM members WHERE id = ?", (member_id,)).fetchone() is None:
        abort(404)


def _preview(item_id):
    it = catalog.item(item_id)
    v = catalog.montar_visual(set(), {})
    tipo = it["tipo"]
    if tipo == "especie":
        v["especie"], v["folha"] = item_id, it.get("folha", "p-folha")
    elif tipo in ("vaso", "companheiro", "acessorio"):
        v[tipo] = item_id
    elif tipo == "slot":
        n = 2 if item_id == "slot_2" else 3
        v["extras"] = [
            {"slot": k, "especie": "muda", "folha": "p-folha"} for k in range(2, n + 1)
        ]
    return {**PREVIEW_BASE, "visual": v}


def _contexto_loja(db, member_id):
    stats = _stats_membro(db, member_id) if member_id else None
    possui = _posses_membro(db, member_id) if stats else set()

    usados = {}
    if stats:
        v = stats["visual"]
        usados = {"especie": v["especie"], "vaso": v["vaso"],
                  "companheiro": v["companheiro"], "acessorio": v["acessorio"]}
        for e in v["extras"]:
            usados[f"especie_{e['slot']}"] = e["especie"]

    itens = []
    for it in catalog.ITENS:
        e = {**it, "preview": _preview(it["id"])}
        e["possui"] = bool(it.get("padrao")) or it["id"] in possui
        e["equipado_em"] = [s for s, iid in usados.items() if iid == it["id"]]
        if stats:
            ok, motivo = catalog.pode_comprar(it["id"], stats["sementes"], possui, stats["floresceu"])
            e["pode_comprar"], e["motivo"] = ok, motivo
        itens.append(e)

    compras = []
    if stats:
        for r in db.execute(
            "SELECT id, item_id, custo, comprado_em, desfeita_em FROM compras "
            "WHERE member_id = ? ORDER BY id DESC LIMIT 30", (member_id,)
        ).fetchall():
            it = catalog.item(r["item_id"]) or {"nome": r["item_id"]}
            compras.append({**dict(r), "nome": it["nome"]})

    membros = db.execute(
        "SELECT id, name FROM members WHERE active = 1 ORDER BY name COLLATE NOCASE"
    ).fetchall()
    compra_ativa = {}
    if stats:
        for r in db.execute(
            "SELECT id, item_id FROM compras WHERE member_id = ? AND desfeita_em IS NULL", (member_id,)
        ).fetchall():
            compra_ativa[r["item_id"]] = r["id"]
    return {
        "membros": [dict(m) for m in membros],
        "atual": stats,
        "compra_ativa": compra_ativa,
        "total_itens": len(catalog.ITENS),
        "itens": itens,
        "grupos": GRUPOS_LOJA,
        "plantas_liberadas": [1] + [n for n in (2, 3) if f"slot_{n}" in possui],
        "compras": compras,
    }


@app.route("/loja")
def loja_page():
    db = get_db()
    return render_template("loja.html", **_contexto_loja(db, request.args.get("m", type=int)))


@app.route("/album")
def album_page():
    db = get_db()
    return render_template("album.html", **_contexto_loja(db, request.args.get("m", type=int)))


def _ler_pedido():
    payload = request.get_json(force=True, silent=True) or {}
    try:
        member_id = int(payload.get("member_id"))
    except (TypeError, ValueError):
        abort(400)
    return payload, member_id


def _erro(msg, status=400):
    return jsonify({"ok": False, "erro": msg}), status


@app.route("/api/loja/comprar", methods=["POST"])
def api_loja_comprar():
    payload, member_id = _ler_pedido()
    item_id = payload.get("item_id")
    db = get_db()
    _membro_ou_404(db, member_id)

    stats = _stats_membro(db, member_id)
    ok, motivo = catalog.pode_comprar(
        item_id, stats["sementes"], _posses_membro(db, member_id), stats["floresceu"]
    )
    if not ok:
        return _erro(motivo)

    db.execute(
        "INSERT INTO compras (member_id, item_id, custo) VALUES (?, ?, ?)",
        (member_id, item_id, catalog.item(item_id)["preco"]),
    )
    db.commit()
    return jsonify({"ok": True, "sementes": _stats_membro(db, member_id)["sementes"]})


@app.route("/api/loja/equipar", methods=["POST"])
def api_loja_equipar():
    payload, member_id = _ler_pedido()
    slot = payload.get("slot")
    item_id = payload.get("item_id")
    db = get_db()
    _membro_ou_404(db, member_id)

    if slot not in SLOTS_EQUIPAVEIS:
        return _erro("Lugar inválido.")
    if item_id is None:
        db.execute("DELETE FROM equipados WHERE member_id = ? AND slot = ?", (member_id, slot))
    else:
        ok, motivo = catalog.pode_equipar(item_id, slot, _posses_membro(db, member_id))
        if not ok:
            return _erro(motivo)
        db.execute(
            "INSERT OR REPLACE INTO equipados (member_id, slot, item_id) VALUES (?, ?, ?)",
            (member_id, slot, item_id),
        )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/loja/desfazer", methods=["POST"])
def api_loja_desfazer():
    payload, member_id = _ler_pedido()
    try:
        compra_id = int(payload.get("compra_id"))
    except (TypeError, ValueError):
        abort(400)
    db = get_db()
    compra = db.execute(
        "SELECT * FROM compras WHERE id = ? AND member_id = ? AND desfeita_em IS NULL",
        (compra_id, member_id),
    ).fetchone()
    if compra is None:
        abort(404)

    item_id = compra["item_id"]
    if item_id == "slot_2" and "slot_3" in _posses_membro(db, member_id):
        return _erro("Desfaça a terceira plantinha antes.")

    db.execute("UPDATE compras SET desfeita_em = datetime('now') WHERE id = ?", (compra_id,))
    db.execute("DELETE FROM equipados WHERE member_id = ? AND item_id = ?", (member_id, item_id))
    if item_id in ("slot_2", "slot_3"):
        db.execute(
            "DELETE FROM equipados WHERE member_id = ? AND slot = ?",
            (member_id, "especie_" + item_id[-1]),
        )
    db.commit()
    return jsonify({"ok": True, "sementes": _stats_membro(db, member_id)["sementes"]})


if __name__ == "__main__":
    backup_db_if_needed()
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
