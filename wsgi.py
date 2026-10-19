"""Ponto de entrada para hospedagem (PythonAnywhere e similares).

No arquivo WSGI do servidor, defina as variaveis de ambiente (STRIKES_DB, ACCESS_CODE,
SECRET_KEY, COOKIE_SECURE) e importe `application` daqui. Os segredos ficam so no servidor,
nunca neste repositorio.
"""
from app import app as application, backup_db_if_needed, init_db

backup_db_if_needed()
init_db()
