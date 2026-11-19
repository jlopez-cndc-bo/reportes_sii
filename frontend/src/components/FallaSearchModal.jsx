import { useEffect, useId, useRef, useState } from "react";
import { api } from "../api";
import { useDialog } from "../useDialog";
import { Close } from "../icons";

// Picker modal para elegir una falla sin saber de memoria el código interno:
// busca por código visible (nro/gestión) o texto de la descripción corta.
// Al abrir, sin texto, ya trae las más recientes (no deja el área en blanco).
export default function FallaSearchModal({ onClose, onSelect }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);
  const dlgRef = useDialog(onClose, inputRef);
  const titleId = useId();

  useEffect(() => {
    let cancelado = false;
    setLoading(true);
    setError(null);
    const t = setTimeout(async () => {
      try {
        const data = await api.sisfallaBuscarFallas(q, 30);
        if (!cancelado) setRows(data);
      } catch (e) {
        if (!cancelado) setError(e.message);
      } finally {
        if (!cancelado) setLoading(false);
      }
    }, q ? 300 : 0);
    return () => { cancelado = true; clearTimeout(t); };
  }, [q]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div ref={dlgRef} className="modal" onClick={(e) => e.stopPropagation()} role="dialog"
        aria-modal="true" aria-labelledby={titleId}>
        <div className="modal-head">
          <h2 id={titleId}>Buscar falla</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Cerrar"><Close /></button>
        </div>
        <div className="modal-body">
          <input
            ref={inputRef}
            type="search"
            aria-label="Buscar falla por código o descripción"
            className="falla-search-input"
            placeholder="Código (nro/gestión) o texto de la descripción…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          {error && <div className="error-box">{error}</div>}
          {!error && loading && (
            <div className="falla-search-state"><span className="spinner" /> Buscando…</div>
          )}
          {!error && !loading && rows.length === 0 && (
            <div className="falla-search-state">Sin resultados para esa búsqueda.</div>
          )}
          {!error && !loading && rows.length > 0 && (
            <ul className="falla-search-list">
              {rows.map((r) => (
                <li key={r.codFalla}>
                  <button type="button" className="falla-search-row" onClick={() => onSelect(r.codFallaTexto)}>
                    <span className="falla-search-cod">{r.codFallaTexto}</span>
                    <span className="falla-search-fecha">
                      {r.fecInicio ? new Date(r.fecInicio).toLocaleDateString("es-BO") : ""}
                    </span>
                    <span className="falla-search-desc">{r.descripcion}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
