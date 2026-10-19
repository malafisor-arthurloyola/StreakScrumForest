"""Backup diario do banco SQLite, para rodar como tarefa agendada no servidor.

Usa a API de backup do SQLite (copia consistente mesmo com o site rodando), guarda um
arquivo por dia (strikes-diario-AAAA-MM-DD.db) e mantem so os ultimos N. Nao mexe em
outros arquivos da pasta (como os backups de migracao).
"""
import argparse
import os
import sqlite3
from datetime import date
from pathlib import Path

PREFIXO = "strikes-diario-"


def fazer_backup(origem, pasta, manter=14, hoje=None):
    origem = Path(origem)
    pasta = Path(pasta)
    if not origem.exists():
        raise FileNotFoundError(origem)
    pasta.mkdir(parents=True, exist_ok=True)

    hoje = hoje or date.today()
    destino = pasta / f"{PREFIXO}{hoje.isoformat()}.db"
    temporario = pasta / f"{PREFIXO}{hoje.isoformat()}.db.tmp"

    src = sqlite3.connect(origem.resolve().as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(temporario)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    os.replace(temporario, destino)

    for antigo in sorted(pasta.glob(f"{PREFIXO}*.db"))[:-manter]:
        antigo.unlink()
    return destino


def main(argv=None):
    base = Path(__file__).resolve().parent
    padrao_banco = Path(os.environ.get("STRIKES_DB", base / "data" / "strikes.db"))

    ap = argparse.ArgumentParser(description="Backup diario do banco do Jardim da Equipe.")
    ap.add_argument("--banco", default=str(padrao_banco), help="caminho do banco (padrao: STRIKES_DB)")
    ap.add_argument("--pasta", default=None, help="pasta dos backups (padrao: <pasta do banco>/backups)")
    ap.add_argument("--manter", type=int, default=14, help="quantos backups diarios guardar")
    args = ap.parse_args(argv)

    pasta = args.pasta or str(Path(args.banco).parent / "backups")
    destino = fazer_backup(args.banco, pasta, manter=args.manter)
    print(f"Backup salvo em {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
