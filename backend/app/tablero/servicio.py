"""Arma lo que muestra el tablero: tarjetas con comparaciones y tendencia, «Ahora» y alertas.

Caché en memoria por (métrica, rango): los meses ya pasados se guardan 12 h y lo reciente 5
min. shortcut: caché en memoria del proceso (se pierde al reiniciar; el arranque la precalienta);
pasar a caché en archivos + timer si las consultas dejan de responder en < 1 s.
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any

from ..potencia_efectiva import vigencia
from . import fuentes as F
from .config import Config, Indicador, cargar
from .periodos import Periodo, Rango, ahora, resolver, ultimos_meses

_cache: dict[tuple, tuple[float, Any]] = {}
_lock = threading.Lock()
# Pool de Oracle = 4 conexiones por defecto: no pedir más en paralelo.
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tablero")


def _cacheado(clave: tuple, ttl: float, fn):
    with _lock:
        hit = _cache.get(clave)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    valor = fn()
    with _lock:
        _cache[clave] = (time.monotonic() + ttl, valor)
    return valor


def _ttl(r: Rango, now: datetime) -> float:
    # Lo de hace más de 7 días casi no cambia (SMEC recarga el mes al cierre mensual).
    return 12 * 3600 if r.hasta < now - timedelta(days=7) else 300


def _calcular(ind: Indicador, r: Rango, now: datetime) -> dict[str, Any]:
    fn = F.METRICAS[ind.metrica]
    params = dict(ind.parametros)
    if ind.metrica in F.CON_AHORA:
        params["ahora"] = now
    clave = (ind.metrica, tuple(sorted(ind.parametros.items())), r.desde, r.hasta)
    return _cacheado(clave, _ttl(r, now), lambda: fn(r, **params))


def semaforo(valor: float | None, ind: Indicador, cfg: Config, dia) -> dict[str, Any] | None:
    """Estado contra el umbral vigente; None = «Meta por definir» (no se inventan metas)."""
    vig = sorted((u for u in cfg.umbrales if u.kpi_id == ind.id and u.vigente_desde <= dia.isoformat()),
                 key=lambda u: u.vigente_desde)
    if valor is None or not vig:
        return None
    u = vig[-1]
    if ind.direccion == "up":
        estado = "verde" if valor >= u.verde else "ambar" if valor >= u.ambar else "rojo"
    else:
        estado = "verde" if valor <= u.verde else "ambar" if valor <= u.ambar else "rojo"
    return {"estado": estado, "meta": u.meta, "aprobado_por": u.aprobado_por}


def comparar(actual: float | None, anterior: float | None, ind: Indicador) -> dict[str, Any] | None:
    """Variación relativa (%) o en puntos (para indicadores en %). None si falta un lado."""
    if actual is None or anterior is None:
        return None
    if ind.comparar == "puntos":
        delta = actual - anterior
    elif anterior == 0:
        return None
    else:
        delta = (actual - anterior) / abs(anterior) * 100
    mejor = None if abs(delta) < 1e-9 else (delta > 0) == (ind.direccion == "up")
    return {"delta": delta, "mejor": mejor}


def _tarjeta(ind: Indicador, p: Periodo, cfg: Config, now: datetime) -> dict[str, Any]:
    nivel = next(n for n in cfg.niveles_dato if n.id == ind.nivel_dato_id)
    meses = ultimos_meses(p.rango.hasta, cfg.inicio.meses_tendencia, now)
    rangos = [p.rango, *(r for _, r in p.comparaciones), *meses]
    puntos = list(_pool.map(lambda r: _calcular(ind, r, now), rangos))
    actual, comps, tend = puntos[0], puntos[1:1 + len(p.comparaciones)], puntos[1 + len(p.comparaciones):]
    hist = None
    if ind.maximo_historico and ind.metrica == "smec_potencia_punta":
        hist = _cacheado(("hist", ind.metrica), 6 * 3600, F.smec_potencia_punta_historica)
    return {
        "id": ind.id, "nombre": ind.nombre, "descripcion": ind.descripcion, "unidad": ind.unidad,
        "decimales": ind.decimales, "direccion": ind.direccion, "comparar": ind.comparar,
        "fuente": ind.fuente, "responsable": ind.responsable,
        "nivel": {"id": nivel.id, "rotulo": nivel.rotulo, "es_oficial": nivel.es_oficial},
        **actual,
        "comparaciones": [
            {"etiqueta": et, "valor": c["valor"], "calidad": c["calidad"],
             **(comparar(actual["valor"], c["valor"], ind) or {"delta": None, "mejor": None})}
            for (et, _), c in zip(p.comparaciones, comps)],
        "tendencia": [{"etiqueta": r.etiqueta, "valor": t["valor"], "calidad": t["calidad"]}
                      for r, t in zip(meses, tend)],
        "maximo_historico": hist,
        "semaforo": semaforo(actual["valor"], ind, cfg, p.rango.desde.date()),
    }


def inicio(periodo: str | None) -> dict[str, Any]:
    cfg, now = cargar(), ahora()
    p = resolver(periodo, now)
    dominios = {d.id: d for d in cfg.dominios}
    monitores = []
    for m in cfg.inicio.monitores:
        d = dominios[m.dominio_id]
        monitores.append({
            "dominio": d.id, "nombre": d.nombre, "modulo": d.modulo,
            "principal": _tarjeta(cfg.indicador(m.principal), p, cfg, now),
            "secundarios": [_tarjeta(cfg.indicador(k), p, cfg, now) for k in m.secundarios],
        })
    return {
        "periodo": {"id": p.id, "etiqueta": p.rango.etiqueta, "en_curso": p.en_curso,
                    "desde": p.rango.desde.isoformat(), "hasta": p.rango.hasta.isoformat()},
        "generado": now.isoformat(),
        "monitores": monitores,
        "niveles": [n.model_dump() for n in cfg.niveles_dato],
        "metas_cargadas": len(cfg.umbrales),
    }


def alertas(hfd: dict | None, smec_ultimo, now: datetime, cfg: Config) -> list[dict[str, str]]:
    """Avisos accionables, ya redactados; máximo 5. Pura salvo `vigencia` (tabla en código)."""
    lim = cfg.limites
    out = []
    if hfd is None:
        out.append({"nivel": "alta", "texto": "HFD sin datos de hoy ni de ayer: revisar la carga de rs7."})
    else:
        # El intervalo hh:mm cubre hasta hh:mm+15: el rezago se mide desde su fin.
        rezago = (now - datetime.fromisoformat(hfd["fecha_dato"])).total_seconds() / 60 - 15
        if rezago > lim.hfd_atrasado_min:
            out.append({"nivel": "alta", "texto": f"La carga HFD está atrasada: último intervalo hace "
                                                  f"{int(rezago)} min."})
        if hfd["congeladas"]:
            n = len(hfd["congeladas"])
            out.append({"nivel": "media", "texto": f"{n} señal(es) de generación HFD sin cambio en las "
                                                   f"últimas {lim.hfd_congelada_lecturas} lecturas."})
    if smec_ultimo is None or (now.date() - smec_ultimo).days > lim.smec_atrasado_dias:
        cuando = smec_ultimo.strftime("%d/%m/%Y") if smec_ultimo else "sin datos en 90 días"
        out.append({"nivel": "media", "texto": f"SMEC atrasado: último día cargado {cuando}."})
    vig = vigencia(now.date())
    if vig is None:
        out.append({"nivel": "alta", "texto": "No hay potencia efectiva oficial vigente hoy: la "
                                              "disponibilidad queda en «-». Cargar el archivo semestral."})
    elif (vig[1] - now.date()).days <= lim.pef_aviso_dias:
        out.append({"nivel": "media", "texto": f"La potencia efectiva oficial vence el "
                                               f"{vig[1]:%d/%m/%Y}: cargar el archivo del semestre siguiente."})
    return out[:5]


def ahora_sistema() -> dict[str, Any]:
    cfg, now = cargar(), ahora()

    def calc():
        f_hfd = _pool.submit(F.hfd_ahora, now.date(), cfg.limites.hfd_congelada_lecturas)
        f_ind = _pool.submit(F.unidades_indisponibles, now)
        f_smec = _pool.submit(F.smec_ultimo_dia)
        hfd, ind, smec = f_hfd.result(), f_ind.result(), f_smec.result()
        return {
            "generado": now.isoformat(), "hfd": hfd, "indisponibles": ind,
            "smec_ultimo_dia": smec.isoformat() if smec else None,
            "alertas": alertas(hfd, smec, now, cfg),
        }
    return _cacheado(("ahora",), 60, calc)


def precalentar() -> None:
    """Llena la caché al arrancar para que la primera visita no espere."""
    try:
        ahora_sistema()
        inicio(None)
    except Exception:  # sólo precalienta; el pedido real mostrará el error
        logging.getLogger(__name__).exception("No se pudo precalentar el tablero")


def dia(fecha_txt: str | None) -> dict[str, Any]:
    """Operación de un día: curvas HFD, punta y energía oficiales SMEC e indisponibilidades."""
    now = ahora()
    try:
        d = datetime.strptime(fecha_txt, "%Y-%m-%d").date() if fecha_txt else now.date()
    except ValueError:
        raise ValueError(f"Fecha no válida: «{fecha_txt}». Use AAAA-MM-DD.")
    if d > now.date():
        raise ValueError("La fecha no puede ser futura.")
    hoy = d == now.date()
    r = Rango(datetime.combine(d, datetime.min.time()),
              min(datetime.combine(d + timedelta(days=1), datetime.min.time()), now), "")

    def calc():
        f_hfd = _pool.submit(F.hfd_dia, d)
        f_punta = _pool.submit(F.smec_potencia_punta, r)
        f_ener = _pool.submit(F.smec_demanda_energia, r)
        f_ind = _pool.submit(F.unidades_indisponibles, now) if hoy else _pool.submit(F.indisponibles_dia, d, now)
        f_temp = _pool.submit(F.temperatura_dia, d)
        punta, energia, dia_smec = f_punta.result(), f_ener.result(), d
        temps = f_temp.result()
        # Temperatura de cada zona en la hora que contiene el intervalo de la punta (mismo día).
        hp = int(punta["detalle"]["fecha_hora"][11:13]) if punta["valor"] is not None else None
        for t in temps:
            t["a_la_punta"] = t["valores"][hp] if hp is not None else None
        if punta["valor"] is None:
            # SMEC se carga al cerrar la transacción diaria: se muestra su último día, rotulado.
            ultimo = F.smec_ultimo_dia()
            if ultimo and ultimo < d:
                ru = Rango(datetime.combine(ultimo, datetime.min.time()),
                           datetime.combine(ultimo + timedelta(days=1), datetime.min.time()), "")
                punta, energia, dia_smec = F.smec_potencia_punta(ru), F.smec_demanda_energia(ru), ultimo
        # Potencia del parque: en la hora de punta (si la punta es del día) o en la última hora con
        # temperatura (hoy). Margen = disponible − punta, sólo con la punta del mismo día.
        instante = None
        if dia_smec == d and punta["valor"] is not None:
            instante = datetime.fromisoformat(punta["detalle"]["fecha_hora"])
        elif temps:
            ult = max((i for t in temps for i, v in enumerate(t["valores"]) if v is not None), default=None)
            instante = None if ult is None else datetime.combine(d, datetime.min.time()) + timedelta(hours=ult)
        potencia = F.potencia_parque(d, instante, now) if instante else None
        if potencia and dia_smec == d and punta["valor"] is not None:
            potencia["punta"] = round(punta["valor"], 1)
            potencia["margen"] = round(potencia["disponible"] - punta["valor"], 1)
        return {"fecha": d.isoformat(), "es_hoy": hoy, "generado": now.isoformat(),
                "hfd": f_hfd.result(), "punta": punta, "energia": energia, "dia_smec": dia_smec.isoformat(),
                "indisponibles": f_ind.result(), "temperaturas": temps, "potencia": potencia}
    return _cacheado(("dia", d), 60 if hoy or d >= now.date() - timedelta(days=3) else 12 * 3600, calc)
