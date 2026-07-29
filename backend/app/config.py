"""Configuración leída desde variables de entorno / archivo .env.

En la app original la conexión Oracle se leía del Registry
(HKLM\\SOFTWARE\\ORACLE_DOTNET_ALL -> DATA_SOURCE) usando autenticación
del sistema operativo. Aquí usamos usuario/clave explícitos por .env,
que es lo más portable para un backend web de solo lectura.
"""
from functools import lru_cache
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv es opcional
    pass


class Settings:
    def __init__(self) -> None:
        self.oracle_user: str = os.getenv("ORACLE_USER", "")
        self.oracle_password: str = os.getenv("ORACLE_PASSWORD", "")
        # DSN puede ser "host:puerto/servicio" o el alias del tnsnames.
        self.oracle_dsn: str = os.getenv("ORACLE_DSN", "")
        # Modo thin (por defecto) no requiere Oracle Client instalado.
        self.oracle_thick: bool = os.getenv("ORACLE_THICK", "0") in ("1", "true", "True")
        self.oracle_lib_dir: str = os.getenv("ORACLE_LIB_DIR", "")
        # Pool
        self.pool_min: int = int(os.getenv("ORACLE_POOL_MIN", "1"))
        self.pool_max: int = int(os.getenv("ORACLE_POOL_MAX", "4"))
        # CORS (frontend dev)
        self.cors_origins: list[str] = os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        # Autenticación HTTP Basic opcional (si ambas están definidas).
        self.app_user: str = os.getenv("APP_USER", "")
        self.app_password: str = os.getenv("APP_PASSWORD", "")

    @property
    def auth_enabled(self) -> bool:
        return bool(self.app_user and self.app_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()
