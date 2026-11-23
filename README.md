# Reportes SII (versión web)

Migración a web de la aplicación de escritorio. Primer módulo: **Reporte de la Operación**
(antes «Indisponibilidades», módulo **INDISP**).
Backend **FastAPI** (Python) + frontend **React** (Vite). Sólo lectura sobre Oracle.

## Estructura

```
web/
├── backend/   FastAPI + oracledb (modo thin, sin cliente Oracle)
│   └── app/
│       ├── config.py, db.py, constants.py, filters.py, sqlutil.py, schemas.py
│       ├── tree.py                 árbol Agente → Central → Unidad
│       ├── reports/                un módulo por reporte
│       └── routers/reports.py      endpoints REST
└── frontend/  React + Vite
```

## 1. Backend

```powershell
cd web/backend
py -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt

# Configurar conexión (una sola vez):
copy .env.example .env
#  ...editar .env con ORACLE_USER / ORACLE_PASSWORD / ORACLE_DSN

# Levantar API en http://localhost:8000  (docs en /docs)
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

Prueba de humo contra la base (valida los 3 reportes):

```powershell
./.venv/Scripts/python.exe smoke_test.py --inicio 2025-01-01 --fin 2025-01-07
```

## 2. Frontend

```powershell
cd web/frontend
npm install
npm run dev          # http://localhost:5173  (proxy /api -> :8000)
```

## 3. Modo producción (una sola URL)

Compila el frontend y el backend lo sirve en la misma dirección:

```powershell
cd web/frontend && npm run build      # genera frontend/dist
cd ../backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
#  -> app completa en http://localhost:8000  (API + UI)
```

## Tests

```powershell
cd web/backend
./.venv/Scripts/python.exe -m pytest -q     # lógica de pivoteo/árbol (sin BD)
```

## Seguridad

- Usar un **usuario Oracle de solo lectura** (no `desa/desa`, que es de desarrollo).
- Autenticación HTTP Basic **opcional**: definir `APP_USER` y `APP_PASSWORD` en `.env`.
- El `.env` está en `.gitignore` (no se versiona).

## Reportes migrados: Reporte de la Operación

| Grupo | Reporte | Endpoint |
|---|---|---|
| Detalle | Disponibilidad por componente | `POST /api/reportes/horas-disponibilidad` |
| Detalle | Eventos | `POST /api/reportes/horas-no-disponibilidad` |
| Detalle | Horas por tipo de operación | `POST /api/reportes/horas-tipo-operacion` |
| — | Árbol de componentes | `POST /api/arbol` |
| — | Exportar a Excel (cada reporte) | `POST /api/exportar/{reporte}` |

## Módulo SMEC (energía y potencia)

Segundo módulo migrado (Etapa 1 del plan). Reusa los paquetes Oracle
`SMEC_POTENCIA_API` y `PKG_OBJETOS` + la tabla `DW_RELACIONES`.

Módulo «Sistema de Medición Comercial» en la UI. Cada reporte del rail elige su
variante con una opción; el `tipo` que va a la API es el de la variante.

| Grupo | Reporte | Opción → `tipo` | Notas |
|---|---|---|---|
| Mediciones | Potencia | Resolución: 15 min / Hora → `potencia_15min` / `potencia_hora` | Nivel Agente/Central/Medidor/Jerárquico, Inyección/Retiro, columnas por intervalo |
| Mediciones | Potencia máxima | Máxima: Diaria / Del rango → `potencia_max_diario` / `potencia_max_entre_fechas` | Tabla plana por dirección |
| Mediciones | Energía | Período: Día / Mes / Año → `energia_dia` / `energia_mes` / `energia_anio` | Día y Mes desde procs; Año y Mes con SQL propio (ver notas) |
| Índices | Factor de carga | Período: Un día / Rango → `factor_dia` / `factor_periodo` | `TRUNC(E/(P·h),2)` |
| Índices | Capacidad efectiva | Agrupar por: Sistema / Tecnología → `capacidad_sistema` / `mix_tecnologia` | Sólo inyección |
| SIN | Pico diario · Conciliación · Potencia limitada | — | `pico_sin` / `conciliacion` / `potencia_limitada` |

Endpoints: `GET /api/smec/estructura`, `POST /api/smec/reporte`, `POST /api/smec/exportar`.

**Notas / hallazgos:**
- `SMEC_POTENCIA_API.P_GET_ENERGIA_MES` tiene un **bug** (SQL dinámico con 4
  binds y sólo 3 en el `USING` → ORA-01008). Se sortea replicando la consulta
  correcta en Python (`app/smec/reportes.py: energia_mes`). Conviene que el DBA
  lo corrija en la base.
- **Energía Año** no tiene proc; se agrega `sm_energia_cen_dia` por año.
- **Factor de carga** existe sólo como funciones escalares
  (`SMEC.GET_FACTOR` / `CALCULATE_FACTOR`); falta un proc de reporte para
  exponerlo. Queda como pendiente con aviso en la UI.

## Notas de la migración

- La lógica SQL y de pivoteo se tradujo fielmente desde las clases C#
  (`PotenciasDisponibles`, `Potencias_Indisponibles`, `HorasDisponibilidad`,
  `HorasNoDisponibilidad`, `HorasPorTipodeOperacion`, `General`).
- Se reutilizan las funciones PL/SQL existentes en Oracle
  (`ri_disponibilidad_unidad`, `ri_get_potencia_unidad`, `ri_get_central`,
  `ri_get_AGENTE`, `ri_get_potencia`).
- La conexión ya no usa el Registry ni autenticación del SO; se configura por
  `.env` con un usuario de solo lectura.
- **Fase 2 (fuera de alcance actual):** `Reporte_compracion` (comparación
  programado vs. real, sólo Excel) y `FrmProgIndisponibilidades` (programación
  de mantenimiento).
```
