"""Atalho para a tarefa agendada: python scripts/backup_db.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backup  # noqa: E402

raise SystemExit(backup.main())
