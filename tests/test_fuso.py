"""Fuso do time: o servidor publicado roda em UTC, mas o "hoje" do site e o de Brasilia.

Cada caso roda num processo novo, porque o fuso e definido ao importar o app."""
import os
import subprocess
import sys
import tempfile
import time
import unittest

RAIZ = os.path.join(os.path.dirname(__file__), "..")

# 29/10/2026 22:30 em Brasilia = 30/10/2026 01:30 em UTC
NOITE_UTC = 1793323800

SCRIPT = (
    "import app, time\n"
    "from datetime import datetime\n"
    "print(time.timezone)\n"
    f"print(datetime.fromtimestamp({NOITE_UTC}).date().isoformat())\n"
)


def _rodar(env_extra):
    env = {k: v for k, v in os.environ.items() if k != "TZ"}
    env.update(env_extra)
    env["STRIKES_DB"] = os.path.join(tempfile.mkdtemp(), "fuso.db")
    saida = subprocess.run([sys.executable, "-c", SCRIPT], cwd=RAIZ, env=env,
                           capture_output=True, text=True, check=True).stdout.split()
    return int(saida[0]), saida[1]


@unittest.skipUnless(hasattr(time, "tzset"), "sem tzset (Windows): vale o fuso do computador")
class TestFuso(unittest.TestCase):
    def test_sem_tz_usa_brasilia(self):
        deslocamento, dia = _rodar({})
        self.assertEqual(deslocamento, 3 * 3600)
        self.assertEqual(dia, "2026-10-29")   # 22h30 ainda e o mesmo dia no time

    def test_tz_do_servidor_tem_prioridade(self):
        deslocamento, dia = _rodar({"TZ": "UTC"})
        self.assertEqual(deslocamento, 0)
        self.assertEqual(dia, "2026-10-30")

    def test_fuso_padrao_e_o_do_time(self):
        sys.path.insert(0, RAIZ)
        import app as appmod
        self.assertEqual(appmod.FUSO_PADRAO, "America/Sao_Paulo")


if __name__ == "__main__":
    unittest.main()
