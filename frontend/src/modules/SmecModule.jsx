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

const SMEC_REPORTS = [
  { grupo: "Potencia", id: "potencia_15min", label: "15 Minutos", interval: true, fin: false },
  { grupo: "Potencia", id: "potencia_hora", label: "Hora", interval: true, fin: false },
  { grupo: "Potencia", id: "potencia_max_diario", label: "Máxima Diaria", interval: false, fin: true },
  { grupo: "Potencia", id: "potencia_max_entre_fechas", label: "Máx. entre fechas", interval: false, fin: true },
  { grupo: "Energía", id: "energia_dia", label: "Día", interval: false, fin: true },
  { grupo: "Energía", id: "energia_mes", label: "Mes", interval: false, fin: true },
  { grupo: "Energía", id: "energia_anio", label: "Año", interval: false, fin: true },
  { grupo: "Índices", id: "factor_dia", label: "Factor Día", interval: false, fin: false },
  { grupo: "Índices", id: "factor_periodo", label: "Factor Periodo", interval: false, fin: true },
];
const GRUPOS = ["Potencia", "Energía", "Índices"];

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
  const report = useMemo(() => SMEC_REPORTS.find((r) => r.id === tipo) || SMEC_REPORTS[0], [tipo]);
  const [direccion, setDireccion] = usePersisted("smec.direccion", "iny");
  const [nivel, setNivel] = usePersisted("smec.nivel", "central");
  const [fechaInicio, setFechaInicio] = useState(iso(1));
  const [fechaFin, setFechaFin] = useState(iso(0));

  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);
  const [showTotals, setShowTotals] = useState(false);
  const [generadoEn, setGeneradoEn] = useState(null);
  const [copied, setCopied] = useState(false);
  const [vista, setVista] = useState("tabla");
  // Export conjunto: un solo .xlsx con hoja Inyección + hoja Retiro, con
  // TODAS las centrales de cada dirección (el árbol sólo muestra/selecciona
  // una dirección a la vez, así que la selección actual no decide esto).
  const [conjunto, setConjunto] = useState(false);
  const puedeConjunto = report.id === "potencia_15min" || report.id === "potencia_hora";
  const hoy = iso(0);
  const unidad = report.grupo === "Potencia" ? "kW"
    : report.grupo === "Energía" ? "kWh" : "factor 0–1";

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
    if (idsSel.length === 0) throw new Error("Seleccione al menos una central en el árbol.");
    return {
      tipo: report.id,
      fecha_inicio: fechaInicio,
      fecha_fin: report.fin ? fechaFin : null,
      unidades: idsSel,
      direccion,
      nivel,
    };
  };

  const generar = async () => {
    setRunning(true); setError(null); setResult(null);
    try {
      setResult(await api.smecReporte(buildBody()));
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
      await copyResultTsv(result);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch (e) { setError(`No se pudo copiar: ${e.message}`); }
  };

  const puedeGenerar = !treeLoading && idsSel.length > 0;

  // Series para el gráfico: columnas numéricas como eje X, una serie por
  // fila (en drill sólo los agentes). Se grafican hasta 8 (las de mayor
  // magnitud), manteniendo el orden original para que el color siga a la
  // entidad y no a su rango.
  const chartData = useMemo(() => {
    if (!result || !GRAFICABLES.has(report.id) || result.rows.length === 0) return null;
    const numCols = result.columns.filter((c) => c.format && c.format !== "datetime" && !c.hidden);
    if (numCols.length < 2) return null;
    const textKeys = result.columns.filter((c) => !c.format).map((c) => c.key);
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

  return (
    <div className="layout">
      <aside className="sidebar">
        <section className="panel">
          <h2>Fechas</h2>
          <label className="field"><span>{report.fin ? "Inicio" : "Fecha"}</span>
            <input type="date" value={fechaInicio} max={report.fin ? fechaFin : hoy} onKeyDown={onKey} onChange={(e) => setFechaInicio(e.target.value)} /></label>
          {report.fin && (
            <label className="field"><span>Final</span>
              <input type="date" value={fechaFin} min={fechaInicio} max={hoy} onKeyDown={onKey} onChange={(e) => setFechaFin(e.target.value)} /></label>
          )}
          <DatePresets single={!report.fin}
            onPick={(ini, fin) => { setFechaInicio(ini); if (report.fin) setFechaFin(fin); }} />
        </section>
        <section className="panel">
          <h2>Dirección</h2>
          <div className="opt-radios">
            <button type="button" aria-pressed={direccion === "iny"} className={`seg ${direccion === "iny" ? "seg--on" : ""}`} onClick={() => setDireccion("iny")}>Inyección</button>
            <button type="button" aria-pressed={direccion === "ret"} className={`seg ${direccion === "ret" ? "seg--on" : ""}`} onClick={() => setDireccion("ret")}>Retiro</button>
          </div>
        </section>
        <section className="panel panel--tree">
          <div className="panel-head">
            <h2>Centrales ({direccion === "iny" ? "Inyección" : "Retiro"})</h2>
            <div className="tree-actions">
              <button onClick={() => setAll(true)}>Todos</button>
              <button onClick={() => setAll(false)}>Ninguno</button>
              <button onClick={cargarArbol} title="Recargar">↻</button>
            </div>
          </div>
          <input className="tree-search" type="search" placeholder="Buscar central/agente…" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
          <div className="tree-count">{idsSel.length} central(es) seleccionada(s)</div>
          {treeLoading ? <div className="tree-empty">Cargando…</div>
            : treeError ? <div className="tree-error">{treeError}</div>
            : <Tree nodes={visibleTree} checked={checked} onToggle={onToggle} filter={filtro} />}
        </section>
      </aside>

      <main className="content">
        <nav className="tabs tabs--grouped">
          {GRUPOS.map((g) => (
            <div className="tab-group" key={g}>
              <span className="tab-group-label">{g}</span>
              {SMEC_REPORTS.filter((r) => r.grupo === g).map((r) => (
                <button key={r.id} className={`tab ${r.id === report.id ? "tab--active" : ""}`}
                  onClick={() => { setTipo(r.id); setResult(null); setError(null); }}>{r.label}</button>
              ))}
            </div>
          ))}
        </nav>

        <div className="report-head">
          <div>
            <h2 className="rpt-title">{report.grupo} › {report.label}</h2>
            <p className="rpt-hint">
              {report.interval ? "Elija el nivel, marque " : "Marque "}
              centrales de {direccion === "iny" ? "Inyección" : "Retiro"} en el árbol
              y pulse «Generar reporte».
            </p>
          </div>
          <span className={`selection-chip ${puedeGenerar ? "selection-chip--ready" : ""}`}>
            {idsSel.length} central(es) seleccionada(s)
          </span>
        </div>

        <div className="controls">
          <div className="controls-left">
            <div className="options">
              {report.interval && (
                <div className="opt-group">
                  <span className="opt-title">Nivel</span>
                  <div className="opt-radios">
                    {[["agente", "Agente"], ["central", "Central"], ["medidor", "Medidor"],
                      ["drill", "Árbol"]].map(([n, lbl]) => (
                      <button key={n} type="button" aria-pressed={nivel === n}
                        title={n === "drill" ? "Grilla jerárquica Agente → Central → Medidor" : undefined}
                        className={`seg ${nivel === n ? "seg--on" : ""}`} onClick={() => setNivel(n)}>
                        {lbl}</button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
          <div className="controls-right">
            <button className="btn btn--primary" onClick={generar} disabled={running || !puedeGenerar}
              title={!puedeGenerar ? "Seleccione al menos una central para generar el reporte." : undefined}>
              {running ? "Generando…" : "Generar reporte"}</button>
            <button className="btn" onClick={exportar}
              disabled={exporting || treeLoading || (!(conjunto && puedeConjunto) && idsSel.length === 0)}>
              {exporting ? "Exportando…" : conjunto && puedeConjunto ? "Exportar (2 hojas)" : "Exportar a Excel"}</button>
            {puedeConjunto && (
              <label className="totals-toggle" title="Un solo archivo con hoja Inyección + hoja Retiro, con todas las centrales de cada dirección (no depende de la selección del árbol).">
                <input type="checkbox" checked={conjunto} onChange={(e) => setConjunto(e.target.checked)} /> Conjunto (Iny.+Ret.)
              </label>
            )}
          </div>
        </div>

        {error && <div className="error-box">{error}</div>}
        {result && result.aviso && <div className="warn-box">⚠ {result.aviso}</div>}
        {result && result.rows.length > 0 && (
          <div className="result-meta">
            {result.rows.length} fila(s) · {result.columns.filter((c) => !c.hidden).length} columna(s)
            · {direccion === "iny" ? "Inyección" : "Retiro"} · valores en {unidad}
            {generadoEn && <> · generado {generadoEn.toLocaleTimeString("es-BO")}</>}
            <label className="totals-toggle">
              <input type="checkbox" checked={showTotals} onChange={(e) => setShowTotals(e.target.checked)} /> Totales
            </label>
            <button className="mini-btn" onClick={copiar} title="Copiar la tabla al portapapeles para pegarla en Excel">
              {copied ? "✓ Copiado" : "Copiar"}
            </button>
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
          </div>
        )}
        {vista === "grafico" && chartData && !running ? (
          <Chart series={chartData.series} labels={chartData.labels}
            unit={unidad} omitidas={chartData.omitidas} />
        ) : (
          <ResultsTable result={result} loading={running} showTotals={showTotals}
            placeholder={`Marque centrales de ${direccion === "iny" ? "Inyección" : "Retiro"} y pulse «Generar reporte».`}
            emptyHint="Sin datos para esta fecha/selección. Verifique la fecha, la dirección y las centrales marcadas." />
        )}
      </main>
    </div>
  );
}
