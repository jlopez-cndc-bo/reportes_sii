import { rangosRapidos } from "../dateUtils";
import { fechaCorta } from "../shell";

// Rangos rápidos en una fila segmentada; se marca el que coincide con las
// fechas actuales. En reportes de fecha única (single) sólo Hoy/Ayer.
export default function DatePresets({ single, ini, fin, onPick }) {
  const rangos = rangosRapidos().filter((r) => !single || r.ini === r.fin);
  const activo = rangos.find((r) => r.ini === ini && (single || r.fin === fin));
  return (
    <div className="opt-radios date-presets" role="group" aria-label="Rangos rápidos">
      {rangos.map((r) => (
        <button key={r.label} type="button"
          className={`seg ${r === activo ? "seg--on" : ""}`}
          aria-current={r === activo ? "true" : undefined}
          title={r.ini === r.fin ? fechaCorta(r.ini) : `${fechaCorta(r.ini)} al ${fechaCorta(r.fin)}`}
          onClick={() => onPick(r.ini, r.fin)}>
          {r.label}
        </button>
      ))}
    </div>
  );
}
