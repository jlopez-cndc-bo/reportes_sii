import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { REPORTS } from "../reports";
import Tree from "../components/Tree";
import OptionsPanel from "../components/OptionsPanel";
import ResultsTable from "../components/ResultsTable";
import Chart from "../components/Chart";
import { seriesDeResultado } from "../chartData";
import DatePresets from "../components/DatePresets";
import { collectIds, allKeys, toggleNode, countLeaves } from "../treeUtils";
import { isoDaysAgo } from "../dateUtils";
import { copyResultTsv } from "../copyTsv";
import { usePersisted, usePersistedSet } from "../usePersisted";
import { Rail, QueryPanel, QSec, ResultBar, fechaCorta } from "../shell";
import { Refresh } from "../icons";

export default function IndispModule() {
  const [fechaInicio, setFechaInicio] = useState(isoDaysAgo(6)); // = atajo «7 d»
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
  const [vista, setVista] = useState("tabla");
  // Zonas térmicas para la consulta de temperaturas: se piden una vez, al necesitarlas.
  const [zonas, setZonas] = useState(null);
  const usaZonas = activeReport.options?.some((o) => o.source === "zonas");
  useEffect(() => {
    if (!usaZonas || zonas) return;
    api.zonasTermicas()
      .then((z) => {
        setZonas(z);
        // Por defecto todas marcadas (null = aún sin elegir).
        setOptState((s) => (s["temperatura-consulta"].zonas ? s
          : { ...s, "temperatura-consulta": { ...s["temperatura-consulta"], zonas: z.map((x) => x.id) } }));
      })
      .catch((e) => setError(`No se pudieron cargar las zonas térmicas: ${e.message}`));
  }, [usaZonas, zonas]);
  const opciones = useMemo(() => (activeReport.options || []).map((o) => (o.source === "zonas"
    ? { ...o, options: (zonas || []).map((z) => ({ value: z.id, label: z.zona, title: z.unidades.join(", ") })) }
    : o)), [activeReport, zonas]);
  const chartData = useMemo(() => (activeReport.grafico ? seriesDeResultado(result) : null),
    [result, activeReport]);

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

  // sinArbol: el reporte es de todo el SIN y no usa la selección del árbol.
  const sinArbol = !!activeReport.sinArbol;
  const puedeGenerar = sinArbol || (!treeLoading && seleccionados > 0);
  const estadoSeleccion = sinArbol ? "Todo el SIN: sin selección requerida" : `${seleccionados} componente(s) seleccionado(s)`;

  const pick = (id) => { setActiveId(id); setResult(null); setError(null); };
  const rango = `${fechaCorta(fechaInicio)} al ${fechaCorta(fechaFin)}`;

  return (
    <div className="layout">
      <Rail grupos={GRUPOS} reports={REPORTS} activeId={activeReport.id} onPick={pick} />

      <QueryPanel
        title={`${activeReport.grupo} › ${activeReport.label}`}
        desc={<p>{activeReport.descripcion}</p>}
        resumen={sinArbol ? rango : `${rango}, ${seleccionados} componente(s)`}
        estado={estadoSeleccion} listo={puedeGenerar}
        onGenerar={generar} running={running} puedeGenerar={puedeGenerar}
        footer={<>
          <button className="btn btn--primary" onClick={generar}
            disabled={running || !puedeGenerar}
            title={!puedeGenerar ? "Seleccione al menos un componente para generar el reporte." : undefined}>
            {running ? "Generando…" : "Generar reporte"}</button>
          <button className="btn" onClick={exportar}
            disabled={exporting || !puedeGenerar}>
            {exporting ? "Exportando…" : "Exportar a Excel"}</button>
        </>}>
        <QSec title="Fechas">
          <div className="dates">
            <label className="dfield"><span>Inicio</span>
              <input type="date" value={fechaInicio} max={fechaFin} onKeyDown={onKey} onChange={(e) => setFechaInicio(e.target.value)} /></label>
            <label className="dfield"><span>Final</span>
              <input type="date" value={fechaFin} min={fechaInicio} onKeyDown={onKey} onChange={(e) => setFechaFin(e.target.value)} /></label>
          </div>
          <DatePresets ini={fechaInicio} fin={fechaFin} onPick={(ini, fin) => { setFechaInicio(ini); setFechaFin(fin); }} />
        </QSec>

        {activeReport.options && activeReport.options.length > 0 && (
          <QSec title="Opciones">
            <OptionsPanel options={opciones} values={optState[activeReport.id]}
              onChange={(v) => setOptState((s) => ({ ...s, [activeReport.id]: v }))} />
          </QSec>
        )}

        {!sinArbol && <QSec title="Componentes" className="qsec--tree"
          aside={<span className="qsec-count">{seleccionados} seleccionado(s)</span>}>
          <div className="tree-tools">
            <input className="tree-search" type="search" aria-label="Buscar componente" placeholder="Buscar componente…" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
            <button type="button" className="pill-btn" onClick={() => setAll(true)}>Todos</button>
            <button type="button" className="pill-btn" onClick={() => setAll(false)}>Ninguno</button>
            <button type="button" className="pill-btn pill-btn--icon" onClick={cargarArbol} title="Recargar el árbol" aria-label="Recargar el árbol"><Refresh /></button>
          </div>
          <div className="tree-count">
            {totales.todos} componente(s) vigente(s) a hoy
            {treeLoading && tree.length > 0 && <span className="tree-refresh">, actualizando…</span>}
          </div>
          {treeError && <div className="tree-error">{treeError}</div>}
          {tree.length === 0
            ? <div className="tree-empty">{treeLoading ? "Cargando…" : "Sin componentes."}</div>
            : <div className={`tree-wrap ${treeLoading ? "tree-wrap--refreshing" : ""}`}>
                <Tree nodes={visibleTree} checked={checked} onToggle={onToggle} filter={filtro} collapsed />
              </div>}
        </QSec>}
      </QueryPanel>

      <main className="content">
        {error && <div className="error-box" role="alert">{error}</div>}
        {result && result.aviso && <div className="warn-box">⚠ {result.aviso}</div>}
        <ResultBar result={result} generadoEn={generadoEn}
          showTotals={showTotals} setShowTotals={setShowTotals} copied={copied} onCopiar={copiar}>
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
            unit={activeReport.unidad} omitidas={chartData.omitidas} />
        ) : <ResultsTable result={result} loading={running} showTotals={showTotals}
          placeholder={sinArbol ? "Elija las fechas y pulse «Generar reporte»." : "Marque componentes en el árbol y pulse «Generar reporte»."}
          emptyHint="Sin datos para el rango/selección. Verifique el rango de fechas y los componentes marcados." />}
      </main>
    </div>
  );
}
