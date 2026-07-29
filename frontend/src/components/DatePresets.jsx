import { rangosRapidos } from "../dateUtils";

// Chips de rango rápido bajo los campos de fecha. En reportes de fecha
// única (single) sólo aplican Hoy/Ayer y se fija únicamente el inicio.
export default function DatePresets({ single, onPick }) {
  const rangos = rangosRapidos().filter((r) => !single || r.ini === r.fin);
  return (
    <div className="date-presets">
      {rangos.map((r) => (
        <button key={r.label} type="button" onClick={() => onPick(r.ini, r.fin)}>
          {r.label}
        </button>
      ))}
    </div>
  );
}
