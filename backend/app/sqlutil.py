"""Ayudas para construir cláusulas IN con binds numéricos seguros."""
from typing import Any


def in_clause(unidades: list[int], prefix: str = "u") -> tuple[str, dict[str, Any]]:
    """Devuelve ("(:u0, :u1, ...)", {u0: .., u1: ..}).

    A diferencia del código original (que anexaba un 0 centinela), NO se agrega
    ningún valor extra: el objeto id_objeto=0 existe en la base y hace fallar a
    funciones PL/SQL como ri_get_central(0). Si la lista viene vacía se usa
    ``(NULL)`` para mantener el SQL válido sin traer filas.
    """
    if not unidades:
        return "(NULL)", {}
    binds: dict[str, Any] = {}
    names: list[str] = []
    for i, u in enumerate(unidades):
        name = f"{prefix}{i}"
        binds[name] = int(u)
        names.append(f":{name}")
    return "(" + ", ".join(names) + ")", binds
