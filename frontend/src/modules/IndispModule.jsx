import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { REPORTS } from "../reports";
import Tree from "../components/Tree";
import OptionsPanel from "../components/OptionsPanel";
import ResultsTable from "../components/ResultsTable";
import DatePresets from "../components/DatePresets";
import { collectIds, allKeys, toggleNode, countLeaves } from "../treeUtils";
import { isoDaysAgo } from "../dateUtils";
import { copyResultTsv } from "../copyTsv";
import { usePersisted, usePersistedSet } from "../usePersisted";

export default function IndispModule() {
  const [fechaInicio, setFechaInicio] = useState(isoDaysAgo(7));
  const [fechaFin, setFechaFin] = useState(isoDaysAgo(0));

  const [tree, setTree] = useState([]);
  // La selección se recuerda entre sesiones (keys de nodo estables).
  const [checked, setChecked] = usePersistedSet("indisp.checked");
  const [treeLoading, setTreeLoading] = useState(false);
  const [treeError, setTreeError] = useState(null);
  const [filtro, setFiltro] = useState("");

  const GRUPOS = useMemo(() => [...new Set(REPORTS.map((r) => r.grupo))], []);
  const [activeId, setActiveId] = usePersisted("indisp.reporte", REPORTS[0].id);
  // Fallback por si un id persistido ya no existe en esta versión.
  const activeReport = useMemo(() => REPORTS.find((r) => r.id === activeId) || REPORTS[0], [activeId]);
  const [optState, setOptState] = useState(() =>
    Object.fromEntries(REPORTS.map((r) => [r.id, { ...r.defaults }]))
  );
  // Alcance del árbol derivado de los tipos de operación activos del
  // reporte (152/153 → generadores; 155/156 → todos los tipos; etc.).
  const compFlag = useMemo(
    () => activeReport.componentesFor(optState[activeReport.id]),
    [activeReport, optState]);

  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);
  const [showTotals, setShowTotals] = useState(false);
  const [generadoEn, setGeneradoEn] = useState(null);
  const [copied, setCopied] = useState(false);

  const cargarArbol = useCallback(async () => {
    setTreeLoading(true);
    setTreeError(null);
    try {
      const nodes = await api.arbol({
        fecha_inicio: fechaInicio,
        fecha_fin: fechaFin,
        tipos_operacion: { op_normal: true, programada: true, forzada: true },
        componentes: compFlag,
        modo: "todos",
      });
      setTree(nodes);
      // Se preserva la selección previa entre recargas (las keys son estables)
      // y el árbol NO se desmonta: la actualización es en el lugar, así que
      // la expansión y el scroll también se conservan.
    } catch (e) {
      setTreeError(e.message);
      // Se conserva el árbol y la selección actuales; sólo se avisa el error.
    } finally {
      setTreeLoading(false);
    }
  }, [fechaInicio, fechaFin, compFlag]);

  useEffect(() => { cargarArbol(); }, [cargarArbol]);

  const onToggle = useCallback((node) => setChecked((prev) => toggleNode(prev, node)), []);

  // El backend ya devuelve el estado operativo vigente a hoy, evitando
  // relaciones históricas duplicadas entre agentes, centrales y unidades.
  const visibleTree = tree;
  const totales = useMemo(() => ({
    todos: countLeaves(tree),
  }), [tree]);

  const setAll = (on) => setChecked(on ? new Set(allKeys(visibleTree)) : new Set());
  const getIds = useCallback((tipo) => collectIds(visibleTree, checked, tipo), [visibleTree, checked]);
  const seleccionados = useMemo(() => collectIds(visibleTree, checked, "componente").length, [visibleTree, checked]);

  const buildBody = () => {
    const body = activeReport.buildBody({ fechaInicio, fechaFin }, optState[activeReport.id], getIds);
    if (!activeReport.sinArbol && (!body.unidades || body.unidades.length === 0))
      throw new Error("Seleccione al menos un componente en el árbol.");
    return body;
  };

  const generar = async () => {
    setRunning(true); setError(null); setResult(null);
    try {
      setResult(await api.reporte(activeReport.endpoint, buildBody()));
      setGeneradoEn(new Date());
    } catch (e) { setError(e.message); }
    finally { setRunning(false); }
  };
  const onKey = (e) => { if (e.key === "Enter" && !running) generar(); };

  const exportar = async () => {
    setExporting(true); setError(null);
    try { await api.exportar(activeReport.endpoint, buildBody()); }
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

  const puedeGenerar = activeReport.sinArbol || (!treeLoading && seleccionados > 0);
  const estadoSeleccion = activeReport.sinArbol
    ? "Sin selección requerida"
    : `${seleccionados} componente(s) seleccionado(s)`;

  return (
    <div className="layout">
      <aside className="sidebar">
        <section className="panel">
          <h2>{activeReport.soloFecha ? "Fecha" : "Rango de fechas"}</h2>
          <label className="field"><span>{activeReport.soloFecha ? "Fecha" : "Inicio"}</span>
            <input type="date" value={fechaInicio} max={activeReport.soloFecha ? undefined : fechaFin} onKeyDown={onKey} onChange={(e) => setFechaInicio(e.target.value)} /></label>
          {!activeReport.soloFecha && (
            <label className="field"><span>Final</span>
              <input type="date" value={fechaFin} min={fechaInicio} onKeyDown={onKey} onChange={(e) => setFechaFin(e.target.value)} /></label>
          )}
          <DatePresets single={activeReport.soloFecha}
            onPick={(ini, fin) => { setFechaInicio(ini); if (!activeReport.soloFecha) setFechaFin(fin); }} />
        </section>
        <section className="panel panel--tree">
          {activeReport.sinArbol && (
            <div className="tree-note">
              Este reporte no usa el árbol: considera todas las unidades con
              programación registrada.
            </div>
          )}
          <div className="panel-head">
            <h2>Componentes</h2>
            <div className="tree-actions">
              <button onClick={() => setAll(true)}>Todos</button>
              <button onClick={() => setAll(false)}>Ninguno</button>
              <button onClick={cargarArbol} title="Recargar">↻</button>
            </div>
          </div>
          <input className="tree-search" type="search" placeholder="Buscar componente…" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
          <div className="tree-count">
            {seleccionados} seleccionado(s) · {totales.todos} componente(s) vigente(s) a hoy
            {treeLoading && tree.length > 0 && <span className="tree-refresh"> · actualizando…</span>}
          </div>
          {treeError && <div className="tree-error">{treeError}</div>}
          {tree.length === 0
            ? <div className="tree-empty">{treeLoading ? "Cargando…" : "Sin componentes."}</div>
            : <div className={`tree-wrap ${treeLoading ? "tree-wrap--refreshing" : ""}`}>
                <Tree nodes={visibleTree} checked={checked} onToggle={onToggle} filter={filtro} />
              </div>}
        </section>
      </aside>

      <main className="content">
        <nav className="tabs tabs--grouped">
          {GRUPOS.map((g) => (
            <div className="tab-group" key={g}>
              <span className="tab-group-label">{g}</span>
              {REPORTS.filter((r) => r.grupo === g).map((r) => (
                <button key={r.id} className={`tab ${r.id === activeReport.id ? "tab--active" : ""}`}
                  onClick={() => { setActiveId(r.id); setResult(null); setError(null); }}>{r.label}</button>
              ))}
            </div>
          ))}
        </nav>

        <div className="report-head">
          <div>
            <h2 className="rpt-title">{activeReport.grupo} › {activeReport.label}</h2>
            <p className="rpt-hint">{activeReport.descripcion}</p>
          </div>
          <span className={`selection-chip ${puedeGenerar ? "selection-chip--ready" : ""}`}>
            {estadoSeleccion}
          </span>
        </div>

        <div className="controls">
          <div className="controls-left">
            <OptionsPanel options={activeReport.options} values={optState[activeReport.id]}
              onChange={(v) => setOptState((s) => ({ ...s, [activeReport.id]: v }))} />
          </div>
          <div className="controls-right">
            <button className="btn btn--primary" onClick={generar}
              disabled={running || !puedeGenerar}
              title={!puedeGenerar ? "Seleccione al menos un componente para generar el reporte." : undefined}>
              {running ? "Generando…" : "Generar reporte"}</button>
            <button className="btn" onClick={exportar}
              disabled={exporting || (!activeReport.sinArbol && (treeLoading || seleccionados === 0))}>
              {exporting ? "Exportando…" : "Exportar a Excel"}</button>
            {result && result.rows.length > 0 && (
              <div className="result-actions">
                <label className="totals-toggle">
                  <input type="checkbox" checked={showTotals} onChange={(e) => setShowTotals(e.target.checked)} /> Totales
                </label>
                <button className="btn btn--compact" onClick={copiar} title="Copiar la tabla al portapapeles para pegarla en Excel">
                  {copied ? "Copiado" : "Copiar"}
                </button>
              </div>
            )}
          </div>
        </div>
        {error && <div className="error-box">{error}</div>}
        {result && result.aviso && <div className="warn-box">⚠ {result.aviso}</div>}
        {result && result.rows.length > 0 && (
          <div className="result-meta">
            {result.rows.length} fila(s) · {result.columns.filter((c) => !c.hidden).length} columna(s)
            {generadoEn && <> · generado {generadoEn.toLocaleTimeString("es-BO")}</>}
          </div>
        )}
        <ResultsTable result={result} loading={running} showTotals={showTotals}
          placeholder="Marque componentes en el árbol y pulse «Generar reporte»."
          emptyHint="Sin datos para el rango/selección. Verifique el rango de fechas y los componentes marcados." />
      </main>
    </div>
  );
}
