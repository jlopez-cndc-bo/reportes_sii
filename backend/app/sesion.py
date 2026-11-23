"""Sesión de los editores de correcciones HFD: login contra Active Directory.

Los reportes siguen sin autenticación (PRODUCT.md); sólo corregir valores HFD exige
un usuario del dominio que esté en HFD_EDITORES. La contraseña se usa una vez para el
bind LDAPS y no se guarda. La sesión es una cookie HttpOnly firmada con HMAC.
"""
import base64
import hashlib
import hmac
import re
import secrets
import ssl
import time

from fastapi import Cookie, HTTPException, Response, status

from .config import get_settings

COOKIE = "hfd_sesion"
_SECRETO_PROCESO = secrets.token_bytes(32)


class CredencialesInvalidas(Exception): ...
class NoAutorizado(Exception): ...
class DirectorioNoDisponible(Exception): ...


def normalizar_usuario(usuario: str) -> str:
    """'CNDC\\jlopez', 'jlopez@cndc.bo' o 'JLopez' → 'jlopez'."""
    u = (usuario or "").strip().lower()
    u = u.split("\\")[-1]
    return u.split("@")[0]


def _secreto() -> bytes:
    s = get_settings().session_secret
    return s.encode() if s else _SECRETO_PROCESO


def _firma(datos: str) -> str:
    return hmac.new(_secreto(), datos.encode(), hashlib.sha256).hexdigest()


def crear_token(usuario: str, ahora: float | None = None) -> str:
    vence = int((ahora or time.time()) + get_settings().session_minutes * 60)
    datos = f"{usuario}|{vence}"
    return base64.urlsafe_b64encode(f"{datos}|{_firma(datos)}".encode()).decode()


def leer_token(token: str | None, ahora: float | None = None) -> str | None:
    """Usuario de un token válido y vigente; None si falta, está alterado o venció."""
    if not token:
        return None
    try:
        usuario, vence, firma = base64.urlsafe_b64decode(token.encode()).decode().split("|")
    except (ValueError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(firma, _firma(f"{usuario}|{vence}")):
        return None
    if int(vence) < (ahora or time.time()):
        return None
    # Revocar a alguien = sacarlo de HFD_EDITORES: deja de valer aunque tenga cookie.
    return usuario if usuario in get_settings().hfd_editores else None


def verificar_ad(usuario: str, password: str) -> None:
    """Bind LDAPS con usuario@dominio. Lanza CredencialesInvalidas o DirectorioNoDisponible."""
    from ldap3 import Connection, Server, Tls
    from ldap3.core.exceptions import LDAPBindError, LDAPException

    s = get_settings()
    if not password:  # un bind con contraseña vacía es "anónimo" y AD lo acepta
        raise CredencialesInvalidas()
    tls = Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=s.ad_ca_file or None)
    server = Server(s.ad_server, port=s.ad_port, use_ssl=True, tls=tls, connect_timeout=5)
    try:
        conn = Connection(server, user=f"{usuario}@{s.ad_domain}", password=password,
                          auto_bind=True, receive_timeout=10)
        conn.unbind()
    except LDAPBindError:
        raise CredencialesInvalidas()
    except LDAPException as e:
        raise DirectorioNoDisponible(str(e))


def iniciar(usuario: str, password: str, response: Response) -> str:
    u = normalizar_usuario(usuario)
    if not re.fullmatch(r"[a-z0-9._-]+", u):  # sin inyección LDAP ni '|' en el token
        raise CredencialesInvalidas()
    verificar_ad(u, password)
    if u not in get_settings().hfd_editores:
        raise NoAutorizado()
    response.set_cookie(COOKIE, crear_token(u), httponly=True, samesite="strict",
                        max_age=get_settings().session_minutes * 60, path="/api/hfd")
    return u


def cerrar(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/api/hfd")


def requiere_editor(hfd_sesion: str | None = Cookie(default=None)) -> str:
    """Dependencia FastAPI: usuario de la sesión o 401 (el frontend reabre el login)."""
    usuario = leer_token(hfd_sesion)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Inicie sesión para corregir valores.")
    return usuario
