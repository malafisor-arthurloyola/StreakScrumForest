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
import qr_puro
import ata_fmt
import gitlab_sync

BASE_DIR = Path(__file__).resolve().parent

# Fuso do time. O PythonAnywhere roda em UTC: sem isto, das 21h a meia-noite de Brasilia o
# "hoje" do servidor (date.today, datetime.now) ja seria o dia seguinte, e a fala escrita a
# noite iria para a ata errada. Um TZ definido no servidor tem prioridade. O SQLite continua
# em UTC (datetime('now')), e o time.time() nao muda. No Windows nao ha tzset: vale o fuso do PC.
FUSO_PADRAO = "America/Sao_Paulo"
os.environ.setdefault("TZ", FUSO_PADRAO)
if hasattr(time, "tzset"):
    time.tzset()

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
    "fundador_ate": "2026-10-23",
    "idioma_ata": "pt",
    "gitlab_base_url": "",
    "gitlab_ultima_sync": "",
}

DEFAULT_FERIADOS = [
    ("2026-10-12", "N. Sra. Aparecida"),
    ("2026-11-02", "Finados"),
    ("2026-11-20", "Consciência Negra"),
]

# cor de cada fonte de sementes (repetida nos cards e no grafico da aba /sementes)
CORES_FONTE = {
    "eventos": "#c6f24e",
    "semanas": "#6db9ff",
    "marcos": "#ff9ec4",
    "dia_cheio": "#ffd35c",
    "floresceu": "#4fdb9b",
    "boas_vindas": "#ff8d76",
    "ata": "#b59bff",
    "relator": "#5fd6ff",
    "meta": "#ffb457",
}

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # em producao (HTTPS) defina COOKIE_SECURE=1; em http://localhost isso quebraria o login
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)
# app.secret_key e definido mais abaixo (apos _segredo), para a sessao assinada funcionar
# tanto com o codigo de acesso do grupo quanto com o login pessoal por PIN (/eu).


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


def _ip_lan():
    """IP da maquina na rede local, para o celular abrir o site. Nao faz conexao real:
    o connect UDP so escolhe a interface de saida. Retorna None se nao der para descobrir."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


# A sessao assinada (codigo de acesso e login pessoal por PIN) precisa de uma chave
# sempre definida, inclusive sem ACCESS_CODE. _segredo() e deterministico.
app.secret_key = _segredo()


# ------------------------------------------------------------ PIN pessoal (/eu)
# Guardamos apenas o hash do PIN com sal aleatorio (scrypt da stdlib), nunca o PIN.
PIN_MAX_ERROS = 5
PIN_BLOQUEIO_SEG = 600
PIN_TENTATIVAS = {}  # chave -> {"erros": int, "bloqueado_ate": float}


def criar_pin_hash(pin):
    """Retorna (hash_hex, salt_hex) para um PIN de 4 digitos. scrypt e da stdlib."""
    salt = os.urandom(16)
    h = hashlib.scrypt(pin.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
    return h.hex(), salt.hex()


def verificar_pin(pin, hash_hex, salt_hex):
    if not hash_hex or not salt_hex:
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        h = hashlib.scrypt(pin.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(h.hex(), hash_hex)


def _pin_valido(pin):
    return isinstance(pin, str) and len(pin) == 4 and pin.isdigit()


def _pin_bloqueado(chaves):
    agora = time.time()
    for k in chaves:
        est = PIN_TENTATIVAS.get(k)
        if est and est["bloqueado_ate"] > agora:
            return True
    return False


def _pin_registrar_erro(chaves):
    agora = time.time()
    for k in chaves:
        est = PIN_TENTATIVAS.get(k, {"erros": 0, "bloqueado_ate": 0})
        est["erros"] += 1
        if est["erros"] >= PIN_MAX_ERROS:
            est["erros"] = 0
            est["bloqueado_ate"] = agora + PIN_BLOQUEIO_SEG
        PIN_TENTATIVAS[k] = est


def _pin_limpar(chaves):
    for k in chaves:
        PIN_TENTATIVAS.pop(k, None)


# ------------------------------------------------------------ codigo do QR de presenca
# O codigo do evento do dia e um HMAC curto de SECRET_KEY sobre data|evento|janela de
# 10 min. Aceitamos a janela atual e a anterior, para o QR nao "virar" na troca de janela.
JANELA_QR_SEG = 600


def _codigo_evento(data_str, evento, janela):
    msg = f"{data_str}|{evento}|{janela}".encode("utf-8")
    assinatura = hmac.new(_segredo().encode("utf-8"), msg, hashlib.sha256).hexdigest()
    # codigo curto e legivel: evento + 8 hex. A data/evento sao recuperados por tentativa.
    return assinatura[:10]


def codigo_do_evento(data_str, evento, agora=None):
    """Codigo atual do evento naquele dia (janela de 10 min)."""
    agora = agora if agora is not None else time.time()
    janela = int(agora // JANELA_QR_SEG)
    return _codigo_evento(data_str, evento, janela)


def verificar_codigo_evento(codigo, data_str, evento, agora=None):
    """True se `codigo` corresponde ao evento/dia na janela atual ou na anterior."""
    agora = agora if agora is not None else time.time()
    janela = int(agora // JANELA_QR_SEG)
    for j in (janela, janela - 1):
        if hmac.compare_digest(codigo, _codigo_evento(data_str, evento, j)):
            return True
    return False


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
    # O snapshot do GitLab vem do PC do dono (script), sem cookie e sem X-Requested-With.
    # Ele NAO passa pela sessao: autentica sozinho so pelo Bearer SYNC_TOKEN. Por isso sai
    # daqui antes das checagens de sessao. Nenhuma outra rota /api ganha esse passe.
    if request.endpoint == "api_gitlab_snapshot":
        return None
    if session.get("auth") != _assinatura():
        if request.path.startswith("/api/"):
            return jsonify({"ok": False, "erro": "Acesso negado."}), 401
        return redirect(url_for("entrar", next=request.full_path.rstrip("?")))
    if request.method == "POST" and request.path.startswith("/api/") \
            and request.headers.get("X-Requested-With") != "fetch":
        return jsonify({"ok": False, "erro": "Pedido inválido."}), 403
    return None


# ------------------------------------------------------------ papeis: administrador x visitante
# Quem pode ALTERAR o que e compartilhado (presenca de todos, ata, membros, calendario,
# metas, QR, download do banco):
#   - quem esta no computador onde o site roda (acesso local, em localhost);
#   - o Scrum (relator) de HOJE, entrando no celular com o PIN;
#   - quem entrou com o ADMIN_CODE (para quando o site esta publicado).
# Os demais so VEEM. Cada pessoa continua dona da propria loja, da propria fala e da propria
# presenca (via /eu e QR).
ENDPOINTS_ADMIN = {
    "api_metas", "api_metas_premio", "api_holofote", "api_calendario", "api_feriados", "api_attendance", "api_marcar_todos",
    "api_add_membro", "api_editar_membro", "api_excluir_membro",
    "qr_page", "baixar_banco",
}
MSG_SO_ADMIN = "Só o administrador (o Scrum do dia ou quem está no computador) pode fazer isso."


def _requisicao_local():
    """True se o pedido vem do proprio computador (localhost), sem proxy no meio.
    ADMIN_LOCAL=0 desliga isso (ex.: se o site rodar num servidor compartilhado)."""
    if os.environ.get("ADMIN_LOCAL", "1") == "0":
        return False
    if request.headers.get("X-Forwarded-For") or request.headers.get("X-Real-IP"):
        return False
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return False
    host = request.host
    host = host[1:host.index("]")] if host.startswith("[") else host.split(":")[0]
    return host in ("localhost", "127.0.0.1", "::1")


def _papel_admin():
    """'codigo' | 'computador' | 'scrum' | None (visitante)."""
    if session.get("admin"):
        return "codigo"
    if _requisicao_local():
        return "computador"
    mid = _eu_id()
    if mid is not None:
        hoje = date.today().isoformat()
        r = get_db().execute(
            "SELECT 1 FROM atas WHERE data = ? AND relator_id = ? LIMIT 1", (hoje, mid)
        ).fetchone()
        if r:
            return "scrum"
    return None


def eh_admin():
    return _papel_admin() is not None


def _pode_editar_ata(db, data_str, tipo):
    """Edita a ata: o administrador, ou o relator DAQUELA ata (logado com o PIN, em qualquer
    aparelho, inclusive no PC), seja ela de hoje ou de outro dia."""
    if eh_admin():
        return True
    mid = _eu_id()
    if mid is None:
        return False
    r = db.execute("SELECT relator_id FROM atas WHERE data = ? AND tipo = ?", (data_str, tipo)).fetchone()
    return bool(r and r["relator_id"] == mid)


@app.before_request
def guarda_de_admin():
    if request.endpoint in ENDPOINTS_ADMIN and not eh_admin():
        if request.path.startswith("/api/") or request.method != "GET":
            return jsonify({"ok": False, "erro": MSG_SO_ADMIN}), 403
        return render_template("so_admin.html"), 403
    return None


@app.context_processor
def contexto_papel():
    try:
        papel = _papel_admin()
    except Exception:
        papel = None
    return {
        "admin": papel is not None,
        "papel_admin": papel,
        "admin_codigo_ativo": bool(os.environ.get("ADMIN_CODE")),
        "eu_id": _eu_id(),
    }


@app.route("/admin/entrar", methods=["GET", "POST"])
def admin_entrar():
    codigo = os.environ.get("ADMIN_CODE", "")
    destino = _destino_seguro(request.values.get("next"))
    erro, status = None, 200
    if request.method == "POST":
        if not codigo:
            erro, status = "O código de administrador não está configurado neste servidor.", 400
        else:
            chave = "adm:" + _ip()
            agora = time.time()
            estado = TENTATIVAS.get(chave, {"erros": 0, "bloqueado_ate": 0})
            if estado["bloqueado_ate"] > agora:
                erro, status = "Muitas tentativas. Tente de novo em alguns minutos.", 429
            else:
                tentativa = (request.form.get("codigo") or "").encode("utf-8")
                if hmac.compare_digest(tentativa, codigo.encode("utf-8")):
                    TENTATIVAS.pop(chave, None)
                    session["admin"] = True
                    session.permanent = True
                    return redirect(destino)
                estado["erros"] += 1
                if estado["erros"] >= MAX_ERROS:
                    estado["erros"] = 0
                    estado["bloqueado_ate"] = agora + BLOQUEIO_SEG
                    erro, status = "Muitas tentativas. Tente de novo em alguns minutos.", 429
                else:
                    erro, status = "Código incorreto.", 401
                TENTATIVAS[chave] = estado
    return render_template("admin_entrar.html", erro=erro, destino=destino,
                           configurado=bool(codigo)), status


@app.route("/admin/sair")
def admin_sair():
    session.pop("admin", None)
    return redirect(url_for("home"))


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

        CREATE TABLE IF NOT EXISTS metas_premio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            prazo TEXT NOT NULL,
            sementes INTEGER NOT NULL,
            para_time INTEGER NOT NULL DEFAULT 0,
            cumprida_em TEXT,
            criada_em TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS metas_premio_membros (
            meta_id INTEGER NOT NULL REFERENCES metas_premio(id) ON DELETE CASCADE,
            member_id INTEGER NOT NULL REFERENCES members(id),
            PRIMARY KEY (meta_id, member_id)
        );

        CREATE TABLE IF NOT EXISTS atas (
            data TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('daily', 'fechamento')),
            relator_id INTEGER REFERENCES members(id),
            bloqueios TEXT NOT NULL DEFAULT '',
            bloqueios_resolvidos INTEGER NOT NULL DEFAULT 0,
            quadro_atualizado INTEGER NOT NULL DEFAULT 0,
            atualizada_em TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (data, tipo)
        );

        CREATE TABLE IF NOT EXISTS ata_falas (
            data TEXT NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('daily', 'fechamento')),
            member_id INTEGER NOT NULL REFERENCES members(id),
            feito TEXT NOT NULL DEFAULT '',
            planejado TEXT NOT NULL DEFAULT '',
            atualizada_em TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (data, tipo, member_id)
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

    _migrar_membros_tipo(db)

    _migrar_gitlab(db)

    db.commit()
    db.close()


def _migrar_membros_tipo(db):
    """Adiciona members.tipo ('equipe' | 'convidado') de forma aditiva e idempotente.
    Convidados ficam fora de tudo que e coletivo; o default mantem todo mundo na equipe."""
    colunas = {r["name"] for r in db.execute("PRAGMA table_info(members)").fetchall()}
    if "tipo" not in colunas:
        db.execute(
            "ALTER TABLE members ADD COLUMN tipo TEXT NOT NULL DEFAULT 'equipe'"
        )
    _migrar_membros_pin(db)


def _migrar_membros_pin(db):
    """Adiciona members.pin_hash e pin_salt (aditivo, idempotente). Guardamos so o hash."""
    colunas = {r["name"] for r in db.execute("PRAGMA table_info(members)").fetchall()}
    if "pin_hash" not in colunas:
        db.execute("ALTER TABLE members ADD COLUMN pin_hash TEXT")
    if "pin_salt" not in colunas:
        db.execute("ALTER TABLE members ADD COLUMN pin_salt TEXT")


def _migrar_gitlab(db):
    """Fase 6 (integracao com o GitLab, so leitura). Tudo aditivo e idempotente:
      - members.gitlab_user: o usuario da pessoa no GitLab (para casar os cards);
      - ata_falas.review: o campo "em revisao" da daily (NUNCA rende semente);
      - gitlab_cards: o retrato do quadro (Doing / Waiting review) empurrado pelo script.
    As configs gitlab_base_url e gitlab_ultima_sync entram pelo DEFAULT_CONFIG (INSERT OR IGNORE)."""
    cols_membros = {r["name"] for r in db.execute("PRAGMA table_info(members)").fetchall()}
    if "gitlab_user" not in cols_membros:
        db.execute("ALTER TABLE members ADD COLUMN gitlab_user TEXT")
    cols_falas = {r["name"] for r in db.execute("PRAGMA table_info(ata_falas)").fetchall()}
    if "review" not in cols_falas:
        db.execute("ALTER TABLE ata_falas ADD COLUMN review TEXT NOT NULL DEFAULT ''")
    if "bloqueios" not in cols_falas:
        db.execute("ALTER TABLE ata_falas ADD COLUMN bloqueios TEXT NOT NULL DEFAULT ''")
    if "origem" not in cols_falas:
        # quem escreveu a fala por ultimo: 'relator' (o Scrum preencheu pela pessoa) ou 'proprio'.
        # Vazio = fala anterior a esta regra (conta para o relator, por boa-fe).
        db.execute("ALTER TABLE ata_falas ADD COLUMN origem TEXT NOT NULL DEFAULT ''")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS gitlab_cards (
            iid INTEGER NOT NULL,
            coluna TEXT NOT NULL CHECK (coluna IN ('doing', 'review', 'em_revisao', 'backlog', 'done')),
            usuario TEXT NOT NULL,
            titulo TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            labels TEXT NOT NULL DEFAULT '',
            atualizado_em TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (iid, coluna, usuario)
        )
        """
    )
    _migrar_gitlab_cards_colunas(db)
    # milestone de cada card (a sprint a que ele pertence): colunas aditivas e idempotentes
    cols_cards = {r["name"] for r in db.execute("PRAGMA table_info(gitlab_cards)").fetchall()}
    for coluna in ("milestone", "milestone_inicio", "milestone_fim"):
        if coluna not in cols_cards:
            db.execute(f"ALTER TABLE gitlab_cards ADD COLUMN {coluna} TEXT NOT NULL DEFAULT ''")
    db.execute("CREATE INDEX IF NOT EXISTS ix_gitlab_cards_usuario ON gitlab_cards (usuario)")
    db.execute(
        "CREATE TABLE IF NOT EXISTS gitlab_usuarios ("
        "username TEXT PRIMARY KEY, nome TEXT NOT NULL DEFAULT '')"
    )


def _gitlab_cards_aceita_novas_colunas(db):
    """True se a tabela gitlab_cards ja aceita as colunas novas (backlog/done/em_revisao).
    Testa inserindo e desfazendo um registro de sonda dentro de um savepoint."""
    db.execute("SAVEPOINT sonda_gl")
    try:
        db.execute("INSERT INTO gitlab_cards (iid, coluna, usuario) VALUES (-999, 'backlog', '__sonda__')")
    except sqlite3.IntegrityError:
        db.execute("ROLLBACK TO sonda_gl")
        db.execute("RELEASE sonda_gl")
        return False
    db.execute("ROLLBACK TO sonda_gl")       # desfaz a sonda (nunca grava de verdade)
    db.execute("RELEASE sonda_gl")
    return True


def _migrar_gitlab_cards_colunas(db):
    """Amplia o CHECK de gitlab_cards para aceitar backlog/done/em_revisao (Fase 6c).

    No SQLite nao da para alterar um CHECK: e preciso recriar a tabela (criar a nova, copiar,
    trocar). Faz isso de forma IDEMPOTENTE (so quando a tabela antiga ainda nao aceita as
    colunas novas) e em transacao, sem perder dados. Nao toca em gitlab_usuarios nem em
    members.gitlab_user. Rodar duas vezes nao quebra."""
    if _gitlab_cards_aceita_novas_colunas(db):
        return
    db.executescript(
        """
        CREATE TABLE gitlab_cards_nova (
            iid INTEGER NOT NULL,
            coluna TEXT NOT NULL CHECK (coluna IN ('doing', 'review', 'em_revisao', 'backlog', 'done')),
            usuario TEXT NOT NULL,
            titulo TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            labels TEXT NOT NULL DEFAULT '',
            atualizado_em TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (iid, coluna, usuario)
        );
        INSERT INTO gitlab_cards_nova (iid, coluna, usuario, titulo, url, labels, atualizado_em)
            SELECT iid, coluna, usuario, titulo, url, labels, atualizado_em FROM gitlab_cards;
        DROP TABLE gitlab_cards;
        ALTER TABLE gitlab_cards_nova RENAME TO gitlab_cards;
        """
    )


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


def _dia_cheio_na_data(db, data_str, dias_letivos_lista):
    """True se `data_str` e um dia cheio do time (todos os ativos presentes, ninguem
    faltou) e cai em dia letivo. Usa a mesma regra de game.dia_cheio."""
    if data_str not in set(dias_letivos_lista):
        return False
    ativos_ids = [
        r["id"] for r in db.execute(
            "SELECT id FROM members WHERE active = 1 AND COALESCE(tipo, 'equipe') = 'equipe'"
        ).fetchall()
    ]
    glob = _registros_globais(db)
    cheios = game.dia_cheio(ativos_ids, {data_str: glob.get(data_str, {})})
    return data_str in cheios


def _registros_globais(db):
    """{data: {member_id: {'presente': True, ...}}} em uma unica consulta."""
    glob = {}
    for r in db.execute("SELECT member_id, event_date, event_type, status FROM attendance").fetchall():
        reg = glob.setdefault(r["event_date"], {}).setdefault(r["member_id"], {})
        reg[r["status"]] = True
        if r["status"] == "presente":
            reg.setdefault("eventos", set()).add(r["event_type"])
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


def _e_equipe(membro_row):
    """True se o membro e da equipe (nao convidado). Tolera linhas antigas sem a
    coluna tipo, tratando-as como equipe."""
    try:
        tipo = membro_row["tipo"]
    except (KeyError, IndexError):
        return True
    return (tipo or "equipe") == "equipe"


def _relatadas_por_ata(db, dias_letivos_lista):
    """{relator_id: {(data, tipo): [nomes de quem ele preencheu]}}: falas de OUTRAS pessoas que o
    relator preencheu naquela ata. So conta a fala que o relator escreveu pela pessoa (origem
    'relator'); falas antigas, sem marca (origem ''), contam. Texto vazio nao conta."""
    saida = {}
    if not dias_letivos_lista:
        return saida
    marc = ",".join("?" * len(dias_letivos_lista))
    for r in db.execute(
        f"SELECT a.relator_id AS rid, f.data AS data, f.tipo AS tipo, m.name AS nome "
        f"FROM ata_falas f JOIN atas a ON a.data = f.data AND a.tipo = f.tipo "
        f"JOIN members m ON m.id = f.member_id "
        f"WHERE a.relator_id IS NOT NULL AND f.member_id <> a.relator_id AND f.data IN ({marc}) "
        f"AND (TRIM(f.feito) <> '' OR TRIM(f.planejado) <> '') AND f.origem IN ('relator', '') "
        f"ORDER BY f.data, f.tipo, m.name",
        tuple(dias_letivos_lista),
    ).fetchall():
        saida.setdefault(r["rid"], {}).setdefault((r["data"], r["tipo"]), []).append(r["nome"])
    return saida


def _contagem_atas(db, dias_letivos_lista):
    """Por membro: (1) numero de atas (em DIA LETIVO) com a fala preenchida (feito OU
    planejado nao vazio) e (2) numero de falas de OUTRAS pessoas que ele preencheu como
    relator, com LIMITE por ata (game.SEED_RELATOR_MAX_POR_ATA). A fala dele mesmo conta so
    no item 1. Fim de semana, feriado ou dia fora do periodo nao rende nada."""
    com_fala, relatadas = {}, {}
    if not dias_letivos_lista:
        return com_fala, relatadas
    marc = ",".join("?" * len(dias_letivos_lista))
    for r in db.execute(
        f"SELECT member_id, COUNT(*) AS n FROM ata_falas "
        f"WHERE data IN ({marc}) AND (TRIM(feito) <> '' OR TRIM(planejado) <> '') "
        f"GROUP BY member_id",
        tuple(dias_letivos_lista),
    ).fetchall():
        com_fala[r["member_id"]] = r["n"]
    for rid, por_ata in _relatadas_por_ata(db, dias_letivos_lista).items():
        relatadas[rid] = sum(min(len(nomes), game.SEED_RELATOR_MAX_POR_ATA) for nomes in por_ata.values())
    return com_fala, relatadas


def _falas_do_membro(db, member_id, dias_letivos_lista):
    """[(data, tipo)] das atas em que o membro tem fala preenchida (dias letivos)."""
    if not dias_letivos_lista:
        return []
    marc = ",".join("?" * len(dias_letivos_lista))
    return [
        (r["data"], r["tipo"]) for r in db.execute(
            f"SELECT data, tipo FROM ata_falas WHERE member_id = ? AND data IN ({marc}) "
            f"AND (TRIM(feito) <> '' OR TRIM(planejado) <> '')",
            (member_id, *dias_letivos_lista),
        ).fetchall()
    ]


def _extrato_do_membro(db, member_id, dias_letivos_lista, semanas, glob, cheios, meta):
    """Extrato (ganhos e gastos) de um membro, para a aba Sementes."""
    reg = _reg_membro(glob, member_id)
    ganhos = game.extrato_sementes(
        dias_letivos_lista, semanas, reg, meta, dias_cheios=cheios,
        falas=_falas_do_membro(db, member_id, dias_letivos_lista),
        relatadas=_relatadas_por_ata(db, dias_letivos_lista).get(member_id, {}),
        metas=_premios_de_metas_do_membro(db, member_id),
    )
    gastos = []
    for r in db.execute(
        "SELECT item_id, custo, comprado_em FROM compras WHERE member_id = ? AND desfeita_em IS NULL "
        "ORDER BY comprado_em", (member_id,)
    ).fetchall():
        it = catalog.item(r["item_id"]) or {}
        gastos.append({"data": (r["comprado_em"] or "")[:10], "fonte": "gasto", "rotulo": "Compra na loja",
                       "valor": -int(r["custo"]), "detalhe": it.get("nome", r["item_id"])})
    todas = sorted(ganhos + gastos, key=lambda x: (x["data"], 0 if x["valor"] > 0 else 1))
    acumulado = 0
    for linha in todas:
        acumulado += linha["valor"]
        linha["acumulado"] = acumulado
    total_ganho = sum(x["valor"] for x in ganhos)
    total_gasto = -sum(x["valor"] for x in gastos)
    return {
        "linhas": list(reversed(todas)),          # mais recente primeiro
        "ganho": total_ganho, "gasto": total_gasto, "saldo": max(total_ganho - total_gasto, 0),
    }


def _coluna(row, nome):
    """Le uma coluna opcional de um sqlite3.Row sem quebrar se ela nao existir."""
    try:
        return row[nome]
    except (KeyError, IndexError):
        return None


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
    # Dia cheio e um calculo de time: so conta a equipe, nunca os convidados.
    ativos_ids = [m["id"] for m in membros if m["active"] and _e_equipe(m)]
    cheios = game.dia_cheio(ativos_ids, {d: v for d, v in glob.items() if d in dias_set})
    gastos = _gastos_por_membro(db)
    posses, equip = _posses_e_equipados(db)
    fundador_ate = _get_config(db).get("fundador_ate", "2026-10-23")
    atas_com_fala, falas_relatadas = _contagem_atas(db, dias_letivos_lista)
    metas_premio, equipe_ids = _metas_premio(db), _ids_equipe(db)

    resultado = []
    for m in membros:
        reg = {d: v[m["id"]] for d, v in glob.items() if m["id"] in v}
        estado = game.calcular_membro(dias_letivos_lista, reg, meta)
        fundador = game.e_fundador(reg, fundador_ate)
        progresso, dias_ate_proximo = game.progresso_estagio(
            estado["g"], meta, estado["estagio"]
        )
        ganho = game.calcular_sementes(
            dias_letivos_lista, semanas, reg, estado["floresceu"], dias_cheios=cheios,
            atas_com_fala=atas_com_fala.get(m["id"], 0),
            falas_relatadas=falas_relatadas.get(m["id"], 0),
            bonus_metas=sum(x["valor"] for x in game.premios_de_metas(metas_premio, m["id"], equipe_ids)),
        )
        gasto = gastos.get(m["id"], 0)
        resultado.append({
            "sementes": max(ganho["total"] - gasto, 0),
            "sementes_ganhas": ganho["total"],
            "sementes_gastas": gasto,
            "visual": catalog.montar_visual(posses.get(m["id"], set()), equip.get(m["id"], {}), fundador),
            "fundador": fundador,
            "progresso": progresso,
            "dias_ate_proximo": dias_ate_proximo,
            "chama": game.nivel_chama(estado["streak"]),
            "id": m["id"],
            "name": m["name"],
            "active": bool(m["active"]),
            "convidado": not _e_equipe(m),
            "tem_pin": bool(_coluna(m, "pin_hash")),
            "gitlab_user": _coluna(m, "gitlab_user") or "",
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


NOMES_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


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
        FROM attendance a
        JOIN members m ON m.id = a.member_id AND COALESCE(m.tipo, 'equipe') = 'equipe'
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
        WHERE m.active = 1 AND COALESCE(m.tipo, 'equipe') = 'equipe'
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

    ativos_visiveis = [s for s in stats_list if s["active"]]
    jardim = _enriquecer_jardim(
        db, [s for s in ativos_visiveis if not s["convidado"]], data_str, set(dias_letivos_lista)
    )
    jardim_convidados = _enriquecer_jardim(
        db, [s for s in ativos_visiveis if s["convidado"]], data_str, set(dias_letivos_lista)
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
        jardim_convidados=jardim_convidados,
        data_extenso=_data_extenso(data_atual),
        dia_n=dias_letivos_lista.index(data_str) + 1 if e_letivo else None,
        dias_total=len(dias_letivos_lista),
        marcos_ids=_marcos_liberados(stats_list, game.meta_floracao(len(dias_letivos_lista))),
        panorama=_panorama(db, _base_coletivo(db), request.args.get("p", "projeto")),
        dia_cheio_inicial=_dia_cheio_na_data(db, data_str, dias_letivos_lista),
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
    # "ativos" e o time: tudo que e coletivo (dia cheio, jardim coletivo, metas, destaques,
    # panorama, trilha, bosque, resumo da sprint) olha so a equipe. Convidados ficam de fora.
    ativos = [m for m in membros if m["active"] and not m["convidado"]]
    ativos_ids = [m["id"] for m in ativos]
    convidados = [m for m in membros if m["active"] and m["convidado"]]
    glob = _registros_globais(db)
    cheios = game.dia_cheio(ativos_ids, {d: v for d, v in glob.items() if d in dias_set})
    return {
        "dias": dias, "dias_set": dias_set, "meta": game.meta_floracao(len(dias)),
        "membros": membros, "ativos": ativos, "ativos_ids": ativos_ids,
        "convidados": convidados,
        "glob": glob, "cheios": cheios, "sprints": _cfg_sprints(db),
        "hoje": date.today().isoformat(),
    }


def _progresso_coletivo(ativos, meta):
    if not ativos or meta <= 0:
        return 0
    return round(sum(m["g"] for m in ativos) / (len(ativos) * meta) * 100)


def _marcos_liberados(stats_list, meta):
    # Jardim coletivo: so a equipe conta para o progresso dos marcos.
    ativos = [s for s in stats_list if s["active"] and not s["convidado"]]
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
    nomes_feriado = {f["data"]: f["nome"] for f in _get_feriados_lista(db)}
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
        for j in range(7):
            dd = seg + timedelta(days=j)
            ds = dd.isoformat()
            rotulo = f"{NOMES_SEMANA[j]} {dd.day:02d}/{dd.month:02d}"
            if ds in nomes_feriado:
                rotulo += f" ({nomes_feriado[ds]})"
            letivo = ds in ctx["dias_set"]
            presentes = sum(
                1 for m in ativos if ctx["glob"].get(ds, {}).get(m["id"], {}).get("presente")
            )
            if letivo and ds <= hoje:
                dias_do_periodo.append(ds)
            if not letivo:
                estado = "feriado" if ds in nomes_feriado else ("fds" if j >= 5 else "folga")
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
                    "estado": (_estado_dia(regs[m["id"]].get(ds, {}), ds, hoje, ctx["dias_set"])
                               if letivo else dias_time[-1]["estado"]),
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

    # Proximos marcos de sequencia, em ordem alfabetica (sem expor quem esta atras).
    # So destaque positivo: barra ate o proximo marco de cada pessoa.
    proximos_marcos = []
    for m in sorted(ctx["ativos"], key=lambda x: x["name"].lower()):
        prox = game.proximo_marco(m["streak"])
        if prox["feito"]:
            pct = 100
        else:
            pct = round(100 * m["streak"] / prox["alvo"]) if prox["alvo"] else 0
        proximos_marcos.append({
            "id": m["id"], "name": m["name"], "streak": m["streak"],
            "proximo": prox, "pct": pct,
        })

    return {
        "progresso_coletivo": progresso,
        "marcos": game.marcos_coletivos(progresso),
        "marcos_ids": _marcos_liberados(ctx["membros"], ctx["meta"]),
        "dias_cheios_seq": seq,
        "chama_time": game.nivel_chama(seq),
        "proximos_marcos": proximos_marcos,
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
    _enriquecer_jardim(db, ctx["convidados"], ctx["hoje"], ctx["dias_set"])
    tendencia = get_overall_trend(db, dias=14)
    return render_template(
        "dashboard.html",
        membros=ctx["membros"],
        convidados=ctx["convidados"],
        grafico_linha=build_line_chart(tendencia),
        tem_tendencia=len(tendencia) >= 2,
        presencas=get_presencas_por_membro(db),
        meta=ctx["meta"],
        total_dias=len(ctx["dias"]),
        stage_names=game.STAGE_NAMES,
        desafios=_metas_premio(db),
        equipe=[m for m in ctx["ativos"]],
        seed_meta_max=game.SEED_META_MAX,
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


def _metas_premio(db):
    """Metas personalizadas (com recompensa em sementes), com os escolhidos de cada uma."""
    metas = []
    for r in db.execute("SELECT * FROM metas_premio ORDER BY prazo, id").fetchall():
        m = dict(r)
        m["membros"] = [x["member_id"] for x in db.execute(
            "SELECT member_id FROM metas_premio_membros WHERE meta_id = ?", (r["id"],)).fetchall()]
        m["no_prazo"] = bool(m["cumprida_em"]) and m["cumprida_em"] <= m["prazo"]
        metas.append(m)
    return metas


def _ids_equipe(db):
    return [m["id"] for m in db.execute("SELECT * FROM members WHERE active = 1").fetchall() if _e_equipe(m)]


def _premios_de_metas_do_membro(db, member_id, metas=None, equipe=None):
    return game.premios_de_metas(
        _metas_premio(db) if metas is None else metas, member_id,
        _ids_equipe(db) if equipe is None else equipe)


HOLOFOTE_VALE_SEGUNDOS = 3 * 3600      # esquecido ligado? apaga sozinho depois de 3 horas


@app.route("/api/holofote", methods=["POST"])
def api_holofote():
    """Quem conduz a rodada de fala acende (ou apaga) o holofote na planta de quem esta falando.
    modo: 'celular' (padrao: a propria pessoa preenche no celular dela) ou 'scrum' (o Scrum preenche por ela)."""
    p = request.get_json(force=True, silent=True) or {}
    mid = _int_ou_none(p.get("member_id"))
    modo = p.get("modo") if p.get("modo") in ("celular", "scrum") else "celular"
    tipo = p.get("tipo") if p.get("tipo") in ATA_TIPOS else "daily"
    db = get_db()
    if mid is not None and not db.execute("SELECT 1 FROM members WHERE id = ? AND active = 1", (mid,)).fetchone():
        return _erro("Pessoa inválida.")
    valores = [("holofote_membro", "" if mid is None else str(mid)), ("holofote_modo", modo), ("holofote_tipo", tipo)]
    # a ordem sorteada fica no servidor, para todas as telas mostrarem quem vem a seguir e outro
    # aparelho do Scrum poder continuar a rodada. Sem "ordem" no pedido, a ordem gravada continua;
    # apagar o holofote (encerrar a rodada) apaga a ordem junto.
    if mid is None:
        valores.append(("holofote_ordem", ""))
    elif "ordem" in p:
        ordem = _ordem_valida(db, p.get("ordem"))
        if ordem is None or mid not in ordem:
            return _erro("Ordem da rodada inválida.")
        valores.append(("holofote_ordem", ",".join(str(x) for x in ordem)))
    for chave, valor in valores:
        db.execute("INSERT INTO config (chave, valor) VALUES (?, ?) ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor",
                   (chave, valor))
    db.execute("INSERT INTO config (chave, valor) VALUES ('holofote_em', datetime('now')) "
               "ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor")
    db.commit()
    return jsonify({"ok": True, "member_id": mid, "modo": modo, "tipo": tipo})


HOLOFOTE_ORDEM_MAX = 60


def _ordem_valida(db, ordem):
    """Lista de ids de pessoas ativas, sem repetir, na ordem do sorteio; None se o pedido for invalido."""
    if not isinstance(ordem, list) or not 0 < len(ordem) <= HOLOFOTE_ORDEM_MAX:
        return None
    ids = [_int_ou_none(x) for x in ordem]
    if None in ids or len(set(ids)) != len(ids):
        return None
    ativos = {r["id"] for r in db.execute("SELECT id FROM members WHERE active = 1").fetchall()}
    return ids if set(ids) <= ativos else None


def _holofote_ordem(db, mid):
    """[{id, nome}] da rodada em andamento e a posicao de `mid` nela; ([], None) sem ordem gravada."""
    row = db.execute("SELECT valor FROM config WHERE chave = 'holofote_ordem'").fetchone()
    ids = [_int_ou_none(x) for x in (row["valor"] if row else "").split(",") if x.strip()]
    nomes = {r["id"]: r["name"] for r in db.execute("SELECT id, name FROM members").fetchall()}
    ids = [x for x in ids if x in nomes]          # alguem excluido no meio da rodada sai da lista
    if mid is None or mid not in ids:
        return [], None
    return [{"id": x, "nome": nomes[x]} for x in ids], ids.index(mid)


def _holofote_atual(db):
    """(member_id, modo, tipo) do holofote aceso agora; member_id None se apagado ou esquecido."""
    row = db.execute(
        "SELECT (SELECT valor FROM config WHERE chave = 'holofote_membro') AS m, "
        "(SELECT valor FROM config WHERE chave = 'holofote_modo') AS modo, "
        "(SELECT valor FROM config WHERE chave = 'holofote_tipo') AS tipo, "
        "CAST(strftime('%s', 'now') AS INTEGER) - CAST(strftime('%s', (SELECT valor FROM config WHERE chave = 'holofote_em')) AS INTEGER) AS idade"
    ).fetchone()
    mid = _int_ou_none(row["m"]) if row and row["m"] else None
    if mid is not None and (row["idade"] is None or row["idade"] > HOLOFOTE_VALE_SEGUNDOS):
        mid = None
    modo = row["modo"] if row and row["modo"] in ("celular", "scrum") else "celular"
    tipo = row["tipo"] if row and row["tipo"] in ATA_TIPOS else "daily"
    return mid, modo, tipo


@app.route("/api/holofote", methods=["GET"])
def api_holofote_ver():
    """Estado do holofote para todas as telas: quem esta falando, quem preenche e o que ja foi escrito.
    Com ?comjogo=1 devolve tambem o estado do jogo da pessoa (para a tela acender a chama dela)."""
    db = get_db()
    mid, modo, tipo = _holofote_atual(db)
    hoje = date.today().isoformat()
    resp = {"ok": True, "member_id": mid, "modo": modo, "data": hoje, "tipo": tipo,
            "eu": _eu_id(), "pode_scrum": False, "nome": "", "status": "",
            "falas": {"feito": "", "planejado": "", "review": ""}, "ordem": [], "pos": None}
    if mid is not None:
        resp["ordem"], resp["pos"] = _holofote_ordem(db, mid)
        resp["pode_scrum"] = bool(_pode_editar_ata(db, hoje, tipo))
        m = db.execute("SELECT name FROM members WHERE id = ?", (mid,)).fetchone()
        resp["nome"] = m["name"] if m else ""
        resp["status"] = _status_do_evento(db, hoje, ATA_EVENTO[tipo]).get(mid) or ""
        f = db.execute("SELECT feito, planejado, review FROM ata_falas WHERE data = ? AND tipo = ? AND member_id = ?",
                       (hoje, tipo, mid)).fetchone()
        if f:
            resp["falas"] = {"feito": f["feito"] or "", "planejado": f["planejado"] or "", "review": f["review"] or ""}
        if request.args.get("comjogo") == "1":
            resp["jogo_resposta"] = _resposta_jogo(db, mid, hoje)
    return jsonify(resp)


@app.route("/api/metas-premio", methods=["POST"])
def api_metas_premio():
    p = request.get_json(force=True, silent=True) or {}
    acao = p.get("acao")
    db = get_db()
    mid = _int_ou_none(p.get("id"))

    if acao in ("remover", "cumprir", "reabrir"):
        if mid is None or not db.execute("SELECT 1 FROM metas_premio WHERE id = ?", (mid,)).fetchone():
            return _erro("Meta não encontrada.", 404)
        if acao == "remover":
            db.execute("DELETE FROM metas_premio_membros WHERE meta_id = ?", (mid,))
            db.execute("DELETE FROM metas_premio WHERE id = ?", (mid,))
        elif acao == "reabrir":
            db.execute("UPDATE metas_premio SET cumprida_em = NULL WHERE id = ?", (mid,))
        else:
            quando = (p.get("data") or "").strip() or date.today().isoformat()
            try:
                datetime.strptime(quando, "%Y-%m-%d")
            except ValueError:
                return _erro("Data inválida.")
            db.execute("UPDATE metas_premio SET cumprida_em = ? WHERE id = ?", (quando, mid))
        db.commit()
        return jsonify({"ok": True})

    if acao != "criar":
        abort(400)
    titulo = (p.get("titulo") or "").strip()
    if not titulo:
        return _erro("Dê um nome para a meta.")
    prazo = (p.get("prazo") or "").strip()
    try:
        datetime.strptime(prazo, "%Y-%m-%d")
    except ValueError:
        return _erro("Escolha o prazo da meta.")
    sementes = _int_ou_none(p.get("sementes"))
    if sementes is None or not 1 <= sementes <= game.SEED_META_MAX:
        return _erro(f"A recompensa vai de 1 a {game.SEED_META_MAX} sementes.")
    para_time = bool(p.get("para_time"))
    escolhidos = []
    if not para_time:
        validos = {r["id"] for r in db.execute("SELECT id FROM members WHERE active = 1").fetchall()}
        escolhidos = sorted({i for i in (_int_ou_none(x) for x in (p.get("membros") or [])) if i in validos})
        if not escolhidos:
            return _erro("Escolha quem recebe a recompensa, ou marque o time inteiro.")
    cur = db.execute(
        "INSERT INTO metas_premio (titulo, prazo, sementes, para_time) VALUES (?, ?, ?, ?)",
        (titulo[:100], prazo, sementes, int(para_time)))
    db.executemany("INSERT INTO metas_premio_membros (meta_id, member_id) VALUES (?, ?)",
                   [(cur.lastrowid, i) for i in escolhidos])
    db.commit()
    return jsonify({"ok": True, "id": cur.lastrowid})


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
    usuarios_gitlab = [
        dict(r) for r in db.execute("SELECT username, nome FROM gitlab_usuarios ORDER BY username").fetchall()
    ]
    return render_template("membros.html", membros=membros, usuarios_gitlab=usuarios_gitlab)


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
    campos_validos = {"semana1_inicio", "num_semanas", "sprint_semanas", "contar_a_partir_de", "fundador_ate"}
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


def _resposta_jogo(db, member_id, event_date):
    """Estado do jogo apos mexer na presenca de alguem: o que a tela precisa para acender a chama,
    subir a planta e atualizar as sementes. Usado por /api/attendance e pela ata/rodada."""
    dias_letivos_lista = _dias_letivos(db)
    meta = game.meta_floracao(len(dias_letivos_lista))

    # Recalcula o estado de todos os ativos de uma vez: assim o cliente atualiza o
    # contador de sementes de cada um. Quando esta marcacao fecha o dia cheio, todos
    # os presentes ganham +1, nao so quem foi marcado (bug corrigido na Fase 1.1).
    todos = get_member_stats(db, dias_letivos_lista)
    por_id = {s["id"]: s for s in todos}
    stats = por_id.get(member_id)
    estado = _estado_jogo_membro(db, member_id, dias_letivos_lista)

    progresso, dias_ate_proximo = game.progresso_estagio(
        estado["g"], meta, estado["estagio"]
    )
    extras = _extras_dia(db, [member_id], event_date, set(dias_letivos_lista))[member_id]

    # Dia cheio desta data (apos a marcacao). O cliente compara com o valor anterior
    # que ele mesmo guarda para decidir se mostra a celebracao (Fase 1.2).
    dia_cheio_hoje = _dia_cheio_na_data(db, event_date, dias_letivos_lista)

    sementes_por_membro = [
        {"id": s["id"], "sementes": s["sementes"], "sementes_ganhas": s["sementes_ganhas"]}
        for s in todos
    ]

    return {
        "ok": True,
        "dia_cheio": dia_cheio_hoje,
        "sementes_membros": sementes_por_membro,
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
    }


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

    return jsonify(_resposta_jogo(db, member_id, event_date))


@app.route("/api/attendance/marcar_todos", methods=["POST"])
def api_marcar_todos():
    payload = request.get_json(force=True, silent=True) or {}
    event_date = payload.get("event_date")
    event_type = payload.get("event_type")
    status = payload.get("status", "presente")
    tipo = payload.get("tipo")  # None = todos; 'equipe' ou 'convidado' = so esse grupo

    try:
        date.fromisoformat(event_date)
    except (TypeError, ValueError):
        abort(400)
    if event_type not in EVENT_KEYS:
        abort(400)
    if status not in ("presente", "faltou", "justificada"):
        abort(400)
    if tipo not in (None, "equipe", "convidado"):
        abort(400)

    db = get_db()
    if tipo is None:
        membros_ativos = db.execute("SELECT id FROM members WHERE active = 1").fetchall()
    else:
        membros_ativos = db.execute(
            "SELECT id FROM members WHERE active = 1 AND COALESCE(tipo, 'equipe') = ?", (tipo,)
        ).fetchall()
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


@app.route("/api/dia/<data_str>/estado")
def api_dia_estado(data_str):
    """Estado leve do dia para o Hoje atualizar sozinho (polling): sementes de cada
    ativo, status de cada celula (membro x evento) e se o dia esta cheio. Nunca dispara
    a celebracao — o cliente so atualiza numeros/estados."""
    try:
        date.fromisoformat(data_str)
    except ValueError:
        abort(404)
    db = get_db()
    dias_letivos_lista = _dias_letivos(db)
    membros = get_member_stats(db, dias_letivos_lista)
    sementes = [{"id": m["id"], "sementes": m["sementes"]} for m in membros if m["active"]]
    registros = db.execute(
        "SELECT member_id, event_type, status FROM attendance WHERE event_date = ?", (data_str,)
    ).fetchall()
    celulas = [{"member_id": r["member_id"], "evento": r["event_type"], "status": r["status"]}
               for r in registros]
    return jsonify({
        "sementes_membros": sementes,
        "celulas": celulas,
        "dia_cheio": _dia_cheio_na_data(db, data_str, dias_letivos_lista),
    })


@app.route("/api/membros", methods=["POST"])
def api_add_membro():
    payload = request.get_json(force=True, silent=True) or {}
    nome = (payload.get("name") or "").strip()
    if not nome:
        abort(400)
    tipo = payload.get("tipo", "equipe")
    if tipo not in ("equipe", "convidado"):
        abort(400)
    db = get_db()
    db.execute("INSERT INTO members (name, tipo) VALUES (?, ?)", (nome, tipo))
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
    if "tipo" in payload:
        tipo = payload.get("tipo")
        if tipo not in ("equipe", "convidado"):
            abort(400)
        db.execute("UPDATE members SET tipo = ? WHERE id = ?", (tipo, member_id))
    if "gitlab_user" in payload:
        # Usuario da pessoa no GitLab (para casar os cards). Vazio = nao mapeado.
        gu = (payload.get("gitlab_user") or "").strip().lstrip("@")[:100]
        db.execute("UPDATE members SET gitlab_user = ? WHERE id = ?", (gu or None, member_id))
    if payload.get("resetar_pin"):
        # o dono reseta o PIN: a pessoa cria um novo no proximo acesso ao /eu
        db.execute(
            "UPDATE members SET pin_hash = NULL, pin_salt = NULL WHERE id = ?", (member_id,)
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


def _e_fundador_membro(db, member_id):
    reg = _registros_membro(db, member_id)
    fundador_ate = _get_config(db).get("fundador_ate", "2026-10-23")
    return game.e_fundador(reg, fundador_ate)


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
    fundador = bool(stats and stats.get("fundador"))

    usados = {}
    if stats:
        v = stats["visual"]
        usados = {"especie": v["especie"], "vaso": v["vaso"],
                  "companheiro": v["companheiro"], "acessorio": v["acessorio"]}
        for e in v["extras"]:
            usados[f"especie_{e['slot']}"] = e["especie"]

    itens = []
    for it in catalog.ITENS:
        # Item exclusivo (Selo Fundador) so aparece para quem tem direito.
        if it.get("exclusivo") and not fundador:
            continue
        e = {**it, "preview": _preview(it["id"])}
        # Exclusivo liberado conta como "possui" para poder equipar (nunca foi comprado).
        e["possui"] = bool(it.get("padrao")) or it["id"] in possui or (it.get("exclusivo") and fundador)
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
        "fundador": fundador,
        "compra_ativa": compra_ativa,
        "total_itens": len(catalog.ITENS),
        "itens": itens,
        "grupos": GRUPOS_LOJA,
        "plantas_liberadas": [1] + [n for n in (2, 3) if f"slot_{n}" in possui],
        "compras": compras,
        "desfazer_restantes": max(DESFAZER_MAX - _desfeitas_do_membro(db, member_id), 0) if stats else 0,
        "fontes": {
            "por_evento": game.SEED_POR_EVENTO,
            "semana_fechada": game.SEED_SEMANA_FECHADA,
            "dia_cheio": game.SEED_DIA_CHEIO,
            "marcos": game.SEED_MILESTONES,
        },
    }


@app.route("/loja")
def loja_page():
    db = get_db()
    m = request.args.get("m", type=int)
    eu = _eu_id()
    if m is None and eu is not None:
        return redirect(url_for("loja_page", m=eu))
    ctx = _contexto_loja(db, m)
    # Qualquer um pode ver a loja/colecao de alguem. Compra e equipa a propria pessoa
    # (logada com o PIN) ou o administrador, que escolhe o perfil.
    ctx["pode_agir"] = m is not None and ((eu is not None and eu == m) or eh_admin())
    ctx["estagio_previa"] = PREVIEW_BASE["estagio"]
    ctx["stage_names"] = game.STAGE_NAMES
    return render_template("loja.html", **ctx)


def _contexto_sementes(db, member_id, compare_id=None):
    """Dados da aba Sementes: as constantes (fonte unica dos numeros) e, se a pessoa
    escolheu quem acompanhar, o detalhamento do ganho dela (e de uma segunda pessoa
    para comparar lado a lado, de forma neutra)."""
    fontes = {
        "por_evento": game.SEED_POR_EVENTO,
        "semana_fechada": game.SEED_SEMANA_FECHADA,
        "dia_cheio": game.SEED_DIA_CHEIO,
        "floresceu": game.SEED_FLORESCEU,
        "boas_vindas": game.SEED_BOAS_VINDAS,
        "marcos": game.SEED_MILESTONES,
        "ata": game.SEED_ATA,
        "relator": game.SEED_RELATOR,
        "relator_max": game.SEED_RELATOR_MAX_POR_ATA,
    }

    # Composicao do perfil "dedicado" (3 eventos, 45 dias, time perfeito), derivada das
    # mesmas funcoes de game.py para o grafico nunca mentir se as constantes mudarem.
    dias = _dias_letivos(db)
    semanas = _semanas_projeto(db)
    regs_dedicado = {
        d: {"presente": True, "eventos": set(game.SEED_POR_EVENTO)} for d in dias
    }
    ded = game.calcular_sementes(dias, semanas, regs_dedicado, True, dias_cheios=set(dias),
                                 atas_com_fala=2 * len(dias))
    composicao = [
        {"id": "eventos", "rotulo": "Presença nos eventos", "valor": ded["por_presenca"]},
        {"id": "semanas", "rotulo": "Semanas fechadas", "valor": ded["por_semanas_fechadas"]},
        {"id": "marcos", "rotulo": "Marcos de sequência", "valor": ded["por_marcos"]},
        {"id": "dia_cheio", "rotulo": "Dia cheio do time", "valor": ded["por_dia_cheio"]},
        {"id": "floresceu", "rotulo": "Floresceu", "valor": ded["por_floresceu"]},
        {"id": "boas_vindas", "rotulo": "Boas-vindas", "valor": ded["por_boas_vindas"]},
        {"id": "ata", "rotulo": "Atas preenchidas", "valor": ded["por_ata"]},
    ]
    total_ded = ded["total"]
    acumulado = 0
    for c in composicao:
        c["cor"] = CORES_FONTE[c["id"]]
        c["pct"] = round(100 * c["valor"] / total_ded, 1) if total_ded else 0
        c["inicio"] = round(100 * acumulado / total_ded, 3) if total_ded else 0
        acumulado += c["valor"]

    membros = db.execute(
        "SELECT id, name FROM members WHERE active = 1 ORDER BY name COLLATE NOCASE"
    ).fetchall()

    # Dados comuns reusados para a pessoa A e a pessoa B (comparacao).
    dias_letivos_lista = _dias_letivos(db)
    meta = game.meta_floracao(len(dias_letivos_lista))
    semanas_proj = _semanas_projeto(db)
    dias_set = set(dias_letivos_lista)
    glob = _registros_globais(db)
    ativos_ids = [r["id"] for r in membros]
    cheios = game.dia_cheio(ativos_ids, {d: v for d, v in glob.items() if d in dias_set})
    com_fala_todos, relatadas_todos = _contagem_atas(db, dias_letivos_lista)
    gastos_todos = _gastos_por_membro(db)

    def _detalhe_membro(mid):
        if not mid:
            return None, None
        m = db.execute(
            "SELECT id, name FROM members WHERE id = ? AND active = 1", (mid,)
        ).fetchone()
        if not m:
            return None, None
        reg = _reg_membro(glob, mid)            # com os eventos de cada dia (igual ao saldo real)
        estado = game.calcular_membro(dias_letivos_lista, reg, meta)
        ganho = game.calcular_sementes(
            dias_letivos_lista, semanas_proj, reg, estado["floresceu"], dias_cheios=cheios,
            atas_com_fala=com_fala_todos.get(mid, 0), falas_relatadas=relatadas_todos.get(mid, 0),
            bonus_metas=sum(x["valor"] for x in _premios_de_metas_do_membro(db, mid)),
        )
        pessoa = {"id": m["id"], "name": m["name"]}
        gasto = gastos_todos.get(mid, 0)
        det = {
            "gasto": gasto,
            "saldo": max(ganho["total"] - gasto, 0),
            "extrato": _extrato_do_membro(db, mid, dias_letivos_lista, semanas_proj, glob, cheios, meta),
            "streak": estado["streak"],
            "melhor_streak": estado["melhor_streak"],
            "proximo": game.proximo_marco(estado["streak"]),
            "ganho": ganho,
            "floresceu": estado["floresceu"],
        }
        return pessoa, det

    atual, detalhe = _detalhe_membro(member_id)
    # Pessoa B (comparacao). Nunca compara alguem consigo mesmo.
    comparar, detalhe_b = (None, None)
    if member_id and compare_id and compare_id != member_id:
        comparar, detalhe_b = _detalhe_membro(compare_id)

    # "Por que a diferenca?": fonte a fonte, so o que muda de uma pessoa para a outra
    diferencas = []
    if detalhe and detalhe_b:
        for chave, rotulo in (
            ("por_presenca", "Presença nos eventos"), ("por_semanas_fechadas", "Semanas fechadas"),
            ("por_marcos", "Marcos de sequência"), ("por_dia_cheio", "Dia cheio do time"),
            ("por_floresceu", "Floresceu"), ("por_boas_vindas", "Boas-vindas"),
            ("por_ata", "Atas preenchidas"), ("por_relator", "Scrum: falas de colegas preenchidas"),
            ("por_metas", "Metas personalizadas cumpridas"),
        ):
            va, vb = detalhe["ganho"].get(chave, 0), detalhe_b["ganho"].get(chave, 0)
            if va != vb:
                diferencas.append({"rotulo": rotulo, "a": va, "b": vb, "delta": va - vb})
        if detalhe["gasto"] != detalhe_b["gasto"]:
            diferencas.append({"rotulo": "Gasto na loja (desconta do saldo)", "a": -detalhe["gasto"],
                               "b": -detalhe_b["gasto"], "delta": -detalhe["gasto"] + detalhe_b["gasto"]})

    return {
        "fontes": fontes,
        "membros": [dict(m) for m in membros],
        "atual": atual,
        "detalhe": detalhe,
        "comparar": comparar,
        "detalhe_b": detalhe_b,
        "diferencas": diferencas,
        "composicao": composicao,
        "total_dedicado": total_ded,
        "cores": CORES_FONTE,
    }


@app.route("/sementes")
def sementes_page():
    db = get_db()
    if request.args.get("m", type=int) is None and _eu_id() is not None:
        return redirect(url_for("sementes_page", m=_eu_id()) + "#progresso")
    return render_template(
        "sementes.html",
        **_contexto_sementes(
            db, request.args.get("m", type=int), request.args.get("b", type=int)
        ),
    )


# ------------------------------------------------------------ pagina pessoal /eu
def _eu_id():
    try:
        return int(session.get("eu"))
    except (TypeError, ValueError):
        return None


def _eu_membro(db):
    mid = _eu_id()
    if mid is None:
        return None
    return db.execute("SELECT * FROM members WHERE id = ? AND active = 1", (mid,)).fetchone()


def _chaves_pin(member_id):
    return [f"ip:{_ip()}", f"m:{member_id}"]


@app.route("/eu")
def eu_page():
    db = get_db()
    membro = _eu_membro(db)
    if membro is None:
        # Nao logado: lista de nomes, indicando quem ja tem PIN.
        pessoas = db.execute(
            "SELECT id, name, (pin_hash IS NOT NULL) AS tem_pin, "
            "COALESCE(tipo, 'equipe') AS tipo FROM members WHERE active = 1 "
            "ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return render_template("eu_login.html", pessoas=[dict(p) for p in pessoas])

    stats = _stats_membro(db, membro["id"])
    ctx = _contexto_loja(db, membro["id"])

    # Fala propria do dia: so aparece se a pessoa tem presenca hoje. Ela edita so a dela.
    # O Day Closing so aparece quando faz sentido: quando a pessoa ja marcou presenca no
    # encerramento de hoje (leu o QR do encerramento) ou ja escreveu algo nele. De manha,
    # com so a daily, o /eu mostra so a Daily (nao polui com o fim do dia ainda).
    hoje = date.today().isoformat()
    tem_presenca_hoje = db.execute(
        "SELECT 1 FROM attendance WHERE member_id = ? AND event_date = ? AND status = 'presente' LIMIT 1",
        (membro["id"], hoje),
    ).fetchone() is not None
    tem_encerramento = db.execute(
        "SELECT 1 FROM attendance WHERE member_id = ? AND event_date = ? AND event_type = 'encerramento' "
        "AND status = 'presente' LIMIT 1", (membro["id"], hoje),
    ).fetchone() is not None
    minhas_falas = []
    if tem_presenca_hoje:
        for tipo, rotulo, rot_feito, rot_planejado in (
            ("daily", "Daily", "O que fiz", "O que vou fazer"),
            ("fechamento", "Day Closing", "Concluí hoje", "Ficou para depois"),
        ):
            f = db.execute(
                "SELECT feito, planejado, review FROM ata_falas WHERE data = ? AND tipo = ? AND member_id = ?",
                (hoje, tipo, membro["id"]),
            ).fetchone()
            # o Day Closing so entra se ja ha encerramento marcado ou texto preenchido
            if tipo == "fechamento":
                tem_texto = bool(f and ((f["feito"] or "").strip() or (f["planejado"] or "").strip()))
                if not (tem_encerramento or tem_texto):
                    continue
            minhas_falas.append({
                "tipo": tipo, "rotulo": rotulo,
                "rot_feito": rot_feito, "rot_planejado": rot_planejado,
                "feito": f["feito"] if f else "", "planejado": f["planejado"] if f else "",
                "review": (_coluna(f, "review") or "") if f else "",
            })

    return render_template(
        "eu.html", eu=stats, hoje=hoje, minhas_falas=minhas_falas,
        eu_member_id=membro["id"], **ctx
    )


@app.route("/eu/criar", methods=["POST"])
def eu_criar_pin():
    db = get_db()
    p = request.get_json(force=True, silent=True) or {}
    try:
        member_id = int(p.get("member_id"))
    except (TypeError, ValueError):
        return _erro("Pessoa inválida.")
    pin = str(p.get("pin") or "")
    pin2 = str(p.get("pin2") or "")
    membro = db.execute("SELECT * FROM members WHERE id = ? AND active = 1", (member_id,)).fetchone()
    if membro is None:
        return _erro("Pessoa inválida.")
    if membro["pin_hash"]:
        return _erro("Esta pessoa já tem um PIN. Entre com ele.")
    if not _pin_valido(pin):
        return _erro("O PIN deve ter 4 dígitos.")
    if pin != pin2:
        return _erro("Os dois PINs não batem.")
    h, s = criar_pin_hash(pin)
    db.execute("UPDATE members SET pin_hash = ?, pin_salt = ? WHERE id = ?", (h, s, member_id))
    db.commit()
    session["eu"] = member_id
    session.permanent = True
    return jsonify({"ok": True})


@app.route("/eu/entrar", methods=["POST"])
def eu_entrar():
    db = get_db()
    p = request.get_json(force=True, silent=True) or {}
    try:
        member_id = int(p.get("member_id"))
    except (TypeError, ValueError):
        return _erro("Pessoa inválida.")
    pin = str(p.get("pin") or "")
    chaves = _chaves_pin(member_id)
    if _pin_bloqueado(chaves):
        return _erro("Muitas tentativas. Tente de novo em alguns minutos.", 429)
    membro = db.execute("SELECT * FROM members WHERE id = ? AND active = 1", (member_id,)).fetchone()
    if membro is None or not membro["pin_hash"]:
        return _erro("Pessoa inválida ou sem PIN.")
    if not verificar_pin(pin, membro["pin_hash"], membro["pin_salt"]):
        _pin_registrar_erro(chaves)
        return _erro("PIN incorreto.", 401)
    _pin_limpar(chaves)
    session["eu"] = member_id
    session.permanent = True
    return jsonify({"ok": True})


@app.route("/eu/sair")
def eu_sair():
    session.pop("eu", None)
    return redirect(url_for("eu_page"))


# ------------------------------------------------------------ QR de presenca
EVENT_NOMES = dict(EVENTS)


@app.route("/qr/<evento>")
def qr_page(evento):
    if evento not in EVENT_KEYS:
        abort(404)
    hoje = date.today().isoformat()
    codigo = codigo_do_evento(hoje, evento)
    caminho = url_for("presenca_page", evento=evento, codigo=codigo)
    # Preferimos o IP da maquina na rede local, para o celular (mesma Wi-Fi) abrir direto.
    # Se nao der para descobrir, caimos no host do proprio pedido.
    # So usa o IP da rede local quando o site foi aberto em localhost (rodando no PC do dono).
    # Em producao (PythonAnywhere), o IP da maquina seria interno e o QR nao abriria no celular.
    host_so = request.host.split(":")[0]
    ip_lan = _ip_lan() if host_so in ("localhost", "127.0.0.1", "[::1]", "::1") else None
    porta = request.host.split(":")[-1] if ":" in request.host else "5000"
    if ip_lan:
        base = f"http://{ip_lan}:{porta}"
    else:
        base = request.host_url.rstrip("/")
    url = base + caminho
    svg_qr = qr_puro.svg(url, modulo=8, borda=4)
    template = "qr_fragmento.html" if request.args.get("fragmento") else "qr.html"
    return render_template(
        template,
        evento=evento,
        evento_nome=EVENT_NOMES.get(evento, evento),
        codigo=codigo,
        url=url,
        caminho=caminho,
        svg_qr=svg_qr,
        hoje=hoje,
        data_extenso=_data_completa(hoje),
    )


def _data_completa(data_str):
    """'quinta, 22 de outubro de 2026' a partir de AAAA-MM-DD."""
    d = date.fromisoformat(data_str)
    return f"{_data_extenso(d)} de {d.year}"


# Evento do dia <-> tipo de ata (a Daily e o Day Closing; o Dev nao tem ata)
ATA_EVENTO = {"daily": "daily", "fechamento": "encerramento"}
EVENTO_ATA = {v: k for k, v in ATA_EVENTO.items()}
ATA_ROTULOS_FALA = {
    "daily": ("O que eu fiz de ontem para hoje", "O que vou fazer hoje"),
    "fechamento": ("O que concluí hoje", "O que fica para amanhã"),
}


def _salvar_fala(db, data_str, tipo, member_id, feito=None, planejado=None, review=None, bloqueios=None,
                 origem=None):
    """Grava (upsert) a fala de uma pessoa na ata; so os campos informados mudam."""
    _garantir_ata(db, data_str, tipo)
    db.execute(
        "INSERT INTO ata_falas (data, tipo, member_id, feito, planejado, atualizada_em) "
        "VALUES (?, ?, ?, '', '', datetime('now')) ON CONFLICT (data, tipo, member_id) DO NOTHING",
        (data_str, tipo, member_id),
    )
    if feito is not None:
        db.execute("UPDATE ata_falas SET feito = ?, atualizada_em = datetime('now') "
                   "WHERE data = ? AND tipo = ? AND member_id = ?", (feito, data_str, tipo, member_id))
    if planejado is not None:
        db.execute("UPDATE ata_falas SET planejado = ?, atualizada_em = datetime('now') "
                   "WHERE data = ? AND tipo = ? AND member_id = ?", (planejado, data_str, tipo, member_id))
    if review is not None:
        db.execute("UPDATE ata_falas SET review = ?, atualizada_em = datetime('now') "
                   "WHERE data = ? AND tipo = ? AND member_id = ?", (review, data_str, tipo, member_id))
    if bloqueios is not None:
        db.execute("UPDATE ata_falas SET bloqueios = ?, atualizada_em = datetime('now') "
                   "WHERE data = ? AND tipo = ? AND member_id = ?", (bloqueios, data_str, tipo, member_id))
    if origem and any(v is not None for v in (feito, planejado, review, bloqueios)):
        db.execute("UPDATE ata_falas SET origem = ? WHERE data = ? AND tipo = ? AND member_id = ?",
                   (origem, data_str, tipo, member_id))


def _definir_status(db, member_id, data_str, evento, status):
    """Define (ou apaga, se status vazio) a presenca da pessoa naquele evento do dia."""
    if status in (None, ""):
        db.execute("DELETE FROM attendance WHERE member_id = ? AND event_date = ? AND event_type = ?",
                   (member_id, data_str, evento))
        return
    db.execute(
        """
        INSERT INTO attendance (member_id, event_date, event_type, status, updated_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        ON CONFLICT (member_id, event_date, event_type)
        DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at
        """,
        (member_id, data_str, evento, status),
    )


def _status_do_evento(db, data_str, evento):
    return {r["member_id"]: r["status"] for r in db.execute(
        "SELECT member_id, status FROM attendance WHERE event_date = ? AND event_type = ?",
        (data_str, evento)).fetchall()}


@app.route("/presenca/<evento>/<codigo>", methods=["GET", "POST"])
def presenca_page(evento, codigo):
    if evento not in EVENT_KEYS:
        abort(404)
    db = get_db()
    membro = _eu_membro(db)
    hoje = date.today().isoformat()
    valido = verificar_codigo_evento(codigo, hoje, evento)
    base = dict(evento=evento, evento_nome=EVENT_NOMES.get(evento, evento),
                data_extenso=_data_completa(hoje), hoje=hoje)

    if not membro:
        # precisa estar logado no /eu para marcar a propria presenca
        destino = request.full_path.rstrip("?")
        return render_template("presenca.html", estado="sem_login", destino=destino, **base)

    if not valido:
        return render_template("presenca.html", estado="expirado",
                               eu=_stats_membro(db, membro["id"]), **base)

    tipo_ata = EVENTO_ATA.get(evento)           # None para o Dev (nao tem ata)
    ja_row = db.execute(
        "SELECT status FROM attendance WHERE member_id = ? AND event_date = ? AND event_type = ?",
        (membro["id"], hoje, evento),
    ).fetchone()
    ja = bool(ja_row and ja_row["status"] == "presente")

    if request.method == "POST":
        p = request.get_json(force=True, silent=True) or {}
        fala = p.get("fala") if isinstance(p.get("fala"), dict) else None
        feito = (fala.get("feito") or "").strip() if fala else ""
        planejado = (fala.get("planejado") or "").strip() if fala else ""
        # impedimento pessoal (opcional): vazio = nenhum. NUNCA rende semente.
        tem_bloqueio = bool(fala and ("bloqueios" in fala))
        bloqueios = (fala.get("bloqueios") or "").strip() if fala else ""
        # tinha a fala preenchida antes? (para dizer se o bonus de ata e novo)
        ja_tinha_fala = False
        if tipo_ata:
            f0 = db.execute(
                "SELECT feito, planejado FROM ata_falas WHERE data = ? AND tipo = ? AND member_id = ?",
                (hoje, tipo_ata, membro["id"]),
            ).fetchone()
            ja_tinha_fala = bool(f0 and ((f0["feito"] or "").strip() or (f0["planejado"] or "").strip()))
        # marca presente (idempotente, so o proprio membro, so hoje, nunca "faltou")
        if not ja:
            _definir_status(db, membro["id"], hoje, evento, "presente")
        ganhou_ata = False
        if tipo_ata and (feito or planejado):
            _salvar_fala(db, hoje, tipo_ata, membro["id"], feito, planejado, origem="proprio")
            ganhou_ata = True
        # impedimento salvo a parte (so quando o campo veio no pedido); nao conta semente
        if tipo_ata and tem_bloqueio:
            _salvar_fala(db, hoje, tipo_ata, membro["id"], bloqueios=bloqueios, origem="proprio")
        db.commit()
        return jsonify({
            "ok": True,
            "ganhou_presenca": not ja,          # presenca e nova neste POST?
            "ganhou_ata": ganhou_ata and not ja_tinha_fala,  # bonus de ata e novo?
            "tem_fala": ganhou_ata or ja_tinha_fala,
            "rende_presenca": game.SEED_POR_EVENTO.get(evento, 0),
            "rende_ata": game.SEED_ATA,
            "sementes": _stats_membro(db, membro["id"])["sementes"],
        })

    fala_atual = {"feito": "", "planejado": "", "bloqueios": ""}
    if tipo_ata:
        f = db.execute("SELECT feito, planejado, bloqueios FROM ata_falas WHERE data = ? AND tipo = ? AND member_id = ?",
                       (hoje, tipo_ata, membro["id"])).fetchone()
        if f:
            fala_atual = {"feito": f["feito"], "planejado": f["planejado"],
                          "bloqueios": _coluna(f, "bloqueios") or ""}
    rot_feito, rot_planejado = ATA_ROTULOS_FALA.get(tipo_ata, ("", ""))
    return render_template(
        "presenca.html", estado="ok", codigo=codigo, eu=_stats_membro(db, membro["id"]),
        ja=ja, tem_ata=bool(tipo_ata), fala_atual=fala_atual,
        rot_feito=rot_feito, rot_planejado=rot_planejado,
        rende_presenca=game.SEED_POR_EVENTO.get(evento, 0), rende_ata=game.SEED_ATA, **base,
    )


# ------------------------------------------------------------ Ata da daily (Fase 4)
ATA_TIPOS = ("daily", "fechamento")


def _presentes_no_dia(db, data_str):
    """Membros ativos com qualquer presenca registrada no dia (qualquer evento),
    em ordem alfabetica. Base do 'Present:' automatico e das linhas da ata."""
    rows = db.execute(
        """
        SELECT DISTINCT m.id, m.name
        FROM members m
        JOIN attendance a ON a.member_id = m.id
        WHERE a.event_date = ? AND a.status = 'presente' AND m.active = 1
        ORDER BY m.name COLLATE NOCASE
        """,
        (data_str,),
    ).fetchall()
    return [{"id": r["id"], "name": r["name"]} for r in rows]


def _carregar_ata(db, data_str, tipo):
    """Cabecalho da ata (relator, bloqueios, quadro) ou None se ainda nao existe."""
    return db.execute(
        "SELECT * FROM atas WHERE data = ? AND tipo = ?", (data_str, tipo)
    ).fetchone()


def _falas_da_ata(db, data_str, tipo):
    """{member_id: {'feito', 'planejado', 'review', 'bloqueios'}} do que ja foi preenchido."""
    out = {}
    for r in db.execute(
        "SELECT member_id, feito, planejado, review, bloqueios FROM ata_falas WHERE data = ? AND tipo = ?",
        (data_str, tipo),
    ).fetchall():
        out[r["member_id"]] = {"feito": r["feito"], "planejado": r["planejado"],
                               "review": _coluna(r, "review") or "",
                               "bloqueios": _coluna(r, "bloqueios") or ""}
    return out


def _membros_da_ata(db):
    """Membros ATIVOS da EQUIPE (convidados ficam fora da ata), em ordem alfabetica."""
    rows = db.execute(
        "SELECT id, name FROM members WHERE active = 1 AND COALESCE(tipo, 'equipe') = 'equipe' "
        "ORDER BY name COLLATE NOCASE"
    ).fetchall()
    return [{"id": r["id"], "name": r["name"]} for r in rows]


def _ata_para_fmt(db, data_str, tipo):
    """Monta o dict que o ata_fmt espera. 'Present' = quem esta presente NO EVENTO da ata
    (Daily -> daily, Day Closing -> encerramento); quem avisou vai em 'Excused'."""
    cab = _carregar_ata(db, data_str, tipo)
    membros = _membros_da_ata(db)
    status = _status_do_evento(db, data_str, ATA_EVENTO[tipo])
    falas_map = _falas_da_ata(db, data_str, tipo)
    relator_nome = None
    if cab and cab["relator_id"]:
        r = db.execute("SELECT name FROM members WHERE id = ?", (cab["relator_id"],)).fetchone()
        relator_nome = r["name"] if r else None
    present, excused, falas = [], [], []
    bloqueios_pessoais = []
    for m in membros:
        st = status.get(m["id"])
        f = falas_map.get(m["id"], {})
        rev = (f.get("review") or "").strip() if tipo == "daily" else ""
        tem_texto = bool((f.get("feito") or "").strip() or (f.get("planejado") or "").strip() or rev)
        if st == "presente":
            present.append(m["name"])
        elif st == "justificada":
            excused.append(m["name"])
        if st == "presente" or tem_texto:
            falas.append({"nome": m["name"], "feito": f.get("feito", ""),
                          "planejado": f.get("planejado", ""), "review": rev})
        bloq = (f.get("bloqueios") or "").strip()
        if bloq:
            bloqueios_pessoais.append({"nome": m["name"], "texto": bloq})
    return {
        "tipo": tipo,
        "data": data_str,
        "relator": relator_nome,
        "present": present,
        "excused": excused,
        "falas": falas,
        "bloqueios": cab["bloqueios"] if cab else "",
        "bloqueios_pessoais": bloqueios_pessoais,
        "quadro_atualizado": bool(cab["quadro_atualizado"]) if cab else False,
    }


def _dia_util_anterior(db, data_str):
    """Dia letivo imediatamente anterior a data_str (para 'usar planejado de ontem')."""
    dias = _dias_letivos(db)
    anteriores = [d for d in dias if d < data_str]
    return anteriores[-1] if anteriores else None


def _garantir_ata(db, data_str, tipo):
    """Cria a linha de cabecalho da ata se ainda nao existe (idempotente)."""
    if _carregar_ata(db, data_str, tipo) is None:
        db.execute("INSERT OR IGNORE INTO atas (data, tipo) VALUES (?, ?)", (data_str, tipo))
        db.commit()


def _linhas_da_ata(db, data_str, tipo):
    """Todos os membros da equipe, com status no evento da ata e a fala (se houver)."""
    status = _status_do_evento(db, data_str, ATA_EVENTO[tipo])
    falas_map = _falas_da_ata(db, data_str, tipo)
    cab = _carregar_ata(db, data_str, tipo)
    relator_id = cab["relator_id"] if cab else None
    ontem = _dia_util_anterior(db, data_str)
    planejado_ontem = {}
    if ontem and tipo == "daily":
        for r in db.execute(
            "SELECT member_id, planejado FROM ata_falas WHERE data = ? AND tipo = 'daily'", (ontem,)
        ).fetchall():
            if (r["planejado"] or "").strip():
                planejado_ontem[r["member_id"]] = r["planejado"]
    linhas = []
    for m in _membros_da_ata(db):
        f = falas_map.get(m["id"], {})
        linhas.append({
            "id": m["id"], "name": m["name"], "status": status.get(m["id"]) or "",
            "feito": f.get("feito", ""), "planejado": f.get("planejado", ""),
            "review": f.get("review", ""),
            "bloqueios": f.get("bloqueios", ""),
            "planejado_ontem": planejado_ontem.get(m["id"], ""),
            "e_relator": m["id"] == relator_id,
        })
    return linhas


@app.route("/ata/<data_str>/<tipo>")
def ata_page(data_str, tipo):
    if tipo not in ATA_TIPOS:
        abort(404)
    try:
        d = date.fromisoformat(data_str)
    except ValueError:
        abort(404)
    db = get_db()
    cfg = _get_config(db)
    cab = _carregar_ata(db, data_str, tipo)
    linhas = _linhas_da_ata(db, data_str, tipo)
    relator_nome = next((l["name"] for l in linhas if l["e_relator"]), None)
    return render_template(
        "ata.html",
        pode_editar=_pode_editar_ata(db, data_str, tipo),
        relator_nome=relator_nome,
        data_str=data_str,
        data_extenso=_data_completa(data_str),
        tipo=tipo,
        titulo="Daily" if tipo == "daily" else "Day Closing",
        evento_nome=EVENT_NOMES.get(ATA_EVENTO[tipo], ATA_EVENTO[tipo]),
        linhas=linhas,
        n_presentes=sum(1 for l in linhas if l["status"] == "presente"),
        n_avisos=sum(1 for l in linhas if l["status"] == "justificada"),
        relator_id=cab["relator_id"] if cab else None,
        bloqueios=cab["bloqueios"] if cab else "",
        quadro_atualizado=bool(cab["quadro_atualizado"]) if cab else False,
        idioma_ata=cfg.get("idioma_ata", "pt"),
        rot_feito=ATA_ROTULOS_FALA[tipo][0], rot_planejado=ATA_ROTULOS_FALA[tipo][1],
        evento_qr=ATA_EVENTO[tipo],
    )


@app.route("/api/ata/estado")
def api_ata_estado():
    """Estado atual da ata (para a tela do relator atualizar sozinha quando alguem
    marca presenca ou preenche a propria fala pelo celular)."""
    data_str = request.args.get("data", "")
    tipo = request.args.get("tipo", "")
    try:
        date.fromisoformat(data_str)
    except ValueError:
        return _erro("Data inválida.")
    if tipo not in ATA_TIPOS:
        return _erro("Tipo inválido.")
    db = get_db()
    cab = _carregar_ata(db, data_str, tipo)
    linhas = _linhas_da_ata(db, data_str, tipo)
    return jsonify({
        "ok": True,
        "relator_id": cab["relator_id"] if cab else None,
        "bloqueios": cab["bloqueios"] if cab else "",
        "quadro_atualizado": bool(cab["quadro_atualizado"]) if cab else False,
        "linhas": [{"id": l["id"], "status": l["status"], "feito": l["feito"],
                    "planejado": l["planejado"], "review": l["review"], "bloqueios": l["bloqueios"], "e_relator": l["e_relator"]} for l in linhas],
    })


@app.route("/api/ata/salvar", methods=["POST"])
def api_ata_salvar():
    p = request.get_json(force=True, silent=True) or {}
    data_str = p.get("data")
    tipo = p.get("tipo")
    campo = p.get("campo")
    try:
        date.fromisoformat(data_str or "")
    except (TypeError, ValueError):
        return _erro("Data inválida.")
    if tipo not in ATA_TIPOS:
        return _erro("Tipo inválido.")

    db = get_db()
    if not _pode_editar_ata(db, data_str, tipo):
        return _erro(MSG_SO_ADMIN, 403)
    _garantir_ata(db, data_str, tipo)
    resposta = {"ok": True}

    if campo in ("feito", "planejado"):
        mid = _int_ou_none(p.get("member_id"))
        if mid is None:
            return _erro("Pessoa inválida.")
        texto = (p.get("valor") or "")
        _salvar_fala(db, data_str, tipo, mid, origem="relator", **{campo: texto})
        # relatar a fala de alguem conta como presenca (a menos que ele tenha avisado)
        if texto.strip():
            evento = ATA_EVENTO[tipo]
            atual = _status_do_evento(db, data_str, evento).get(mid)
            if atual not in ("presente", "justificada"):
                _definir_status(db, mid, data_str, evento, "presente")
                resposta["status"] = "presente"
                resposta["_jogo_de"] = mid
    elif campo == "review":
        # "Em revisao" (Waiting review) da daily: so guarda, NUNCA rende semente e nao
        # mexe na presenca (nem toda revisao e uma fala da daily).
        if tipo != "daily":
            return _erro("Revisão só existe na daily.")
        mid = _int_ou_none(p.get("member_id"))
        if mid is None:
            return _erro("Pessoa inválida.")
        _salvar_fala(db, data_str, tipo, mid, review=(p.get("valor") or ""), origem="relator")
    elif campo == "bloqueio_pessoal":
        # impedimento de UMA pessoa (o relator pode preencher por ela). Nunca rende semente
        # e nao mexe na presenca. Diferente do 'bloqueios' (impedimento geral do dia).
        mid = _int_ou_none(p.get("member_id"))
        if mid is None:
            return _erro("Pessoa inválida.")
        _salvar_fala(db, data_str, tipo, mid, bloqueios=(p.get("valor") or ""), origem="relator")
    elif campo == "status":
        mid = _int_ou_none(p.get("member_id"))
        valor = p.get("valor") or ""
        if mid is None or valor not in ("", "presente", "justificada", "faltou"):
            return _erro("Pedido inválido.")
        _definir_status(db, mid, data_str, ATA_EVENTO[tipo], valor)
        resposta["status"] = valor
        resposta["_jogo_de"] = mid
    elif campo == "relator":
        mid = _int_ou_none(p.get("valor"))
        db.execute(
            "UPDATE atas SET relator_id = ?, atualizada_em = datetime('now') WHERE data = ? AND tipo = ?",
            (mid, data_str, tipo),
        )
    elif campo == "bloqueios":
        db.execute(
            "UPDATE atas SET bloqueios = ?, atualizada_em = datetime('now') WHERE data = ? AND tipo = ?",
            (p.get("valor") or "", data_str, tipo),
        )
    elif campo == "bloqueios_resolvidos":
        db.execute(
            "UPDATE atas SET bloqueios_resolvidos = ?, atualizada_em = datetime('now') WHERE data = ? AND tipo = ?",
            (1 if p.get("valor") else 0, data_str, tipo),
        )
    elif campo == "quadro_atualizado":
        db.execute(
            "UPDATE atas SET quadro_atualizado = ?, atualizada_em = datetime('now') WHERE data = ? AND tipo = ?",
            (1 if p.get("valor") else 0, data_str, tipo),
        )
    else:
        return _erro("Campo inválido.")
    db.commit()
    quem = resposta.pop("_jogo_de", None)
    if quem is not None:
        resposta["jogo_resposta"] = _resposta_jogo(db, quem, data_str)
    return jsonify(resposta)


@app.route("/api/ata/assumir", methods=["POST"])
def api_ata_assumir():
    """Quem entrou no proprio jardim (PIN) vira o relator da ata, se ainda nao ha um.
    Assim o relator escreve a ata de qualquer aparelho, inclusive de um PC."""
    db = get_db()
    membro = _eu_membro(db)
    if membro is None:
        return _erro("Entre no seu jardim (com o PIN) para assumir a ata.", 401)
    p = request.get_json(force=True, silent=True) or {}
    data_str, tipo = p.get("data"), p.get("tipo")
    try:
        date.fromisoformat(data_str or "")
    except (TypeError, ValueError):
        return _erro("Data inválida.")
    if tipo not in ATA_TIPOS:
        return _erro("Tipo inválido.")
    if (membro["tipo"] if "tipo" in membro.keys() else "equipe") != "equipe":
        return _erro("Só a equipe relata a ata.", 403)
    _garantir_ata(db, data_str, tipo)
    cab = _carregar_ata(db, data_str, tipo)
    if cab["relator_id"] and cab["relator_id"] != membro["id"]:
        r = db.execute("SELECT name FROM members WHERE id = ?", (cab["relator_id"],)).fetchone()
        return _erro(f"Já existe relator nesta ata: {r['name'] if r else 'outra pessoa'}.", 409)
    db.execute("UPDATE atas SET relator_id = ?, atualizada_em = datetime('now') WHERE data = ? AND tipo = ?",
               (membro["id"], data_str, tipo))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/ata/minha-fala", methods=["POST"])
def api_ata_minha_fala():
    """A propria pessoa (logada no /eu) edita so a sua fala do dia. Nao mexe em outros."""
    db = get_db()
    membro = _eu_membro(db)
    if membro is None:
        return _erro("Entre no seu jardim primeiro.", 401)
    p = request.get_json(force=True, silent=True) or {}
    data_str = p.get("data")
    tipo = p.get("tipo")
    campo = p.get("campo")
    try:
        date.fromisoformat(data_str or "")
    except (TypeError, ValueError):
        return _erro("Data inválida.")
    if tipo not in ATA_TIPOS or campo not in ("feito", "planejado", "review", "bloqueios"):
        return _erro("Pedido inválido.")
    if campo == "review" and tipo != "daily":
        return _erro("Revisão só existe na daily.")
    _garantir_ata(db, data_str, tipo)
    db.execute(
        """
        INSERT INTO ata_falas (data, tipo, member_id, feito, planejado, atualizada_em)
        VALUES (?, ?, ?, '', '', datetime('now'))
        ON CONFLICT (data, tipo, member_id) DO NOTHING
        """,
        (data_str, tipo, membro["id"]),
    )
    db.execute(
        f"UPDATE ata_falas SET {campo} = ?, origem = 'proprio', atualizada_em = datetime('now') "
        "WHERE data = ? AND tipo = ? AND member_id = ?",
        (p.get("valor") or "", data_str, tipo, membro["id"]),
    )
    resposta = {"ok": True}
    # Se o Scrum acendeu o holofote para ESTA pessoa, nesta reuniao e hoje, ela esta na sala:
    # escrever a fala conta como presenca (no QR e igual). Fora da vez dela, nada muda.
    if campo in ("feito", "planejado") and (p.get("valor") or "").strip() and data_str == date.today().isoformat():
        em_vez, _, tipo_vez = _holofote_atual(db)
        if em_vez == membro["id"] and tipo_vez == tipo:
            evento = ATA_EVENTO[tipo]
            if _status_do_evento(db, data_str, evento).get(membro["id"]) not in ("presente", "justificada"):
                _definir_status(db, membro["id"], data_str, evento, "presente")
    db.commit()
    return jsonify(resposta)


# ------------------------------------------------------------ Fase 6: GitLab (so leitura)
# O site nao alcanca o GitLab da faculdade. Um script no PC do dono le o quadro e EMPURRA
# um retrato pronto para ca. O unico segredo que o servidor guarda e o SYNC_TOKEN (variavel
# de ambiente), nunca o token pessoal do GitLab. Sem SYNC_TOKEN configurado, o endpoint de
# snapshot simplesmente nao existe para quem chama (404) - ninguem consegue empurrar dados.
GITLAB_SYNC_ERROS = {}          # ip -> {"erros": int, "ate": float}
GITLAB_SYNC_MAX = 10
GITLAB_SYNC_BLOQUEIO = 300


def _sync_token():
    return os.environ.get("SYNC_TOKEN") or None


def _bearer_do_pedido():
    """Extrai o token do cabecalho 'Authorization: Bearer xxx'. Retorna '' se nao houver."""
    cab = request.headers.get("Authorization", "")
    if cab.startswith("Bearer "):
        return cab[len("Bearer "):].strip()
    return ""


def _sync_bloqueado(ip):
    reg = GITLAB_SYNC_ERROS.get(ip)
    if not reg:
        return False
    if reg["ate"] and time.time() < reg["ate"]:
        return True
    if reg["ate"] and time.time() >= reg["ate"]:
        GITLAB_SYNC_ERROS.pop(ip, None)
    return False


def _sync_erro(ip):
    reg = GITLAB_SYNC_ERROS.setdefault(ip, {"erros": 0, "ate": 0})
    reg["erros"] += 1
    if reg["erros"] >= GITLAB_SYNC_MAX:
        reg["ate"] = time.time() + GITLAB_SYNC_BLOQUEIO


@app.route("/api/gitlab/snapshot", methods=["POST"])
def api_gitlab_snapshot():
    """Recebe o retrato do quadro (Doing / Waiting review) empurrado pelo script do dono.
    Autentica SO pelo Bearer SYNC_TOKEN (nao usa cookie nem sessao). Substitui tudo numa
    transacao. Nunca registra o token em log algum."""
    token_servidor = _sync_token()
    if not token_servidor:
        # Integracao desligada: o endpoint nao existe para quem chama.
        abort(404)
    ip = _ip()
    if _sync_bloqueado(ip):
        return _erro("Muitas tentativas. Tente de novo mais tarde.", 429)
    enviado = _bearer_do_pedido()
    if not enviado or not hmac.compare_digest(enviado, token_servidor):
        _sync_erro(ip)
        return _erro("Autorização inválida.", 403)
    GITLAB_SYNC_ERROS.pop(ip, None)

    p = request.get_json(force=True, silent=True)
    if not isinstance(p, dict):
        return _erro("Corpo inválido.")
    try:
        cards = gitlab_sync.validar_cards(p.get("cards"))
        usuarios = gitlab_sync.validar_usuarios(p.get("usuarios"))
    except ValueError as e:
        return _erro(str(e))
    base_url = (p.get("base_url") or "").strip()

    db = get_db()
    _garantir_config(db)
    mapeados = {}
    if usuarios:
        db.execute("DELETE FROM gitlab_usuarios")
        db.executemany("INSERT INTO gitlab_usuarios (username, nome) VALUES (?, ?)",
                       [(u["username"], u["nome"]) for u in usuarios])
        # casa sozinho quem ainda nao tem usuario (nunca sobrescreve o que o admin definiu)
        sem_usuario = [
            {"id": r["id"], "name": r["name"]}
            for r in db.execute(
                "SELECT id, name FROM members WHERE active = 1 AND COALESCE(tipo, 'equipe') = 'equipe' "
                "AND COALESCE(TRIM(gitlab_user), '') = ''"
            ).fetchall()
        ]
        ja_usados = {r["gitlab_user"] for r in db.execute(
            "SELECT gitlab_user FROM members WHERE COALESCE(TRIM(gitlab_user), '') <> ''").fetchall()}
        livres = [u for u in usuarios if u["username"] not in ja_usados]
        mapeados = gitlab_sync.sugerir_mapeamento(sem_usuario, livres)
        for mid, username in mapeados.items():
            db.execute("UPDATE members SET gitlab_user = ? WHERE id = ?", (username, mid))
    db.execute("DELETE FROM gitlab_cards")
    db.executemany(
        "INSERT INTO gitlab_cards (iid, coluna, usuario, titulo, url, labels, atualizado_em, "
        "milestone, milestone_inicio, milestone_fim) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)",
        [(c["iid"], c["coluna"], c["usuario"], c["titulo"], c["url"], c["labels"],
          c["milestone"], c["milestone_inicio"], c["milestone_fim"]) for c in cards],
    )
    db.execute(
        "INSERT INTO config (chave, valor) VALUES ('gitlab_ultima_sync', datetime('now')) "
        "ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor"
    )
    # A base dos links dos cards vem do proprio GitLab e se corrige a cada envio (antes ficava
    # presa no primeiro valor, que podia estar errado).
    if base_url:
        db.execute(
            "INSERT INTO config (chave, valor) VALUES ('gitlab_base_url', ?) "
            "ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor",
            (base_url,),
        )
    db.commit()
    return jsonify({"ok": True, "cards": len(cards), "mapeados": len(mapeados)})


def _urls_dos_cards(db):
    """{numero do card: URL exata} conhecidas pelo quadro (para o link certo na exportacao)."""
    urls = {}
    for r in db.execute(
        "SELECT iid, url FROM gitlab_cards WHERE url <> '' ORDER BY atualizado_em DESC"
    ).fetchall():
        urls.setdefault(r["iid"], r["url"])
    return urls


def _garantir_config(db):
    """Garante que as chaves de config da Fase 6 existam (idempotente)."""
    for chave in ("gitlab_base_url", "gitlab_ultima_sync"):
        db.execute("INSERT OR IGNORE INTO config (chave, valor) VALUES (?, '')", (chave,))


def _milestone_atual_do_banco(db):
    """Titulo da milestone da sprint de hoje, entre as que aparecem nos cards (ou None)."""
    linhas = db.execute(
        "SELECT DISTINCT milestone, milestone_inicio, milestone_fim FROM gitlab_cards WHERE milestone <> ''"
    ).fetchall()
    if not linhas:
        return None
    hoje = date.today().isoformat()
    try:
        sprint_n = game.sprint_da_data(hoje, _cfg_sprints(db))
    except Exception:
        sprint_n = None
    return gitlab_sync.milestone_atual(
        [(r["milestone"], r["milestone_inicio"], r["milestone_fim"]) for r in linhas], hoje, sprint_n)


def _cards_do_usuario(db, usuario):
    """Cards do quadro para os campos da daily, a partir das colunas internas.

    Devolve (fiz, fazer, revisar):
      - fiz: cards do usuario em 'review' (Waiting review) + 'em_revisao' (Review) + 'done'
             (fechados recentes) -> "O que fiz" (ordenados recentes primeiro, limitados);
      - fazer: cards do usuario em 'doing' -> "O que vou fazer hoje";
      - revisar: cards do QUADRO INTEIRO em 'review' + 'em_revisao' -> "Vou revisar"
             (nao filtra por responsavel: quem revisa nao e o dono do card).
    """
    def _item(r):
        return {"iid": r["iid"], "titulo": r["titulo"], "url": r["url"],
                "citacao": f"#{r['iid']} {(r['titulo'] or '').strip()}".strip()}

    # Review / Waiting review / fechados: so da milestone (sprint) de hoje; muda sozinha.
    atual = _milestone_atual_do_banco(db)
    fil_sql = " AND milestone = ?" if atual else ""
    fil_par = (atual,) if atual else ()

    fazer = []
    fiz = []
    if usuario:
        for r in db.execute(
            "SELECT iid, coluna, titulo, url FROM gitlab_cards WHERE usuario = ? AND coluna = 'doing' "
            "ORDER BY atualizado_em DESC, iid DESC", (usuario,)
        ).fetchall():
            fazer.append(_item(r))
        for r in db.execute(
            "SELECT iid, coluna, titulo, url FROM gitlab_cards WHERE usuario = ? "
            "AND coluna IN ('review', 'em_revisao', 'done')" + fil_sql + " "
            "ORDER BY atualizado_em DESC, iid DESC LIMIT 15", (usuario,) + fil_par
        ).fetchall():
            fiz.append(_item(r))

    # "Vou revisar": todas as linhas em review/em_revisao do quadro, sem repetir o mesmo card.
    revisar, vistos = [], set()
    for r in db.execute(
        "SELECT iid, titulo, url FROM gitlab_cards WHERE coluna IN ('review', 'em_revisao')"
        + fil_sql + " ORDER BY atualizado_em DESC, iid DESC", fil_par
    ).fetchall():
        if r["iid"] in vistos:
            continue
        vistos.add(r["iid"])
        revisar.append(_item(r))
    return fiz, fazer, revisar


@app.route("/api/gitlab/cards")
def api_gitlab_cards():
    """Cards do quadro para uma pessoa (leitura, qualquer um pode ver). Nunca bloqueia:
    se o GitLab nunca sincronizou ou a pessoa nao esta mapeada, devolve listas vazias."""
    db = get_db()
    mid = _int_ou_none(request.args.get("member_id"))
    if mid is None:
        return _erro("Pessoa inválida.")
    m = db.execute("SELECT gitlab_user FROM members WHERE id = ?", (mid,)).fetchone()
    usuario = (_coluna(m, "gitlab_user") or "").strip() if m else ""
    fiz, fazer, revisar = _cards_do_usuario(db, usuario)
    cfg = _get_config(db)
    return jsonify({
        "ok": True,
        "configurado": bool(usuario),
        "fiz": fiz,            # O que fiz (Waiting review + Review + fechados recentes)
        "fazer": fazer,        # O que vou fazer hoje (Doing)
        "revisar": revisar,    # Vou revisar (todo o quadro em revisao)
        "ultima_sync": cfg.get("gitlab_ultima_sync", ""),
        "base_url": cfg.get("gitlab_base_url", ""),
        "milestone": _milestone_atual_do_banco(db) or "",
    })


@app.route("/api/gitlab/backlog")
def api_gitlab_backlog():
    """Busca no Backlog (leitura, qualquer um): por numero (#123 / 123) ou trecho do titulo.
    Devolve ate `limit` cards, sem repetir o mesmo card por responsavel. Sem retrato: vazio."""
    db = get_db()
    q = (request.args.get("q") or "").strip()
    limite = _int_ou_none(request.args.get("limit")) or 20
    limite = max(1, min(limite, 50))
    linhas = db.execute(
        "SELECT iid, usuario, titulo, url FROM gitlab_cards WHERE coluna = 'backlog' "
        "ORDER BY atualizado_em DESC, iid DESC"
    ).fetchall()
    cards = [{"iid": r["iid"], "coluna": "backlog", "usuario": r["usuario"] or "",
              "titulo": r["titulo"] or "", "url": r["url"] or ""} for r in linhas]
    achados = gitlab_sync.busca_backlog(cards, q, limite)
    for a in achados:
        a["citacao"] = f"#{a['iid']} {(a['titulo'] or '').strip()}".strip()
    return jsonify({"ok": True, "cards": achados})


@app.route("/api/gitlab/buscar")
def api_gitlab_buscar():
    """Busca de cards para "O que fiz" e "Vou revisar" (leitura, qualquer um): entre os cards
    em Waiting review, Review e fechados da SPRINT ATUAL (milestone). Por numero (#123 / 123)
    ou trecho do titulo. Excecao proposital: se a busca e um NUMERO exato, acha o card mesmo
    de outra sprint (para registrar algo que ficou para tras). Sem retrato: vazio."""
    db = get_db()
    q = (request.args.get("q") or "").strip()
    limite = _int_ou_none(request.args.get("limit")) or 20
    limite = max(1, min(limite, 50))
    colunas = ("review", "em_revisao", "done")
    atual = _milestone_atual_do_banco(db)
    exato = q.lstrip("#").isdigit()
    sql = ("SELECT iid, coluna, usuario, titulo, url FROM gitlab_cards "
           "WHERE coluna IN ('review', 'em_revisao', 'done')")
    par = []
    if atual and not exato:
        sql += " AND milestone = ?"
        par.append(atual)
    sql += " ORDER BY atualizado_em DESC, iid DESC"
    cards = [dict(r) for r in db.execute(sql, par).fetchall()]
    achados = gitlab_sync.buscar_cards(cards, colunas, q, limite)
    for a in achados:
        a["citacao"] = f"#{a['iid']} {(a['titulo'] or '').strip()}".strip()
    return jsonify({"ok": True, "cards": achados, "milestone": atual or ""})


@app.route("/ata/<data_str>/<tipo>/imprimir")
def ata_imprimir(data_str, tipo):
    if tipo not in ATA_TIPOS:
        abort(404)
    try:
        date.fromisoformat(data_str)
    except ValueError:
        abort(404)
    db = get_db()
    cfg = _get_config(db)
    idioma = request.args.get("idioma") or cfg.get("idioma_ata", "pt")
    gitlab = cfg.get("gitlab_base_url", "")
    ata = _ata_para_fmt(db, data_str, tipo)
    texto = ata_fmt.montar_texto(ata, idioma)
    html_ata = ata_fmt.montar_html(ata, idioma, gitlab, _urls_dos_cards(db))
    return render_template(
        "ata_imprimir.html",
        data_str=data_str, tipo=tipo, idioma=idioma,
        texto=texto, html_ata=html_ata,
        titulo="Daily" if tipo == "daily" else "Day Closing",
    )


@app.route("/ata/sprint/<int:n>")
def ata_sprint_page(n):
    db = get_db()
    sprints = _cfg_sprints(db)
    if not 1 <= n <= len(sprints):
        abort(404)
    cfg = _get_config(db)
    idioma = request.args.get("idioma") or cfg.get("idioma_ata", "pt")
    gitlab = cfg.get("gitlab_base_url", "")
    sp = sprints[n - 1]
    urls_cards = _urls_dos_cards(db)
    dias = [d for d in _dias_letivos(db) if sp["inicio"] <= d <= sp["fim"]]

    documentos = []        # atas em ordem (dia, tipo)
    cards = {}             # numero -> lista de ("DD/MM Tipo", quem/contexto)
    bloqueios_abertos = []
    bloqueios_resolvidos = []
    presentes_por_dia = []

    for d in dias:
        presentes_por_dia.append({"data": d, "nomes": [p["name"] for p in _presentes_no_dia(db, d)]})
        for tipo in ATA_TIPOS:
            cab = _carregar_ata(db, d, tipo)
            falas = _falas_da_ata(db, d, tipo)
            tem_fala = any((f.get("feito") or f.get("planejado") or "").strip() for f in falas.values())
            if cab is None and not tem_fala:
                continue
            ata = _ata_para_fmt(db, d, tipo)
            documentos.append({
                "data": d, "tipo": tipo,
                "titulo": ata_fmt.ROTULOS[idioma if idioma in ata_fmt.ROTULOS else "en"][tipo]["titulo"],
                "html": ata_fmt.montar_html(ata, idioma, gitlab, urls_cards),
            })
            # cards citados (nas falas e nos bloqueios)
            rotulo_doc = f"{d[8:10]}/{d[5:7]} {tipo}"
            textos = [ (f.get('feito') or '') + ' ' + (f.get('planejado') or '') for f in falas.values() ]
            textos.append(cab["bloqueios"] if cab else "")
            for num in ata_fmt.cards_no_texto(" ".join(textos)):
                cards.setdefault(num, [])
                if rotulo_doc not in cards[num]:
                    cards[num].append(rotulo_doc)
            # impedimentos: abertos vs resolvidos
            if cab and (cab["bloqueios"] or "").strip():
                item = {"data": d, "tipo": tipo, "texto": cab["bloqueios"]}
                if cab["bloqueios_resolvidos"]:
                    bloqueios_resolvidos.append(item)
                else:
                    bloqueios_abertos.append(item)

    cards_ordenados = [{"num": k, "docs": v} for k, v in sorted(cards.items(), key=lambda kv: int(kv[0]))]

    return render_template(
        "ata_sprint.html",
        n=n, sprint=sp, total_sprints=len(sprints), idioma=idioma,
        documentos=documentos, cards=cards_ordenados,
        bloqueios_abertos=bloqueios_abertos, bloqueios_resolvidos=bloqueios_resolvidos,
        presentes_por_dia=[p for p in presentes_por_dia if p["nomes"]],
    )


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


def _so_o_dono(member_id):
    """A loja e de cada um: quem entrou no proprio jardim (PIN) mexe na sua. O
    administrador (Scrum do dia ou quem esta no computador) tambem pode escolher um
    perfil e comprar/equipar por ele."""
    if _eu_id() != member_id and not eh_admin():
        return _erro("Entre no seu jardim (com o PIN) para usar a sua loja.", 403)
    return None


@app.route("/api/loja/comprar", methods=["POST"])
def api_loja_comprar():
    payload, member_id = _ler_pedido()
    negado = _so_o_dono(member_id)
    if negado:
        return negado
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
    negado = _so_o_dono(member_id)
    if negado:
        return negado
    slot = payload.get("slot")
    item_id = payload.get("item_id")
    db = get_db()
    _membro_ou_404(db, member_id)

    if slot not in SLOTS_EQUIPAVEIS:
        return _erro("Lugar inválido.")
    if item_id is None:
        db.execute("DELETE FROM equipados WHERE member_id = ? AND slot = ?", (member_id, slot))
    else:
        ok, motivo = catalog.pode_equipar(
            item_id, slot, _posses_membro(db, member_id), _e_fundador_membro(db, member_id)
        )
        if not ok:
            return _erro(motivo)
        db.execute(
            "INSERT OR REPLACE INTO equipados (member_id, slot, item_id) VALUES (?, ?, ?)",
            (member_id, slot, item_id),
        )
    db.commit()
    return jsonify({"ok": True})


DESFAZER_MAX = 2        # cada pessoa pode desfazer ate 2 compras (recupera as sementes), no projeto todo


def _desfeitas_do_membro(db, member_id):
    return db.execute(
        "SELECT COUNT(*) FROM compras WHERE member_id = ? AND desfeita_em IS NOT NULL", (member_id,)
    ).fetchone()[0]


@app.route("/api/loja/desfazer", methods=["POST"])
def api_loja_desfazer():
    payload, member_id = _ler_pedido()
    negado = _so_o_dono(member_id)
    if negado:
        return negado
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

    if _desfeitas_do_membro(db, member_id) >= DESFAZER_MAX:
        return _erro(f"Você já usou os seus {DESFAZER_MAX} desfazimentos. Pense bem antes da próxima compra!")

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
