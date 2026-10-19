import math
import os
import shutil
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, abort, g, jsonify, redirect, render_template, request, url_for

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


def _sprint_atual(db):
    cfg = _get_config(db)
    s1 = date.fromisoformat(cfg.get("semana1_inicio", "2026-10-12"))
    sprint_semanas = int(cfg.get("sprint_semanas", "2"))
    hoje = date.today()
    delta = (hoje - s1).days
    sprint = max(1, math.ceil((delta / 7 + 1) / sprint_semanas))
    return sprint


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
    )


@app.route("/dashboard")
def dashboard():
    db = get_db()
    dias_letivos_lista = _dias_letivos(db)
    membros = get_member_stats(db, dias_letivos_lista)
    tendencia = get_overall_trend(db, dias=14)
    presencas = get_presencas_por_membro(db)
    meta = game.meta_floracao(len(dias_letivos_lista))

    ativos = [m for m in membros if m["active"]]
    _enriquecer_jardim(db, ativos, date.today().isoformat(), set(dias_letivos_lista))
    progresso_coletivo = 0
    if ativos and meta > 0:
        soma_g = sum(m["g"] for m in ativos)
        progresso_coletivo = round(soma_g / (len(ativos) * meta) * 100)

    dias_cheios_seq = _sequencia_dias_cheios(db, [m["id"] for m in ativos], dias_letivos_lista)

    return render_template(
        "dashboard.html",
        membros=membros,
        grafico_linha=build_line_chart(tendencia),
        tem_tendencia=len(tendencia) >= 2,
        presencas=presencas,
        meta=meta,
        total_dias=len(dias_letivos_lista),
        progresso_coletivo=progresso_coletivo,
        dias_cheios_seq=dias_cheios_seq,
        chama_time=game.nivel_chama(dias_cheios_seq),
        sprint_atual=_sprint_atual(db),
        stage_names=game.STAGE_NAMES,
    )


def _sequencia_dias_cheios(db, ativos_ids, dias_letivos_lista):
    if not ativos_ids:
        return 0
    seq = 0
    maior = 0
    for data in reversed(dias_letivos_lista):
        rows = db.execute(
            "SELECT member_id FROM attendance WHERE event_date = ? AND status = 'presente'",
            (data,),
        ).fetchall()
        presentes = {r["member_id"] for r in rows}
        if all(mid in presentes for mid in ativos_ids):
            seq += 1
            maior = max(maior, seq)
        else:
            if seq > 0:
                break
    return seq


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
