import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import Tree from "../components/Tree";
import ResultsTable from "../components/ResultsTable";
import DatePresets from "../components/DatePresets";
import Chart from "../components/Chart";
import { collectIds, allKeys, toggleNode } from "../treeUtils";
import { isoDaysAgo as iso } from "../dateUtils";
import { copyResultTsv } from "../copyTsv";
import { usePersisted, usePersistedSet } from "../usePersisted";
import { Rail, QueryPanel, QSec, ResultBar, fechaCorta } from "../shell";
import { Refresh } from "../icons";

// Entradas del rail. Las que tienen `variantes` muestran un selector (título
// `opcion`) que elige el tipo interno que va a la API; ids, rutas y body no
// cambian, y "smec.reporte" sigue guardando el tipo interno.
const SMEC_REPORTS = [
  { grupo: "Mediciones", id: "potencia", label: "Potencia", unidad: "kW", opcion: "Resolución",
    descripcion: "Potencia de cada central a lo largo de un día, cada 15 minutos o por hora (promedio de sus cuatro intervalos).",
    variantes: [
      { id: "potencia_15min", label: "15 min", interval: true, fin: false,
        title: "Potencia de cada intervalo de 15 minutos." },
      { id: "potencia_hora", label: "Hora", interval: true, fin: false,
        title: "Potencia de cada hora: promedio de sus cuatro intervalos de 15 minutos." },
    ] },
  { grupo: "Mediciones", id: "potencia_max", label: "Potencia máxima", unidad: "kW", opcion: "Máxima",
    descripcion: "La potencia más alta de cada central: la de cada día del rango o una sola para todo el rango.",
    variantes: [
      { id: "potencia_max_diario", label: "Diaria", interval: false, fin: true,
        title: "La potencia más alta de cada día del rango." },
      { id: "potencia_max_entre_fechas", label: "Del rango", interval: false, fin: true,
        title: "La potencia más alta de todo el rango de fechas." },
    ] },
  { grupo: "Mediciones", id: "energia", label: "Energía", unidad: "kWh", opcion: "Período",
    descripcion: "Energía de cada central por día, mes o año del rango, con comparación opcional.",
    variantes: [
      { id: "energia_dia", label: "Día", interval: false, fin: true },
      { id: "energia_mes", label: "Mes", interval: false, fin: true },
      { id: "energia_anio", label: "Año", interval: false, fin: true },
    ] },
  { grupo: "Índices", id: "factor", label: "Factor de carga", unidad: "factor 0–1", opcion: "Período",
    descripcion: "Cuánto se acerca la potencia media a la máxima: energía ÷ (potencia máxima × horas), en un día (24 h) o en todo el rango.",
    variantes: [
      { id: "factor_dia", label: "Un día", interval: false, fin: false,
        title: "Factor de carga del día: energía ÷ (potencia máxima × 24 h)." },
      { id: "factor_periodo", label: "Rango", interval: false, fin: true,
        title: "Factor de carga del rango: energía ÷ (potencia máxima × horas del rango)." },
    ] },
  { grupo: "Índices", id: "capacidad", label: "Capacidad efectiva", opcion: "Agrupar por",
    unidad: "capacidad en MW, energía en kWh, factor 0–1", soloIny: true,
    descripcion: "Energía frente a la capacidad efectiva, por sistema o por tecnología (con su participación %): factor de planta = energía ÷ (capacidad × horas).",
    variantes: [
      { id: "capacidad_sistema", label: "Sistema", interval: false, fin: true },
      { id: "mix_tecnologia", label: "Tecnología", interval: false, fin: true },
    ] },
  // SIN completo: el total no depende del árbol. arbolOpcional = el árbol sólo
  // elige qué centrales se desglosan; sinArbol = no se usa.
  { grupo: "SIN", id: "pico_sin", descripcion: "Para cada día, el intervalo de 15 minutos con la mayor inyección del SIN y el aporte de cada central.",
    label: "Pico diario", interval: false, fin: true, unidad: "kW",
    soloIny: true, arbolOpcional: true },
  { grupo: "SIN", id: "conciliacion", descripcion: "Inyección menos retiro de cada día: pérdidas y desbalance de medición.",
    label: "Conciliación", interval: false, fin: true,
    sinArbol: true, unidad: "kWh" },
  { grupo: "SIN", id: "potencia_limitada", descripcion: "Cada evento de limitación con su límite, la potencia efectiva de la unidad y lo que midió su medidor.",
    label: "Potencia limitada", interval: false, fin: true,
    sinArbol: true, unidad: "MW" },
];
// Un "tipo" por cada consulta posible: la entrada con su variante aplanada
// (label = el de la entrada; variante = el texto del botón).
const TIPOS = SMEC_REPORTS.flatMap((e) => (e.variantes || [{}])
  .map((v) => ({ ...e, ...v, label: e.label, variante: v.label, entrada: e })));
const GRUPOS = ["Mediciones", "Índices", "SIN"];
// Más columnas que esto en el pico diario hace la tabla difícil de leer.
const PICO_COLS_AVISO = 10;

// "Comparar con" de Energía: la semana anterior sólo tiene sentido en Día.
// [clave, nombre (resumen y title), texto corto del botón para que entre en una línea]
const COMPARAR = [["ninguno", "Ninguno", "Ninguno"], ["semana", "Semana anterior", "Semana ant."],
  ["anio", "Año anterior", "Año ant."]];
const opcionesComparar = (id) => COMPARAR.filter(([k]) => k !== "semana" || id === "energia_dia");

// Reportes con serie temporal graficable (X = intervalos/días/meses/años).
const GRAFICABLES = new Set([
  "potencia_15min", "potencia_hora", "potencia_max_diario",
  "energia_dia", "energia_mes", "energia_anio",
]);

export default function SmecModule() {
  const [tree, setTree] = useState([]);
  // La selección se recuerda entre sesiones (keys de nodo estables).
  const [checked, setChecked] = usePersistedSet("smec.checked");
  const [treeLoading, setTreeLoading] = useState(false);
  const [treeError, setTreeError] = useState(null);
  const [filtro, setFiltro] = useState("");

  const [tipo, setTipo] = usePersisted("smec.reporte", "potencia_15min");
  // Fallback por si un id persistido ya no existe en esta versión.
  const report = useMemo(() => TIPOS.find((r) => r.id === tipo) || TIPOS[0], [tipo]);
  const [direccionGuardada, setDireccion] = usePersisted("smec.direccion", "iny");
  // Capacidad/Mix sólo existen para Inyección: se fuerza sin pisar la preferencia guardada.
  const direccion = report.soloIny ? "iny" : direccionGuardada;
  const [nivel, setNivel] = usePersisted("smec.nivel", "central");
  const [fechaInicio, setFechaInicio] = useState(iso(1));
  const [fechaFin, setFechaFin] = useState(iso(0));

  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);
  // Fila TOTAL por período visible por defecto en SMEC (se recuerda si se oculta).
  const [showTotals, setShowTotals] = usePersisted("smec.totales", true);
  const [generadoEn, setGeneradoEn] = useState(null);
  const [copied, setCopied] = useState(false);
  const [vista, setVista] = useState("tabla");
  // Export conjunto: un solo .xlsx con hoja Inyección + hoja Retiro, con
  // TODAS las centrales de cada dirección (el árbol sólo muestra/selecciona
  // una dirección a la vez, así que la selección actual no decide esto).
  const [conjunto, setConjunto] = useState(false);
  const puedeConjunto = report.id === "potencia_15min" || report.id === "potencia_hora";
  const esEnergia = report.id.startsWith("energia_");
  const [compararGuardado, setComparar] = usePersisted("smec.comparar", "ninguno");
  // Valor persistido que no aplica al reporte actual (p. ej. "semana" en Mes) → Ninguno.
  const comparar = esEnergia && opcionesComparar(report.id).some(([k]) => k === compararGuardado)
    ? compararGuardado : "ninguno";
  const compararLabel = COMPARAR.find(([k]) => k === comparar)[1].toLowerCase();
  // Indicadores de Potencia: sólo vista (se ocultan en el cliente, sin re-consultar).
  const [indicadores, setIndicadores] = usePersisted("smec.indicadores", true);
  const [picoPct, setPicoPct] = usePersisted("smec.picoPct", false);
  const esSin = report.grupo === "SIN";
  const hoy = iso(0);
  const unidad = report.unidad;

  const cargarArbol = useCallback(async () => {
    setTreeLoading(true); setTreeError(null);
    try {
      const nodes = await api.smecEstructura();
      setTree(nodes);
      // La selección previa (persistida) se conserva: las keys son estables.
    } catch (e) { setTreeError(e.message); setTree([]); }
    finally { setTreeLoading(false); }
  }, []);

  useEffect(() => { cargarArbol(); }, [cargarArbol]);

  const onToggle = useCallback((node) => setChecked((prev) => toggleNode(prev, node)), []);

  // El árbol muestra sólo la rama de la dirección activa: así la selección y
  // el resultado siempre coinciden (evita elegir centrales de una dirección y
  // consultar la otra → 0 filas).
  const visibleTree = useMemo(
    () => tree.filter((r) => r.direccion === direccion), [tree, direccion]);

  const setAll = (on) => setChecked(on ? new Set(allKeys(visibleTree)) : new Set());

  const idsSel = useMemo(
    () => [...new Set(collectIds(visibleTree, checked, "central"))],
    [visibleTree, checked]);

  const buildBody = () => {
    if (idsSel.length === 0 && !report.arbolOpcional && !report.sinArbol) {
      throw new Error("Seleccione al menos una central en el árbol.");
    }
    return {
      tipo: report.id,
      fecha_inicio: fechaInicio,
      fecha_fin: report.fin ? fechaFin : null,
      unidades: report.sinArbol ? [] : idsSel,
      direccion,
      nivel,
      comparar,
      porcentaje: report.id === "pico_sin" && picoPct,
    };
  };

  const vistaResult = useMemo(() => {
    if (!result || indicadores || !puedeConjunto) return result;
    return { ...result, columns: result.columns.map((c) => (c.resumen ? { ...c, hidden: true } : c)) };
  }, [result, indicadores, puedeConjunto]);

  const generar = async () => {
    setRunning(true); setError(null); setResult(null);
    try {
      const body = buildBody();
      // Se guarda con qué se comparó: el selector puede cambiar después.
      setResult({ ...(await api.smecReporte(body)), comparar: body.comparar, porcentaje: body.porcentaje });
      setGeneradoEn(new Date());
    } catch (e) { setError(e.message); }
    finally { setRunning(false); }
  };
  const onKey = (e) => { if (e.key === "Enter" && !running) generar(); };

  const exportar = async () => {
    setExporting(true); setError(null);
    try {
      if (conjunto && puedeConjunto) {
        await api.smecExportarConjunto({ tipo: report.id, fecha_inicio: fechaInicio, nivel });
      } else {
        await api.smecExportar(buildBody());
      }
    }
    catch (e) { setError(e.message); }
    finally { setExporting(false); }
  };

  const copiar = async () => {
    try {
      await copyResultTsv(vistaResult, { totales: showTotals });
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch (e) { setError(`No se pudo copiar: ${e.message}`); }
  };

  const requiereSeleccion = !report.arbolOpcional && !report.sinArbol;
  const puedeGenerar = !treeLoading && (idsSel.length > 0 || !requiereSeleccion);
  // Textos del SIN: el modo (kW / %) es el de la consulta generada, no el del selector.
  const descSin = (pct) => (report.id === "pico_sin"
    ? `Todo el SIN (inyección), valores en ${pct ? "% del pico" : "kW"}` : `Todo el SIN, valores en ${unidad}`);
  const estadoSin = report.sinArbol ? "Sin selección requerida"
    : idsSel.length ? `${idsSel.length} central(es) a desglosar` : "Solo total del SIN";

  // Series para el gráfico: columnas numéricas como eje X, una serie por
  // fila (en drill sólo los agentes). Se grafican hasta 8 (las de mayor
  // magnitud), manteniendo el orden original para que el color siga a la
  // entidad y no a su rango.
  const chartData = useMemo(() => {
    if (!result || !GRAFICABLES.has(report.id) || result.rows.length === 0) return null;
    // "resumen": Total/Máx/Mín/Promedio no son un período del eje X.
    const numCols = result.columns.filter((c) => c.format && c.format !== "datetime" && !c.hidden && !c.resumen);
    if (numCols.length < 2) return null;
    const textKeys = result.columns.filter((c) => !c.format && !c.resumen).map((c) => c.key);
    let rows = result.rows;
    if (rows[0]?._nivel !== undefined) rows = rows.filter((r) => r._nivel === 0);
    const todas = rows.map((r, i) => ({
      i,
      name: textKeys.map((k) => r[k]).filter(Boolean).join(" · ") || `fila ${i + 1}`,
      values: numCols.map((c) => (typeof r[c.key] === "number" ? r[c.key] : null)),
    }));
    const score = (s) => Math.max(0, ...s.values.map((v) => Math.abs(v ?? 0)));
    const top = [...todas].sort((a, b) => score(b) - score(a)).slice(0, 8)
      .sort((a, b) => a.i - b.i);
    return { series: top, omitidas: todas.length - top.length,
             labels: numCols.map((c) => c.label) };
  }, [result, report.id]);

  const pick = (id) => {
    setTipo(id); setResult(null); setError(null);
    // Al pasar a un tipo con rango, el final no puede quedar antes del inicio.
    if (TIPOS.find((r) => r.id === id).fin && fechaFin < fechaInicio) setFechaFin(fechaInicio);
  };
  const dirLabel = direccion === "iny" ? "Inyección" : "Retiro";
  const rango = report.fin
    ? `${fechaCorta(fechaInicio)} al ${fechaCorta(fechaFin)}`
    : fechaCorta(fechaInicio);

  return (
    <div className="layout">
      <Rail grupos={GRUPOS} reports={SMEC_REPORTS} activeId={report.entrada.id}
        onPick={(eid) => pick(eid === report.entrada.id ? report.id : TIPOS.find((t) => t.entrada.id === eid).id)} />

      <QueryPanel
        title={`${report.grupo} › ${report.label}`}
        desc={<p>{report.descripcion} {esSin ? `${descSin(picoPct)}.` : `Centrales de ${dirLabel}, valores en ${unidad}.`}</p>}
        resumen={`${report.variante ? `${report.variante}, ` : ""}` + (esSin ? `${rango}, ${estadoSin.toLowerCase()}`
          : `${rango}, ${dirLabel}, ${idsSel.length} central(es)${comparar !== "ninguno" ? `, vs. ${compararLabel}` : ""}`)}
        estado={esSin ? estadoSin : `${idsSel.length} central(es) seleccionada(s)`} listo={puedeGenerar}
        onGenerar={generar} running={running} puedeGenerar={puedeGenerar}
        footer={<>
          <button className="btn btn--primary" onClick={generar} disabled={running || !puedeGenerar}
            title={!puedeGenerar ? "Seleccione al menos una central para generar el reporte." : undefined}>
            {running ? "Generando…" : "Generar reporte"}</button>
          <button className="btn" onClick={exportar}
            disabled={exporting || treeLoading || (!(conjunto && puedeConjunto) && !puedeGenerar)}>
            {exporting ? "Exportando…" : conjunto && puedeConjunto ? "Exportar (2 hojas)" : "Exportar a Excel"}</button>
        </>}>
        <QSec title={report.fin ? "Fechas" : "Fecha"}>
          <div className="dates">
            <label className="dfield"><span>{report.fin ? "Inicio" : "Fecha"}</span>
              <input type="date" value={fechaInicio} max={report.fin ? fechaFin : hoy} onKeyDown={onKey} onChange={(e) => setFechaInicio(e.target.value)} /></label>
            {report.fin && (
              <label className="dfield"><span>Final</span>
                <input type="date" value={fechaFin} min={fechaInicio} max={hoy} onKeyDown={onKey} onChange={(e) => setFechaFin(e.target.value)} /></label>
            )}
          </div>
          <DatePresets single={!report.fin} ini={fechaInicio} fin={fechaFin}
            onPick={(ini, fin) => { setFechaInicio(ini); if (report.fin) setFechaFin(fin); }} />
        </QSec>

        {/* soloIny fuerza Inyección y oculta Dirección; la sección se oculta si no queda nada. */}
        {(report.entrada.variantes || (!report.soloIny && !report.sinArbol) || report.id === "pico_sin") && <QSec title="Opciones">
          <div className="options">
            {report.entrada.variantes && (
              <div className="opt-group">
                <span className="opt-title">{report.entrada.opcion}</span>
                <div className="opt-radios">
                  {report.entrada.variantes.map((v) => (
                    <button key={v.id} type="button" aria-pressed={report.id === v.id} title={v.title}
                      className={`seg ${report.id === v.id ? "seg--on" : ""}`}
                      onClick={() => report.id !== v.id && pick(v.id)}>{v.label}</button>
                  ))}
                </div>
              </div>
            )}
            {!report.soloIny && !report.sinArbol && (
            <div className="opt-group">
              <span className="opt-title">Dirección</span>
              <div className="opt-radios">
                <button type="button" aria-pressed={direccion === "iny"} className={`seg ${direccion === "iny" ? "seg--on" : ""}`} onClick={() => setDireccion("iny")}>Inyección</button>
                <button type="button" aria-pressed={direccion === "ret"} className={`seg ${direccion === "ret" ? "seg--on" : ""}`} onClick={() => setDireccion("ret")}>Retiro</button>
              </div>
            </div>
            )}
            {report.id === "pico_sin" && (
              <div className="opt-group">
                <span className="opt-title">Mostrar</span>
                <div className="opt-radios">
                  {[[false, "kW"], [true, "% del pico"]].map(([v, lbl]) => (
                    <button key={lbl} type="button" aria-pressed={picoPct === v}
                      className={`seg ${picoPct === v ? "seg--on" : ""}`} onClick={() => setPicoPct(v)}>{lbl}</button>
                  ))}
                </div>
              </div>
            )}
            {report.interval && (
              <div className="opt-group opt-group--stack">
                <span className="opt-title">Nivel</span>
                <div className="opt-radios opt-radios--compact">
                  {[["agente", "Agente"], ["central", "Central"], ["medidor", "Medidor"],
                    ["drill", "Jerárquico"]].map(([n, lbl]) => (
                    <button key={n} type="button" aria-pressed={nivel === n}
                      title={n === "drill" ? "Grilla jerárquica Agente → Central → Medidor" : undefined}
                      className={`seg ${nivel === n ? "seg--on" : ""}`} onClick={() => setNivel(n)}>
                      {lbl}</button>
                  ))}
                </div>
              </div>
            )}
            {esEnergia && (
              <div className="opt-group opt-group--stack">
                <span className="opt-title">Comparar con</span>
                <div className="opt-radios">
                  {opcionesComparar(report.id).map(([k, lbl, corto]) => (
                    <button key={k} type="button" aria-pressed={comparar === k} title={lbl}
                      className={`seg ${comparar === k ? "seg--on" : ""}`} onClick={() => setComparar(k)}>
                      {corto}</button>
                  ))}
                </div>
              </div>
            )}
            {puedeConjunto && (
              <label className="opt-check opt-check--wide" title="Un solo archivo con hoja Inyección + hoja Retiro, con todas las centrales de cada dirección (no depende de la selección del árbol).">
                <input type="checkbox" checked={conjunto} onChange={(e) => setConjunto(e.target.checked)} />
                Exportar Inyección y Retiro en un solo archivo
              </label>
            )}
          </div>
        </QSec>}

        {report.sinArbol ? (
          <QSec title="Centrales">
            <div className="tree-note">Este reporte usa todas las centrales del SIN.</div>
          </QSec>
        ) : (
        <QSec title={report.arbolOpcional ? "Centrales a desglosar (opcional)" : `Centrales de ${dirLabel}`} className="qsec--tree"
          aside={<span className="qsec-count">{idsSel.length} seleccionada(s)</span>}>
          {report.arbolOpcional && (
            <div className="tree-note">
              El total es siempre el del SIN; las centrales marcadas se muestran como columnas y
              las demás se agrupan en «Resto».
              {idsSel.length > PICO_COLS_AVISO && ` Con ${idsSel.length} centrales marcadas, la tabla tendrá ${idsSel.length + 1} columnas de aporte.`}
            </div>
          )}
          <div className="tree-tools">
            <input className="tree-search" type="search" aria-label="Buscar central o agente" placeholder="Buscar central o agente…" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
            <button type="button" className="pill-btn" onClick={() => setAll(true)}>Todos</button>
            <button type="button" className="pill-btn" onClick={() => setAll(false)}>Ninguno</button>
            <button type="button" className="pill-btn pill-btn--icon" onClick={cargarArbol} title="Recargar el árbol" aria-label="Recargar el árbol"><Refresh /></button>
          </div>
          {treeLoading ? <div className="tree-empty">Cargando…</div>
            : treeError ? <div className="tree-error">{treeError}</div>
            : <div className="tree-wrap">
                <Tree nodes={visibleTree} checked={checked} onToggle={onToggle} filter={filtro} collapsed />
              </div>}
        </QSec>
        )}
      </QueryPanel>

      <main className="content">
        {error && <div className="error-box" role="alert">{error}</div>}
        {result && result.aviso && <div className="warn-box">⚠ {result.aviso}</div>}
        <ResultBar result={vistaResult} generadoEn={generadoEn}
          extra={esSin ? descSin(result?.porcentaje)
            : `${dirLabel}, valores en ${unidad}${result && result.comparar !== "ninguno"
            ? `, vs. ${COMPARAR.find(([k]) => k === result.comparar)[1].toLowerCase()}` : ""}`}
          showTotals={showTotals} setShowTotals={setShowTotals} copied={copied} onCopiar={copiar}>
          {puedeConjunto && (
            <label className="totals-toggle" title="Máx, mín, promedio, energía, arranques, rampa… al final de cada fila. El Excel siempre los incluye.">
              <input type="checkbox" checked={indicadores} onChange={(e) => setIndicadores(e.target.checked)} /> Indicadores
            </label>
          )}
          {chartData && (
            <span className="vista-toggle">
              <button type="button" aria-pressed={vista === "tabla"}
                className={`seg ${vista === "tabla" ? "seg--on" : ""}`}
                onClick={() => setVista("tabla")}>Tabla</button>
              <button type="button" aria-pressed={vista === "grafico"}
                className={`seg ${vista === "grafico" ? "seg--on" : ""}`}
                onClick={() => setVista("grafico")}>Gráfico</button>
            </span>
          )}
        </ResultBar>
        {vista === "grafico" && chartData && !running ? (
          <Chart series={chartData.series} labels={chartData.labels}
            unit={unidad} omitidas={chartData.omitidas} />
        ) : (
          <ResultsTable result={vistaResult} loading={running} showTotals={showTotals}
            placeholder={esSin ? "Pulse «Generar reporte»." : `Marque centrales de ${dirLabel} y pulse «Generar reporte».`}
            emptyHint={esSin ? "Sin datos para estas fechas."
              : "Sin datos para esta fecha/selección. Verifique la fecha, la dirección y las centrales marcadas."} />
        )}
      </main>
    </div>
  );
}
