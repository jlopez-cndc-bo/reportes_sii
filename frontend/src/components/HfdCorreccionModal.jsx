import { useId, useMemo, useState } from "react";
import { api } from "../api";
import { useDialog } from "../useDialog";
import { Close } from "../icons";
import { formatNumber, parseNumeroBO } from "../numFormat";
import { fechaCorta } from "../shell";
import ConfirmDialog from "./ConfirmDialog";

const HORAS = Array.from({ length: 96 }, (_, i) => `${String(Math.floor(i / 4)).padStart(2, "0")}:${String((i % 4) * 15).padStart(2, "0")}`);
const MOTIVO_MIN = 10;
const fmt = (v) => (v === null || v === undefined ? "-" : formatNumber(v, "num"));

// Corrección de una señal HFD (una fila de Registros) en un día cerrado.
// «Valor corregido» vacío = sin cambio. onSesionVencida(reintentar) reabre el login.
export default function HfdCorreccionModal({ fila, onClose, onGuardado, onSesionVencida }) {
  const [corr, setCorr] = useState(() => Array(96).fill(""));
  const [fuente, setFuente] = useState(() => Array(96).fill("MANUAL"));
  const [propuesta, setPropuesta] = useState(null);   // {medidor, factor, valores} | null
  const [cargandoSmec, setCargandoSmec] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState(null);
  const [confirmar, setConfirmar] = useState(null);   // "guardar" | "descartar" | null
  const [guardando, setGuardando] = useState(false);
  const titleId = useId();

  const parsed = useMemo(() => corr.map(parseNumeroBO), [corr]);
  const cambios = parsed.map((v, i) => ({ i, v })).filter(({ v }) => v !== null && !Number.isNaN(v));
  const invalidos = parsed.filter((v) => Number.isNaN(v)).length;
  const senal = `${fila.estacion}/${fila.elemento} ${fila.magnitud}`;

  const cerrar = () => (cambios.length || invalidos ? setConfirmar("descartar") : onClose());
  const ref = useDialog(() => { if (!confirmar) cerrar(); });

  const setValor = (i, texto, fte = "MANUAL") => {
    setCorr((c) => c.map((x, k) => (k === i ? texto : x)));
    setFuente((f) => f.map((x, k) => (k === i ? fte : x)));
  };

  // Pegar una columna de Excel en cualquier celda: llena desde esa hora hacia abajo.
  const onPaste = (i, e) => {
    const partes = e.clipboardData.getData("text").split(/\r?\n|\t/).filter((s, k, a) => s !== "" || k < a.length - 1);
    if (partes.length < 2) return;   // un solo valor: pegado normal
    e.preventDefault();
    if (i + partes.length > 96) {
      setError(`Se pegaron ${partes.length} valores desde las ${HORAS[i]}; sólo caben ${96 - i}. No se aplicó nada.`);
      return;
    }
    setError(null);
    setCorr((c) => c.map((x, k) => (k >= i && k < i + partes.length ? partes[k - i].trim() : x)));
    setFuente((f) => f.map((x, k) => (k >= i && k < i + partes.length ? "MANUAL" : x)));
  };

  const cargarSmec = async () => {
    setCargandoSmec(true); setError(null);
    try {
      const r = await api.hfdPropuestaSmec(fila.id, fila.fecha);
      if (!r.medidor) setError("Esta señal no tiene medidor SMEC asociado: cargue los valores a mano.");
      setPropuesta(r.medidor ? r : null);
    } catch (e) {
      if (e.status === 401) onSesionVencida(cargarSmec); else setError(e.message);
    } finally { setCargandoSmec(false); }
  };

  const usarPropuesta = (i) => {
    const v = propuesta?.valores?.[i];
    if (v !== null && v !== undefined) setValor(i, formatNumber(v, "num"), "SMEC");
  };
  const usarPropuestaEnTodos = () => propuesta.valores.forEach((v, i) => { if (v !== null) usarPropuesta(i); });

  const pedirGuardar = () => {
    if (invalidos) return setError(`Hay ${invalidos} valor(es) que no son números; corríjalos o déjelos vacíos.`);
    if (!cambios.length) return setError("No hay valores corregidos: escriba, pegue o use la propuesta SMEC.");
    if (motivo.trim().length < MOTIVO_MIN) return setError(`Escriba el motivo (al menos ${MOTIVO_MIN} caracteres).`);
    setError(null); setConfirmar("guardar");
  };

  const guardar = async () => {
    setConfirmar(null); setGuardando(true); setError(null);
    try {
      await api.hfdGuardarCorrecciones({
        archivo: "generadores", id_obj: fila.id, el: fila.magnitud, fecha: fila.fecha, motivo: motivo.trim(),
        cambios: cambios.map(({ i, v }) => ({ intervalo: i, valor: v, fuente: fuente[i] })),
      });
      onGuardado(cambios.length, fila.fecha);
    } catch (e) {
      // Sesión vencida: no se pierde nada; tras el login se reintenta el guardado.
      if (e.status === 401) onSesionVencida(guardar); else setError(e.message);
    } finally { setGuardando(false); }
  };

  return (
    <div className="modal-overlay">
      <div ref={ref} className="modal modal--wide" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="modal-head">
          <h2 id={titleId}>Corregir {senal} · {fechaCorta(fila.fecha)}</h2>
          <button type="button" className="icon-btn" onClick={cerrar} aria-label="Cerrar"><Close /></button>
        </div>
        <div className="modal-body">
          {error && <div className="error-box" role="alert">{error}</div>}
          <div className="corr-herramientas">
            <button type="button" className="pill-btn" onClick={cargarSmec} disabled={cargandoSmec}>
              {cargandoSmec ? "Cargando SMEC…" : "Cargar valores SMEC"}</button>
            {propuesta && <button type="button" className="pill-btn" onClick={usarPropuestaEnTodos}>Usar propuesta en todos</button>}
            {propuesta && <span className="field-hint">Propuesta: medidor SMEC {propuesta.codigo ?? propuesta.medidor} × {formatNumber(propuesta.factor, "num")} (promedio de 15 min, MW). Revise que sea razonable antes de usarla.</span>}
          </div>
          <div className="corr-scroll">
            <table className="corr-tabla">
              <thead><tr><th scope="col">Hora</th><th scope="col">HFD actual (MW)</th>
                <th scope="col">Propuesta SMEC (MW)</th><th scope="col">Valor corregido (MW)</th></tr></thead>
              <tbody>
                {HORAS.map((h, i) => {
                  const nota = fila._corr?.[`p${i}`];
                  const pv = propuesta?.valores?.[i];
                  return (
                    <tr key={i} className={cambios.some((c) => c.i === i) ? "cambia" : ""}>
                      <td>{h}</td>
                      <td title={nota}>{fmt(fila[`p${i}`])}{nota && <span className="cell-edited-mark" aria-hidden="true">*</span>}</td>
                      <td>{propuesta ? (pv === null || pv === undefined ? "-" : (
                        <button type="button" className="mini-btn" onClick={() => usarPropuesta(i)}
                          aria-label={`Usar ${fmt(pv)} a las ${h}`}>{fmt(pv)}</button>)) : ""}</td>
                      <td><input inputMode="decimal" value={corr[i]} aria-label={`Valor corregido a las ${h}`}
                        aria-invalid={Number.isNaN(parsed[i]) || undefined}
                        onChange={(e) => setValor(i, e.target.value)} onPaste={(e) => onPaste(i, e)} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <label className="dfield"><span>Motivo (obligatorio)</span>
            <input className="motivo-input" value={motivo} maxLength={400} onChange={(e) => setMotivo(e.target.value)} />
            <small className="field-hint">P. ej. «Señal congelada en SCADA desde el 16/11; valor del medidor SMEC 1011».</small>
          </label>
          <p className="field-hint">Celda vacía = sin cambio. Puede pegar una columna de Excel en cualquier celda: se llena desde esa hora hacia abajo.</p>
        </div>
        <div className="modal-foot">
          <span>{cambios.length} de 96 valores cambian</span>
          <div className="acciones">
            <button type="button" className="btn" onClick={cerrar}>Cancelar</button>
            <button type="button" className="btn btn--primary" onClick={pedirGuardar} disabled={guardando}>
              {guardando ? "Guardando…" : "Guardar y recargar"}</button>
          </div>
        </div>
      </div>

      {confirmar === "guardar" && (
        <ConfirmDialog titulo="¿Guardar y recargar?" confirmar="Guardar y recargar"
          onConfirm={guardar} onCancel={() => setConfirmar(null)}>
          <p>Se corregirán {cambios.length} valores de {senal} del {fechaCorta(fila.fecha)} y se recargará el día
            en el ETL (alrededor de 1 minuto). Queda registrado con su usuario y el motivo.</p>
        </ConfirmDialog>
      )}
      {confirmar === "descartar" && (
        <ConfirmDialog titulo={`¿Descartar ${cambios.length + invalidos} cambio(s)?`} confirmar="Descartar"
          cancelar="Seguir editando" onConfirm={onClose} onCancel={() => setConfirmar(null)}>
          <p>Los valores escritos en esta corrección se perderán.</p>
        </ConfirmDialog>
      )}
    </div>
  );
}
