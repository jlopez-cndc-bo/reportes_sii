import { useMemo, useState } from "react";
import { api } from "../api";
import { SCADA_REPORTS, MAX_DIAS_HFD, UNIDADES } from "../scadaReports";
import OptionsPanel from "../components/OptionsPanel";
import ResultsTable from "../components/ResultsTable";
import DatePresets from "../components/DatePresets";
import { isoDaysAgo as iso } from "../dateUtils";
import { copyResultTsv } from "../copyTsv";
import { usePersisted } from "../usePersisted";
import { Rail, QueryPanel, QSec, ResultBar, fechaCorta } from "../shell";

const GRUPOS = [...new Set(SCADA_REPORTS.map((r) => r.grupo))];
const DIA_MS = 86400000;

export default function ScadaModule() {
  const [activeId, setActiveId] = usePersisted("scada.reporte", SCADA_REPORTS[0].id);
  // Fallback por si un id persistido ya no existe en esta versión.
  const report = useMemo(() => SCADA_REPORTS.find((r) => r.id === activeId) || SCADA_REPORTS[0], [activeId]);
  const [magnitudes, setMagnitudes] = useState(() =>
    Object.fromEntries(SCADA_REPORTS.map((r) => [r.id, r.magnitudes?.[0]])));
  const consolidado = !!report.consolidado;
  const unRango = !consolidado || report.fin;
  const magnitud = magnitudes[report.id];
  const unidad = consolidado ? null : UNIDADES[magnitud];
  const extra = consolidado ? report.extra : unidad && `Valores en ${unidad}`;

  const hoy = iso(0);
  const [fechaInicio, setFechaInicio] = useState(iso(1));
  const [fechaFin, setFechaFin] = useState(iso(1));
  const [estacion, setEstacion] = useState("");

  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);
  const [showTotals, setShowTotals] = useState(false);
  const [generadoEn, setGeneradoEn] = useState(null);
  const [copied, setCopied] = useState(false);

  const dias = fechaInicio && fechaFin
    ? Math.round((new Date(fechaFin) - new Date(fechaInicio)) / DIA_MS) + 1 : 0;
  const motivoNoListo = !unRango ? (!fechaInicio ? "Elija la fecha." : null)
    : !fechaInicio || !fechaFin ? "Elija las fechas de inicio y final."
    : dias < 1 ? "La fecha final es anterior a la de inicio."
    : dias > MAX_DIAS_HFD ? `El rango no puede superar ${MAX_DIAS_HFD} días (eligió ${dias}).`
    : null;
  const puedeGenerar = !running && !motivoNoListo;

  const body = () => consolidado
    ? (report.fin ? { desde: fechaInicio, hasta: fechaFin } : { fecha: fechaInicio })
    : { archivo: report.id, magnitud, desde: fechaInicio, hasta: fechaFin, estacion: estacion.trim() || null };

  const generar = async () => {
    if (!puedeGenerar) return;
    setRunning(true); setError(null); setResult(null);
    try {
      setResult(consolidado ? await api.hfdConsolidado(report.id, body()) : await api.hfdRegistros(body()));
      setGeneradoEn(new Date());
    } catch (e) { setError(e.message); }
    finally { setRunning(false); }
  };
  const onKey = (e) => { if (e.key === "Enter") generar(); };

  const exportar = async () => {
    setExporting(true); setError(null);
    try { await (consolidado ? api.hfdConsolidadoExportar(report.id, body()) : api.hfdExportar(body())); }
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
  const rango = !unRango || fechaInicio === fechaFin ? fechaCorta(fechaInicio)
    : `${fechaCorta(fechaInicio)} a ${fechaCorta(fechaFin)}`;
  const resumen = consolidado ? rango : [rango, magnitud, estacion.trim() && `estación «${estacion.trim()}»`].filter(Boolean).join(", ");

  return (
    <div className="layout">
      <Rail grupos={GRUPOS} reports={SCADA_REPORTS} activeId={report.id} onPick={pick} />

      <QueryPanel
        title={`${report.grupo} › ${report.label}`}
        desc={<>
          <p>{report.descripcion}</p>
          {consolidado ? <p>{report.extra}.</p> : (
            <p>Una fila por medida y día, con los valores crudos de SCADA cada 15 minutos,
               de 00:00 a 23:45, igual que el archivo del HFD.{unidad && ` Valores en ${unidad}.`}</p>
          )}
        </>}
        resumen={resumen}
        estado={motivoNoListo || "Listo para generar"} listo={!motivoNoListo}
        onGenerar={generar} running={running} puedeGenerar={puedeGenerar}
        footer={<>
          <button className="btn btn--primary" onClick={generar} disabled={!puedeGenerar}
            title={motivoNoListo || undefined}>
            {running ? "Generando…" : "Generar reporte"}</button>
          <button className="btn" onClick={exportar} disabled={exporting || !!motivoNoListo}
            title={motivoNoListo || undefined}>
            {exporting ? "Exportando…" : "Exportar a Excel"}</button>
        </>}>
        <QSec title={unRango ? "Fechas" : "Fecha"}>
          <div className="dates">
            <label className="dfield"><span>{unRango ? "Inicio" : "Fecha"}</span>
              <input type="date" value={fechaInicio} max={unRango ? fechaFin || hoy : hoy} onKeyDown={onKey}
                onChange={(e) => setFechaInicio(e.target.value)} /></label>
            {unRango && (
              <label className="dfield"><span>Final</span>
                <input type="date" value={fechaFin} min={fechaInicio} max={hoy} onKeyDown={onKey}
                  onChange={(e) => setFechaFin(e.target.value)} /></label>
            )}
          </div>
          <DatePresets single={!unRango}
            onPick={(ini, fin) => { setFechaInicio(ini); if (unRango) setFechaFin(fin); }} />
        </QSec>

        {/* Magnitud y Estación sólo aplican a los registros crudos. */}
        {!consolidado && <QSec title="Opciones">
          <OptionsPanel
            options={[{ type: "radio", key: "magnitud", label: "Magnitud",
              options: report.magnitudes.map((m) => ({ value: m, label: m })) }]}
            values={{ magnitud }}
            onChange={(v) => setMagnitudes((s) => ({ ...s, [report.id]: v.magnitud }))}
          />
          <label className="dfield"><span>Estación</span>
            <input type="text" placeholder="Opcional, p. ej. WARNES" value={estacion} onKeyDown={onKey}
              onChange={(e) => setEstacion(e.target.value)} />
            <small className="field-hint">Coincidencia parcial; reduce lo que se consulta.</small>
          </label>
        </QSec>}
      </QueryPanel>

      <main className="content">
        {error && <div className="error-box" role="alert">{error}</div>}
        {result && result.aviso && <div className="warn-box">⚠ {result.aviso}</div>}
        {result && showTotals && result.aviso_total && <div className="warn-box">⚠ {result.aviso_total}</div>}
        <ResultBar result={result} generadoEn={generadoEn} extra={extra}
          showTotals={showTotals} setShowTotals={setShowTotals} copied={copied} onCopiar={copiar} />
        <ResultsTable result={result} loading={running} showTotals={showTotals}
          placeholder={consolidado ? "Elija la fecha y pulse «Generar reporte»."
            : "Elija fechas y magnitud y pulse «Generar reporte»."}
          emptyHint={consolidado ? "Sin datos para esta fecha." : "Sin registros para este archivo, magnitud y rango."} />
      </main>
    </div>
  );
}
