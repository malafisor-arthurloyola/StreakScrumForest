"""Leitura do GitLab resistente a conexao cortada no meio (IncompleteRead) e a 5xx.

Nao toca a rede: troca urllib.request.urlopen por respostas falsas."""
import http.client
import io
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import sync_gitlab  # noqa: E402


class _Resp:
    def __init__(self, dados, proxima=""):
        self._corpo = json.dumps(dados).encode("utf-8")
        self.headers = {"X-Next-Page": proxima}

    def read(self):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Cortada(_Resp):
    def read(self):
        raise http.client.IncompleteRead(b"x" * 10, 99)


class GetJsonComRetry(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(sync_gitlab, "_esperar")
        self.esperar = p.start()
        self.addCleanup(p.stop)
        os.environ.pop("GITLAB_POR_PAGINA", None)

    def test_incomplete_read_tenta_de_novo_e_consegue(self):
        respostas = [_Cortada([]), _Cortada([]), _Resp([{"iid": 1}])]
        with mock.patch("urllib.request.urlopen", side_effect=lambda *a, **k: respostas.pop(0)):
            dados, _ = sync_gitlab._get_json("https://gitlab.exemplo/x", {})
        self.assertEqual(dados, [{"iid": 1}])
        self.assertEqual([c.args[0] for c in self.esperar.call_args_list], [2, 4])

    def test_desiste_depois_das_tentativas(self):
        with mock.patch("urllib.request.urlopen", side_effect=lambda *a, **k: _Cortada([])):
            with self.assertRaises(SystemExit):
                sync_gitlab._get_json("https://gitlab.exemplo/x", {}, tentativas=3)
        self.assertEqual(self.esperar.call_count, 2)

    def test_503_tenta_de_novo(self):
        erro = urllib.error.HTTPError("u", 503, "ocupado", {}, io.BytesIO(b""))
        respostas = [erro, _Resp([])]

        def abrir(*a, **k):
            r = respostas.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        with mock.patch("urllib.request.urlopen", side_effect=abrir):
            dados, _ = sync_gitlab._get_json("https://gitlab.exemplo/x", {})
        self.assertEqual(dados, [])

    def test_401_para_na_hora(self):
        erro = urllib.error.HTTPError("u", 401, "nao", {}, io.BytesIO(b""))
        with mock.patch("urllib.request.urlopen", side_effect=erro) as m:
            with self.assertRaises(SystemExit):
                sync_gitlab._get_json("https://gitlab.exemplo/x", {})
        self.assertEqual(m.call_count, 1)
        self.esperar.assert_not_called()

    def test_fechadas_paginam_com_pagina_menor(self):
        urls = []
        respostas = [_Resp([{"iid": 1}], proxima="2"), _Cortada([]), _Resp([{"iid": 2}])]

        def abrir(req, **k):
            urls.append(req.full_url)
            return respostas.pop(0)
        with mock.patch("urllib.request.urlopen", side_effect=abrir):
            fechadas = sync_gitlab.ler_fechadas_do_gitlab("https://gitlab.exemplo", "g/p", "t", 5)
        self.assertEqual([i["iid"] for i in fechadas], [1, 2])
        self.assertIn("per_page=40", urls[0])
        self.assertIn("state=closed", urls[0])
        self.assertIn("page=2", urls[1])
        self.assertEqual(urls[1], urls[2])     # repetiu a MESMA pagina depois do corte

    def test_por_pagina_do_env_fica_entre_1_e_100(self):
        with mock.patch.dict(os.environ, {"GITLAB_POR_PAGINA": "20"}):
            self.assertEqual(sync_gitlab._por_pagina(), 20)
        with mock.patch.dict(os.environ, {"GITLAB_POR_PAGINA": "500"}):
            self.assertEqual(sync_gitlab._por_pagina(), 100)
        with mock.patch.dict(os.environ, {"GITLAB_POR_PAGINA": "abc"}):
            self.assertEqual(sync_gitlab._por_pagina(), sync_gitlab.POR_PAGINA)


if __name__ == "__main__":
    unittest.main()
