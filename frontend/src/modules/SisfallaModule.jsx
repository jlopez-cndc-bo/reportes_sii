import { useMemo, useState } from "react";
import { api } from "../api";
import { SISFALLA_REPORTS } from "../sisfallaReports";
import OptionsPanel from "../components/OptionsPanel";
import ResultsTable from "../components/ResultsTable";
import DatePresets from "../components/DatePresets";
import FallaSearchModal from "../components/FallaSearchModal";
import { copyResultTsv } from "../copyTsv";
import { usePersisted } from "../usePersisted";
import { Rail, QueryPanel, QSec, ResultBar, fechaCorta } from "../shell";

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

  const pick = (id) => { setActiveId(id); setResult(null); setError(null); };
  const resumen = activeReport.sinFiltros ? "sin filtros"
    : [filtros.codFalla && `falla ${filtros.codFalla}`,
       filtros.agente && `agente ${filtros.agente}`,
       !gestionActiva && filtros.desde && `desde ${fechaCorta(filtros.desde)}`,
       !gestionActiva && filtros.hasta && `hasta ${fechaCorta(filtros.hasta)}`,
       opt.gestion && `gestión ${opt.gestion}`].filter(Boolean).join(", ") || "sin filtros";

  return (
    <div className="layout">
      <Rail grupos={GRUPOS} reports={SISFALLA_REPORTS} activeId={activeReport.id} onPick={pick} />

      <QueryPanel
        title={`${activeReport.grupo} › ${activeReport.label}`}
        desc={<>
          <p>{activeReport.descripcion}</p>
          {activeReport.reglaCndc && (
            <p>
              Sólo incluye fallas cuyo informe final o rectificatorio del CNDC ya fue
              emitido: un rango sin ninguna falla en ese estado da 0 filas aunque el
              filtro funcione.
            </p>
          )}
        </>}
        resumen={resumen}
        estado={estadoFiltro} listo
        onGenerar={generar} running={running} puedeGenerar={puedeGenerar}
        footer={<>
          <button className="btn btn--primary" onClick={generar} disabled={running}>
            {running ? "Generando…" : "Generar reporte"}</button>
          <button className="btn" onClick={exportar} disabled={exporting}>
            {exporting ? "Exportando…" : "Exportar a Excel"}</button>
        </>}>
        <QSec title="Filtros">
          {activeReport.sinFiltros ? (
            <div className="tree-note">Este reporte no acepta filtros: siempre trae todo.</div>
          ) : (
            <div className="filtros">
              {campos.codFalla && (
                <label className="dfield"><span>Falla</span>
                  <div className="field-with-action">
                    <input type="text" placeholder="247/2026" value={filtros.codFalla} onKeyDown={onKey}
                      title="Formato: nro/gestión, ej. 247/2026 o 0247-26"
                      onChange={(e) => setFiltro("codFalla", e.target.value)} />
                    <button type="button" className="pill-btn" onClick={() => setBuscandoFalla(true)}
                      title="Buscar falla por código o descripción">Buscar falla</button>
                  </div>
                  <small className="field-hint">Número y gestión, por ejemplo 247/2026.</small>
                </label>
              )}
              {campos.agente && (
                <label className="dfield"><span>Agente</span>
                  <input type="text" placeholder="Sigla o nombre" value={filtros.agente} onKeyDown={onKey}
                    onChange={(e) => setFiltro("agente", e.target.value)} /></label>
              )}
              {(campos.desde || campos.hasta) && (
                <div className="dates" title={gestionActiva ? "No aplica: la gestión (año) ya reemplaza el rango de fechas." : undefined}>
                  {campos.desde && (
                    <label className="dfield"><span>Desde</span>
                      <input type="date" value={filtros.desde} max={filtros.hasta || undefined} disabled={gestionActiva}
                        onKeyDown={onKey} onChange={(e) => setFiltro("desde", e.target.value)} /></label>
                  )}
                  {campos.hasta && (
                    <label className="dfield"><span>Hasta</span>
                      <input type="date" value={filtros.hasta} min={filtros.desde || undefined} disabled={gestionActiva}
                        onKeyDown={onKey} onChange={(e) => setFiltro("hasta", e.target.value)} /></label>
                  )}
                </div>
              )}
              {campos.desde && campos.hasta && !gestionActiva && (
                <DatePresets onPick={(ini, fin) => { setFiltro("desde", ini); setFiltro("hasta", fin); }} />
              )}
            </div>
          )}
        </QSec>

        {!activeReport.sinFiltros && activeReport.options && activeReport.options.length > 0 && (
          <QSec title="Opciones">
            <OptionsPanel
              options={activeReport.options}
              values={{ ...opt, _codFalla: filtros.codFalla }}
              onChange={(v) => {
                const { _codFalla, ...rest } = v;
                setOptState((s) => ({ ...s, [activeReport.id]: rest }));
              }}
            />
          </QSec>
        )}

        <div className="tree-note">
          Todos los filtros son opcionales. Sin ninguno, el reporte trae
          todos los registros disponibles (puede ser un volumen grande).
        </div>
      </QueryPanel>

      <main className="content">
        {error && <div className="error-box" role="alert">{error}</div>}
        {result && result.aviso && <div className="warn-box">⚠ {result.aviso}</div>}
        <ResultBar result={result} generadoEn={generadoEn}
          showTotals={showTotals} setShowTotals={setShowTotals} copied={copied} onCopiar={copiar} />
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
