import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { SCADA_REPORTS, MAX_DIAS_HFD, UNIDADES } from "../scadaReports";
import OptionsPanel from "../components/OptionsPanel";
import ResultsTable from "../components/ResultsTable";
import DatePresets from "../components/DatePresets";
import HfdLoginDialog from "../components/HfdLoginDialog";
import HfdCorreccionModal from "../components/HfdCorreccionModal";
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

  // ── Correcciones de operadores SCADA (sólo Registros › Generadores) ──
  const corregible = report.id === "generadores";
  const [editor, setEditor] = useState(null);          // usuario AD con sesión, o null
  const [login, setLogin] = useState(null);            // {despues} mientras el login está abierto
  const [seleccion, setSeleccion] = useState(false);   // modo «elija la fila a corregir»
  const [filaEditar, setFilaEditar] = useState(null);
  const [recarga, setRecarga] = useState(null);        // {estado, fecha, n, log, ultimo, inicio}
  const [ahora, setAhora] = useState(Date.now());

  useEffect(() => { api.hfdSesion().then((r) => setEditor(r.usuario)).catch(() => {}); }, []);
  useEffect(() => {
    if (recarga?.estado !== "corriendo") return undefined;
    const t = setInterval(() => setAhora(Date.now()), 1000);
    return () => clearInterval(t);
  }, [recarga?.estado]);

  const conSesion = (accion) => (editor ? accion() : setLogin({ despues: accion }));
  const onLoginOk = (u) => { const despues = login?.despues; setEditor(u); setLogin(null); despues?.(); };
  // Sesión vencida a mitad de una corrección: se reabre el login y se reintenta lo pendiente.
  const onSesionVencida = (reintentar) => { setEditor(null); setLogin({ despues: reintentar }); };
  const cerrarSesion = () => { api.hfdLogout().catch(() => {}); setEditor(null); setSeleccion(false); };

  const recargar = (fecha, n) => {
    let exito = false, fin = false;
    setRecarga({ estado: "corriendo", fecha, n, log: [], ultimo: "Iniciando la recarga…", inicio: Date.now() });
    const es = new EventSource(api.hfdRecargarUrl(fecha));
    es.onmessage = (ev) => {
      if (ev.data === "[FIN]") {
        fin = true; es.close();
        setRecarga((r) => ({ ...r, estado: exito ? "ok" : "error" }));
        if (exito) generar();
        return;
      }
      if (ev.data.startsWith("✓")) exito = true;
      setRecarga((r) => ({ ...r, log: [...r.log, ev.data], ultimo: ev.data }));
    };
    // EventSource reintenta solo: hay que cerrarlo, o volvería a pedir la recarga.
    es.onerror = () => { es.close(); if (!fin) setRecarga((r) => ({ ...r, estado: "cortado" })); };
  };
  const onGuardado = (n, fecha) => { setFilaEditar(null); setSeleccion(false); recargar(fecha, n); };

  const rowAction = seleccion && corregible ? (row) => (row.fecha < hoy ? (
    <button type="button" className="mini-btn row-action-btn" onClick={() => setFilaEditar(row)}
      aria-label={`Corregir ${row.estacion}/${row.elemento} ${row.magnitud} ${fechaCorta(row.fecha)}`}>Corregir</button>
  ) : null) : undefined;

  const textoRecarga = !recarga ? null
    : recarga.estado === "corriendo" ? `Recargando el ${fechaCorta(recarga.fecha)} en el ETL… ${Math.round((ahora - recarga.inicio) / 1000)} s — ${recarga.ultimo}`
    : recarga.estado === "ok" ? `${recarga.n} valor(es) corregido(s); la tabla muestra el día recargado.`
    : recarga.estado === "error" ? `Las correcciones se guardaron, pero la recarga falló: ${recarga.ultimo}`
    : "Se perdió la conexión con la recarga; puede seguir en el servidor.";

  const pick = (id) => { setActiveId(id); setResult(null); setError(null); setSeleccion(false); };
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
        {recarga && (
          <div className={recarga.estado === "error" ? "error-box" : "status-box"} role="status" aria-live="polite">
            {recarga.estado === "corriendo" && <span className="spinner" />}
            <div>
              <div>{textoRecarga}</div>
              {recarga.log.length > 0 && (
                <details><summary>Ver detalle</summary><pre>{recarga.log.join("\n")}</pre></details>
              )}
              {recarga.estado === "error" && (
                <button type="button" className="pill-btn" onClick={() => recargar(recarga.fecha, recarga.n)}>Reintentar recarga</button>
              )}
              {recarga.estado === "cortado" && <button type="button" className="pill-btn" onClick={generar}>Actualizar tabla</button>}
              {recarga.estado !== "corriendo" && <button type="button" className="pill-btn" onClick={() => setRecarga(null)}>Cerrar aviso</button>}
            </div>
          </div>
        )}
        {seleccion && (
          <div className="warn-box">
            Elija la fila a corregir con el botón «Corregir» (sólo días cerrados).{" "}
            <button type="button" className="pill-btn" onClick={() => setSeleccion(false)}>Salir</button>
          </div>
        )}
        <ResultBar result={result} generadoEn={generadoEn} extra={extra}
          showTotals={showTotals} setShowTotals={setShowTotals} copied={copied} onCopiar={copiar}>
          {corregible && editor && (
            <span className="sesion-hfd">Sesión: {editor}{" "}
              <button type="button" className="pill-btn" onClick={cerrarSesion}>Cerrar sesión</button></span>
          )}
          {corregible && (
            <button type="button" className="pill-btn" disabled={recarga?.estado === "corriendo"}
              title="Corregir señales congeladas (requiere usuario autorizado)"
              onClick={() => conSesion(() => setSeleccion(true))}>
              {recarga?.estado === "corriendo" ? "Recargando…" : "Revisar registros"}</button>
          )}
        </ResultBar>
        <ResultsTable result={result} loading={running} showTotals={showTotals} rowAction={rowAction}
          placeholder={consolidado ? "Elija la fecha y pulse «Generar reporte»."
            : "Elija fechas y magnitud y pulse «Generar reporte»."}
          emptyHint={consolidado ? "Sin datos para esta fecha." : "Sin registros para este archivo, magnitud y rango."} />
      </main>

      {filaEditar && (
        <HfdCorreccionModal fila={filaEditar} onClose={() => setFilaEditar(null)}
          onGuardado={onGuardado} onSesionVencida={onSesionVencida} />
      )}
      {login && <HfdLoginDialog onClose={() => setLogin(null)} onOk={onLoginOk} />}
    </div>
  );
}
