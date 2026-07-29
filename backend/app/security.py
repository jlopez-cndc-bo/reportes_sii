"""Autenticación HTTP Basic opcional.

Si APP_USER y APP_PASSWORD están definidos en el entorno, protege los
endpoints; si no, no exige credenciales (útil para uso interno de solo lectura).
"""
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import get_settings

_basic = HTTPBasic(auto_error=False)


def require_auth(credentials: HTTPBasicCredentials | None = Depends(_basic)) -> None:
    s = get_settings()
    if not s.auth_enabled:
        return
    ok = credentials is not None and (
        secrets.compare_digest(credentials.username, s.app_user)
        and secrets.compare_digest(credentials.password, s.app_password)
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
            headers={"WWW-Authenticate": "Basic"},
        )
