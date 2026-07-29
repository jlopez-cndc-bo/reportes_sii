# Reportes SII — Indisponibilidades (versión web)

Migración a web del módulo **INDISP** de la aplicación de escritorio.
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

Prueba de humo contra la base (valida los 5 reportes):

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

## Reportes migrados

| # | Reporte | Endpoint |
|---|---------|----------|
| 1 | Potencias Disponibles | `POST /api/reportes/potencias-disponibles` |
| 2 | Potencias Indisponibles | `POST /api/reportes/potencias-indisponibles` |
| 3 | Horas de Disponibilidad | `POST /api/reportes/horas-disponibilidad` |
| 4 | Horas de No Disponibilidad | `POST /api/reportes/horas-no-disponibilidad` |
| 5 | Horas por Tipo de Operación | `POST /api/reportes/horas-tipo-operacion` |
| — | Árbol de componentes | `POST /api/arbol` |
| — | Exportar a Excel (cada reporte) | `POST /api/exportar/{reporte}` |

## Módulo SMEC (energía y potencia)

Segundo módulo migrado (Etapa 1 del plan). Reusa los paquetes Oracle
`SMEC_POTENCIA_API` y `PKG_OBJETOS` + la tabla `DW_RELACIONES`.

| Reporte | Notas |
|---|---|
| Potencia 15 min / Hora | Jerárquico Agente/Central/Medidor (selector de nivel), toggle Inyección/Retiro, columnas por intervalo |
| Potencia Máxima Diaria / entre fechas | Tabla plana por dirección |
| Energía Día / Mes / Año | Día y Mes desde procs; Año y Mes con SQL propio (ver notas) |
| Factor de carga Día / Periodo | **Pendiente**: falta confirmar el procedimiento Oracle |

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
