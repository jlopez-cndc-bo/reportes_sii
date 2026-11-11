// Armazón de tres columnas compartido por los módulos:
//   Rail (módulos + reportes) · QueryPanel (consulta) · resultados.
// Rail y QueryPanel se comprimen a una franja; el estado vive en App y se
// comparte por contexto para que sea el mismo en los tres módulos.
import { createContext, useContext } from "react";
import cndcLogo from "./assets/cndc-logo-azul.png";

export const ShellContext = createContext(null);
const useShell = () => useContext(ShellContext);

export const fechaCorta = (iso) => (iso ? iso.split("-").reverse().join("/") : "");

function Chevrons({ dir }) {
  const d = dir === "left"
    ? "M8 3.5L3.5 8 8 12.5M12.5 3.5L8 8l4.5 4.5"
    : "M8 3.5L12.5 8 8 12.5M3.5 3.5L8 8l-4.5 4.5";
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor"
      strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

function IconBtn({ label, onClick, children, ...rest }) {
  return (
    <button type="button" className="icon-btn" aria-label={label} title={label} onClick={onClick} {...rest}>
      {children}
    </button>
  );
}

export function Rail({ grupos, reports, activeId, onPick }) {
  const sh = useShell();
  const mod = sh.modulos.find((m) => m.id === sh.modulo);
  const active = reports.find((r) => r.id === activeId);
  const oracleOk = sh.health && sh.health.oracle === "conectado";

  if (!sh.railOpen) {
    return (
      <div className="strip strip--rail">
        <IconBtn label="Expandir navegación" onClick={sh.toggleRail}><Chevrons dir="right" /></IconBtn>
        <span className="strip-text">
          {mod.label}{active ? `, ${active.grupo.toLowerCase()}: ${active.label}` : ""}
        </span>
      </div>
    );
  }

  return (
    <nav className="rail" aria-label="Módulos y reportes">
      <div className="rail-brand">
        <img className="rail-logo" src={cndcLogo} alt="CNDC — Comité Nacional de Despacho de Carga" />
        <div className="rail-title">
          <span>Reportes SII</span>
          <IconBtn label="Comprimir navegación" onClick={sh.toggleRail}><Chevrons dir="left" /></IconBtn>
        </div>
      </div>
      <div className="rail-mods">
        {sh.modulos.map((m) => (
          <button key={m.id} type="button" className="mod" aria-pressed={m.id === sh.modulo}
            title={m.beta ? `${m.label} (en desarrollo)` : undefined}
            onClick={() => sh.setModulo(m.id)}>
            {m.label}
            {m.beta && <span className="mod-beta">beta</span>}
          </button>
        ))}
      </div>
      <div className="rail-reports">
        {grupos.map((g) => (
          <div key={g} role="group" aria-label={g}>
            <div className="rail-group">{g}</div>
            {reports.filter((r) => r.grupo === g).map((r) => (
              <button key={r.id} type="button" className="rep"
                aria-current={r.id === activeId ? "page" : undefined}
                onClick={() => onPick(r.id)}>{r.label}</button>
            ))}
          </div>
        ))}
      </div>
      <div className="rail-foot">
        <span className={`oracle ${oracleOk ? "oracle--ok" : "oracle--warn"}`}>
          <span className="oracle-dot" aria-hidden="true" />
          Oracle {sh.health ? sh.health.oracle : "…"}
        </span>
        <button type="button" className="pill-btn" onClick={sh.openHelp}>Guía rápida</button>
      </div>
    </nav>
  );
}

// Panel de consulta. Comprimido NO se desmonta (se oculta) para conservar
// la expansión y el scroll del árbol; la franja ofrece Generar sin expandir.
export function QueryPanel({
  title, desc, resumen, estado, listo,
  onGenerar, running, puedeGenerar, footer, children,
}) {
  const sh = useShell();
  const open = sh.queryOpen;
  return (
    <>
      {!open && (
        <div className="strip strip--query">
          <IconBtn label="Expandir consulta" onClick={sh.toggleQuery}><Chevrons dir="right" /></IconBtn>
          <button type="button" className="icon-btn icon-btn--primary" onClick={onGenerar}
            disabled={running || !puedeGenerar}
            aria-label="Generar reporte" title={running ? "Generando…" : "Generar reporte"}>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor" aria-hidden="true">
              <path d="M4 2.2v9.6a.6.6 0 00.92.5l7.3-4.8a.6.6 0 000-1L4.92 1.7A.6.6 0 004 2.2z" />
            </svg>
          </button>
          <span className="strip-text">{title}{resumen ? `, ${resumen}` : ""}</span>
        </div>
      )}
      <section className={`query ${open ? "" : "query--hidden"}`} aria-label="Consulta">
        <div className="query-body">
          <header className="query-head">
            <div>
              <h1>{title}</h1>
              {desc}
            </div>
            <IconBtn label="Comprimir consulta" onClick={sh.toggleQuery}><Chevrons dir="left" /></IconBtn>
          </header>
          {children}
        </div>
        <div className="query-foot">
          {estado && <div className={`query-estado ${listo ? "query-estado--ok" : ""}`}>{estado}</div>}
          <div className="query-actions">{footer}</div>
        </div>
      </section>
    </>
  );
}

// Encabezado de una sección del panel de consulta.
export function QSec({ title, aside, className = "", children }) {
  return (
    <section className={`qsec ${className}`}>
      <div className="qsec-head">
        <h2>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

// Resumen + acciones sobre el resultado ya generado.
export function ResultBar({ result, generadoEn, extra, showTotals, setShowTotals, copied, onCopiar, children }) {
  if (!result || result.rows.length === 0) return null;
  const nCols = result.columns.filter((c) => !c.hidden).length;
  return (
    <div className="result-bar">
      <div className="result-meta">
        <span>{result.rows.length.toLocaleString("es-BO")} fila(s), {nCols} columna(s)</span>
        {extra && <span>{extra}</span>}
        {generadoEn && <span>Generado a las {generadoEn.toLocaleTimeString("es-BO")}</span>}
      </div>
      <div className="result-actions">
        {children}
        <label className="totals-toggle">
          <input type="checkbox" checked={showTotals} onChange={(e) => setShowTotals(e.target.checked)} /> Totales
        </label>
        <button type="button" className="pill-btn" onClick={onCopiar}
          title="Copiar la tabla al portapapeles para pegarla en Excel">
          {copied ? "Copiado" : "Copiar"}
        </button>
      </div>
    </div>
  );
}
