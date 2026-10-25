"""Cria um banco de DEMONSTRACAO (mock) para testar o site sem tocar nos dados reais.

Uso (a partir da pasta do projeto, com o venv ativo):

    python scripts/criar_banco_demo.py                      # cria demo.db na pasta temporaria
    python scripts/criar_banco_demo.py C:\\temp\\demo.db     # ou num caminho a sua escolha
    python scripts/criar_banco_demo.py demo.db --forcar     # recria se o arquivo ja existir

Depois, aponte o site para ele:

    PowerShell:  $env:STRIKES_DB = "C:\\temp\\demo.db"; python app.py
    cmd:         set STRIKES_DB=C:\\temp\\demo.db && python app.py

Seguranca: o script RECUSA escrever em data/strikes.db (o banco real) e so sobrescreve um
arquivo existente com --forcar. O banco criado tem 7 membros da equipe, 3 convidados, um
historico de presencas realista, algumas atas e o PIN 1234 para a Arthur (so para teste).
"""
import argparse
import os
import sqlite3
import sys
import tempfile
from datetime import date

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EQUIPE = ["Arthur", "Bruno", "Guilherme", "Heloisa", "Luiz", "Pablo", "Rachel"]
CONVIDADOS = ["Camila", "Joana", "Ovidio"]
EVENTOS = ("daily", "dev", "encerramento")

# (taxa de presenca no dia, chance de ir ao dev, chance de ir ao encerramento, inicio da ausencia)
PERFIS = {
    "Arthur": (1.00, 1.00, 1.00), "Bruno": (0.95, 0.90, 0.85), "Guilherme": (0.90, 0.80, 0.70),
    "Heloisa": (0.92, 0.85, 0.80), "Luiz": (0.80, 0.70, 0.60), "Pablo": (0.75, 0.60, 0.50),
    "Rachel": (0.70, 0.60, 0.50), "Camila": (0.85, 0.75, 0.60), "Joana": (0.60, 0.50, 0.40),
    "Ovidio": (0.40, 0.30, 0.30),
}


def _pseudo(nome, i, salt):
    """Numero deterministico em [0, 1): o mesmo banco de demo sai igual toda vez."""
    h = 0
    for ch in f"{nome}|{i}|{salt}":
        h = (h * 131 + ord(ch)) % 1000003
    return (h % 1000) / 1000.0


def main():
    ap = argparse.ArgumentParser(description="Cria um banco de demonstracao (mock).")
    ap.add_argument("caminho", nargs="?", default=os.path.join(tempfile.gettempdir(), "jardim-demo.db"))
    ap.add_argument("--forcar", action="store_true", help="recria o arquivo se ele ja existir")
    args = ap.parse_args()

    destino = os.path.abspath(args.caminho)
    real = os.path.abspath(os.path.join(RAIZ, "data", "strikes.db"))
    if os.path.normcase(destino) == os.path.normcase(real) or os.path.normcase(destino).startswith(
        os.path.normcase(os.path.join(RAIZ, "data")) + os.sep
    ):
        sys.exit("RECUSADO: esse caminho esta na pasta data/ (banco real). Escolha outro arquivo.")
    if os.path.exists(destino):
        if not args.forcar:
            sys.exit(f"O arquivo ja existe: {destino}\nUse --forcar para recriar (ele e so de demo).")
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(destino + ext):
                os.remove(destino + ext)
    os.makedirs(os.path.dirname(destino), exist_ok=True)

    # O app le STRIKES_DB ao ser importado: define antes do import.
    os.environ["STRIKES_DB"] = destino
    sys.path.insert(0, RAIZ)
    import app as appmod

    appmod.init_db()
    con = sqlite3.connect(destino)
    con.row_factory = sqlite3.Row
    con.execute("DELETE FROM attendance")
    con.execute("DELETE FROM members")
    ids = {}
    for nome in EQUIPE:
        cur = con.execute("INSERT INTO members (name, active, tipo) VALUES (?, 1, 'equipe')", (nome,))
        ids[nome] = cur.lastrowid
    for nome in CONVIDADOS:
        cur = con.execute("INSERT INTO members (name, active, tipo) VALUES (?, 1, 'convidado')", (nome,))
        ids[nome] = cur.lastrowid
    con.commit()

    dias = appmod._dias_letivos(con)
    hoje = date.today().isoformat()
    passados = [d for d in dias if d <= hoje]
    if len(passados) < 5:           # antes do inicio do projeto: usa os 10 primeiros dias letivos
        passados = dias[:10]

    for nome, (p_dia, p_dev, p_enc) in PERFIS.items():
        for i, d in enumerate(passados):
            if _pseudo(nome, i, "dia") > p_dia:
                # ausencia: de vez em quando avisou, de vez em quando faltou
                status = "justificada" if _pseudo(nome, i, "aviso") < 0.5 else "faltou"
                con.execute(
                    "INSERT OR IGNORE INTO attendance (member_id, event_date, event_type, status) VALUES (?,?,?,?)",
                    (ids[nome], d, "daily", status),
                )
                continue
            for ev, p in (("daily", 1.0), ("dev", p_dev), ("encerramento", p_enc)):
                if ev == "daily" or _pseudo(nome, i, ev) <= p:
                    con.execute(
                        "INSERT OR IGNORE INTO attendance (member_id, event_date, event_type, status) VALUES (?,?,?,'presente')",
                        (ids[nome], d, ev),
                    )

    # Atas dos ultimos 3 dias letivos (com impedimento aberto e um resolvido)
    for k, d in enumerate(passados[-3:]):
        for tipo in ("daily", "fechamento"):
            con.execute(
                "INSERT OR IGNORE INTO atas (data, tipo, relator_id, bloqueios) VALUES (?,?,?,?)",
                (d, tipo, ids[EQUIPE[k % len(EQUIPE)]], "Aguardando acesso ao dataset" if k == 0 and tipo == "daily" else ""),
            )
        presentes = [r["member_id"] for r in con.execute(
            "SELECT DISTINCT member_id FROM attendance WHERE event_date = ? AND status = 'presente'", (d,))]
        for mid in presentes[:5]:
            con.execute(
                "INSERT OR IGNORE INTO ata_falas (data, tipo, member_id, feito, planejado) VALUES (?,?,?,?,?)",
                (d, "daily", mid, f"Terminei a tarefa (#{100 + mid})", f"Revisar o merge request (#{110 + mid})"),
            )

    # PIN de teste da Arthur: 1234
    h, s = appmod.criar_pin_hash("1234")
    con.execute("UPDATE members SET pin_hash = ?, pin_salt = ? WHERE id = ?", (h, s, ids["Arthur"]))
    con.commit()
    con.close()

    print(f"Banco de demonstracao criado em: {destino}")
    print(f"  {len(EQUIPE)} membros da equipe, {len(CONVIDADOS)} convidados, {len(passados)} dias de historico.")
    print("  PIN de teste da Arthur: 1234 (os outros criam o PIN no primeiro acesso a /eu).")
    print()
    print("Para usar:")
    print(f'  PowerShell:  $env:STRIKES_DB = "{destino}"; python app.py')
    print(f"  cmd:         set STRIKES_DB={destino} && python app.py")


if __name__ == "__main__":
    main()
