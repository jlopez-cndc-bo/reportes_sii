import { useMemo, useState } from "react";
import { api } from "../api";
import { SISFALLA_REPORTS } from "../sisfallaReports";
import OptionsPanel from "../components/OptionsPanel";
import ResultsTable from "../components/ResultsTable";
import DatePresets from "../components/DatePresets";
import FallaSearchModal from "../components/FallaSearchModal";
import { copyResultTsv } from "../copyTsv";
import { usePersisted } from "../usePersisted";

export default function SisfallaModule() {
  const GRUPOS = useMemo(() => [...new Set(SISFALLA_REPORTS.map((r) => r.grupo))], []);
  const [activeId, setActiveId] = usePersisted("sisfalla.reporte", SISFALLA_REPORTS[0].id);
  // Fallback por si un id persistido ya no existe en esta versión.
  const activeReport = useMemo(
    () => SISFALLA_REPORTS.find((r) => r.id === activeId) || SISFALLA_REPORTS[0],
    [activeId]
  );
  const [optState, setOptState] = useState(() =>
    Object.fromEntries(SISFALLA_REPORTS.map((r) => [r.id, { ...r.defaults }]))
  );

  // Filtros compartidos entre reportes: no hay árbol de componentes en este
  // dominio, así que cod_falla/agente/desde/hasta son campos sueltos en vez
  // de una selección. Se conservan al cambiar de reporte (como fechaInicio/
  // fechaFin en los otros módulos).
  const [filtros, setFiltros] = useState({ codFalla: "", agente: "", desde: "", hasta: "" });
  const setFiltro = (k, v) => setFiltros((s) => ({ ...s, [k]: v }));

  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);
  const [showTotals, setShowTotals] = useState(false);
  const [generadoEn, setGeneradoEn] = useState(null);
  const [copied, setCopied] = useState(false);
  const [buscandoFalla, setBuscandoFalla] = useState(false);

  const campos = activeReport.campos || {};
  const opt = optState[activeReport.id] || {};
  // detalle-informes: gestión reemplaza el rango de fechas, pero no tiene
  // sentido junto a un código de falla puntual (ya es un único resultado).
  const gestionActiva = !!(activeReport.gestionExcluyeFecha && opt.gestion && !filtros.codFalla);

  const hayFiltros = !!(filtros.codFalla || filtros.agente || filtros.desde || filtros.hasta || opt.gestion);
  const puedeGenerar = !running;
  const estadoFiltro = activeReport.sinFiltros
    ? "Sin filtros: trae todo"
    : hayFiltros ? "Filtrado" : "Sin filtros: trae todo";

  const buildBody = () => activeReport.buildBody ? activeReport.buildBody(filtros, opt) : {};

  const generar = async () => {
    setRunning(true); setError(null); setResult(null);
    try {
      const data = activeReport.sinFiltros
        ? await api.sisfallaReporteGet(activeReport.id)
        : await api.sisfallaReporte(activeReport.id, buildBody());
      setResult(data);
      setGeneradoEn(new Date());
    } catch (e) { setError(e.message); }
    finally { setRunning(false); }
  };
  const onKey = (e) => { if (e.key === "Enter" && !running) generar(); };

  const exportar = async () => {
    setExporting(true); setError(null);
    try { await api.sisfallaExportar(activeReport.id, buildBody()); }
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

  return (
    <div className="layout">
      <aside className="sidebar">
        <section className="panel panel--filtros">
          <h2>Filtros</h2>
          {activeReport.sinFiltros ? (
            <div className="tree-note">Este reporte no acepta filtros: siempre trae todo.</div>
          ) : (
            <>
              {campos.codFalla && (
                <label className="field"><span>Falla</span>
                  <div className="field-with-action">
                    <input type="text" placeholder="nro/gestión, ej. 247/2026" value={filtros.codFalla} onKeyDown={onKey}
                      title="Formato: nro/gestión, ej. 247/2026 o 0247-26"
                      onChange={(e) => setFiltro("codFalla", e.target.value)} />
                    <button type="button" className="mini-btn" onClick={() => setBuscandoFalla(true)}
                      title="Buscar falla por código o descripción">🔎 Buscar</button>
                  </div>
                  <small className="field-hint">Formato: nro/gestión, ej. 247/2026 — o use «Buscar»</small>
                </label>
              )}
              {campos.agente && (
                <label className="field"><span>Agente</span>
                  <input type="text" placeholder="sigla o nombre" value={filtros.agente} onKeyDown={onKey}
                    onChange={(e) => setFiltro("agente", e.target.value)} /></label>
              )}
              {campos.desde && (
                <label className="field" title={gestionActiva ? "No aplica: la gestión (año) ya reemplaza el rango de fechas." : undefined}>
                  <span>Desde</span>
                  <input type="date" value={filtros.desde} max={filtros.hasta || undefined} disabled={gestionActiva}
                    onKeyDown={onKey} onChange={(e) => setFiltro("desde", e.target.value)} /></label>
              )}
              {campos.hasta && (
                <label className="field" title={gestionActiva ? "No aplica: la gestión (año) ya reemplaza el rango de fechas." : undefined}>
                  <span>Hasta</span>
                  <input type="date" value={filtros.hasta} min={filtros.desde || undefined} disabled={gestionActiva}
                    onKeyDown={onKey} onChange={(e) => setFiltro("hasta", e.target.value)} /></label>
              )}
              {campos.desde && campos.hasta && !gestionActiva && (
                <DatePresets onPick={(ini, fin) => { setFiltro("desde", ini); setFiltro("hasta", fin); }} />
              )}
              {activeReport.options && activeReport.options.length > 0 && (
                <div className="opt-group">
                  <OptionsPanel
                    options={activeReport.options}
                    values={{ ...opt, _codFalla: filtros.codFalla }}
                    onChange={(v) => {
                      const { _codFalla, ...rest } = v;
                      setOptState((s) => ({ ...s, [activeReport.id]: rest }));
                    }}
                  />
                </div>
              )}
            </>
          )}
          <div className="tree-note">
            Todos los filtros son opcionales. Sin ninguno, el reporte trae
            todos los registros disponibles (puede ser un volumen grande).
          </div>
        </section>
      </aside>

      <main className="content">
        <nav className="tabs tabs--grouped">
          {GRUPOS.map((g) => (
            <div className="tab-group" key={g}>
              <span className="tab-group-label">{g}</span>
              {SISFALLA_REPORTS.filter((r) => r.grupo === g).map((r) => (
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
            {activeReport.reglaCndc && (
              <p className="rpt-hint">
                Sólo incluye fallas cuyo informe FINAL o RECTIFICATORIO del CNDC ya fue
                emitido — un rango sin ninguna falla en ese estado da 0 filas aunque el
                filtro funcione.
              </p>
            )}
          </div>
          <span className={`selection-chip ${puedeGenerar ? "selection-chip--ready" : ""}`}>
            {estadoFiltro}
          </span>
        </div>

        <div className="controls">
          <div className="controls-left" />
          <div className="controls-right">
            <button className="btn btn--primary" onClick={generar} disabled={running}>
              {running ? "Generando…" : "Generar reporte"}</button>
            <button className="btn" onClick={exportar} disabled={exporting}>
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
          placeholder="Cargue los filtros que necesite (o ninguno) y pulse «Generar reporte»."
          emptyHint="Sin datos para este filtro/rango." />
      </main>
      {buscandoFalla && (
        <FallaSearchModal
          onClose={() => setBuscandoFalla(false)}
          onSelect={(codFallaTexto) => { setFiltro("codFalla", codFallaTexto); setBuscandoFalla(false); }}
        />
      )}
    </div>
  );
}
