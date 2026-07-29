"""Conexión y pool a Oracle usando python-oracledb (solo lectura)."""
from contextlib import contextmanager
from typing import Any, Iterator

import oracledb

from .config import get_settings

_pool: oracledb.ConnectionPool | None = None


def init_pool() -> None:
    global _pool
    if _pool is not None:
        return
    s = get_settings()
    if s.oracle_thick:
        oracledb.init_oracle_client(lib_dir=s.oracle_lib_dir or None)
    if not (s.oracle_user and s.oracle_dsn):
        # Sin credenciales configuradas: no creamos pool (el endpoint /health
        # lo reportará). Permite levantar el server para desarrollo de frontend.
        return
    _pool = oracledb.create_pool(
        user=s.oracle_user,
        password=s.oracle_password,
        dsn=s.oracle_dsn,
        min=s.pool_min,
        max=s.pool_max,
        increment=1,
    )


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def pool_ready() -> bool:
    return _pool is not None


@contextmanager
def get_connection() -> Iterator[oracledb.Connection]:
    if _pool is None:
        raise RuntimeError(
            "Oracle no está configurado. Defina ORACLE_USER / ORACLE_PASSWORD / "
            "ORACLE_DSN en el archivo .env del backend."
        )
    conn = _pool.acquire()
    try:
        yield conn
    finally:
        _pool.release(conn)


def call_proc(proc: str, in_params: list[Any]) -> tuple[list[str], list[tuple]]:
    """Llama un procedimiento con un REF CURSOR de salida como último parámetro.

    Devuelve (columnas, filas). Se preservan columnas repetidas (algunos procs
    SMEC devuelven 'DIR' dos veces), por eso las filas son tuplas, no dicts.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            rc = cur.var(oracledb.DB_TYPE_CURSOR)
            cur.callproc(proc, in_params + [rc])
            result_cur = rc.getvalue()
            cols = [d[0].upper() for d in result_cur.description]
            rows = result_cur.fetchall()
            result_cur.close()
            return cols, rows


def query(sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Ejecuta un SELECT y devuelve filas como dicts con claves en minúscula."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            cols = [d[0].lower() for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
