import { useEffect, useState } from "react";
import { api } from "./api";
import IndispModule from "./modules/IndispModule";
import SmecModule from "./modules/SmecModule";
import cndcLogo from "./assets/cndc-logo-naranja.png";

const MODULOS = [
  { id: "indisp", label: "Indisponibilidades", short: "INDISP" },
  { id: "smec", label: "SMEC", short: "SMEC" },
];

function HelpModal({ onClose }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Ayuda">
        <div className="modal-head">
          <h2>Guía rápida</h2>
          <button className="modal-close" onClick={onClose} aria-label="Cerrar">✕</button>
        </div>
        <div className="modal-body">
          <h3>Jerarquía de elementos</h3>
          <p><b>Agente → Central → Unidad/Medidor.</b> Marque en el árbol el nivel que desea;
             al marcar un padre se marcan sus hijos.</p>

          <h3>SMEC · Inyección vs. Retiro</h3>
          <p><b>Inyección</b>: energía/potencia que la central entrega al sistema.
             <b> Retiro</b>: la que consume. Elija la dirección en el panel izquierdo;
             el árbol muestra sólo las centrales de esa dirección. Potencia en <b>kW</b>,
             energía en <b>kWh</b>.</p>

          <h3>Indisponibilidades · Tipos de operación</h3>
          <ul className="codes">
            <li><b>152</b> Operación Normal</li>
            <li><b>153</b> Potencia Limitada</li>
            <li><b>155</b> Programada</li>
            <li><b>156</b> Forzada</li>
            <li><b>158</b> Prueba</li>
            <li><b>192</b> Reprogramación</li>
          </ul>

          <h3>SMEC · Nivel «Árbol»</h3>
          <p>En Potencia 15 min/Hora, el nivel <b>Árbol</b> muestra una grilla
             jerárquica expandible Agente → Central → Medidor (pulse ▸).</p>

          <h3>Indisponibilidades · Programación</h3>
          <p>Los reportes de <b>Programación</b> (mantenimiento y Programado vs
             Real) no usan el árbol: consideran todas las unidades con
             programación registrada. La semana se ancla en <b>sábado</b>, como
             en la aplicación original.</p>

          <h3>Tips</h3>
          <ul>
            <li>Click en un encabezado de columna para <b>ordenar</b>.</li>
            <li>Marque «Totales» para sumar las columnas numéricas.</li>
            <li>«Copiar» deja la tabla lista para pegar en Excel.</li>
            <li>Estando en un campo de fecha, <b>Enter</b> genera el reporte.</li>
            <li>Los valores negativos se muestran en rojo.</li>
            <li>En el árbol, «Vigentes» oculta los componentes dados de baja
                en el rango.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [health, setHealth] = useState(null);
  const [modulo, setModulo] = useState(() => {
    try { return localStorage.getItem("modulo") || "indisp"; } catch { return "indisp"; }
  });
  const [help, setHelp] = useState(false);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ oracle: "desconocido" }));
  }, []);

  useEffect(() => {
    try { localStorage.setItem("modulo", modulo); } catch {}
  }, [modulo]);

  const oracleOk = health && health.oracle === "conectado";

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand-lockup">
          <img className="brand-logo" src={cndcLogo} alt="CNDC — Comité Nacional de Despacho de Carga" />
          <div>
            <h1>Reportes SII</h1>
            <span className="subtitle">Consulta operativa</span>
          </div>
        </div>
        <nav className="modtabs">
          {MODULOS.map((m) => (
            <button key={m.id} aria-pressed={m.id === modulo}
              className={`modtab ${m.id === modulo ? "modtab--active" : ""}`}
              title={m.label}
              onClick={() => setModulo(m.id)}>
              <span className="modtab-short">{m.short}</span>
              <span className="modtab-label">{m.label}</span>
            </button>
          ))}
        </nav>
        <div className="topbar-actions">
          <span className={`badge ${oracleOk ? "badge--ok" : "badge--warn"}`}>
            <span className="badge-dot" aria-hidden="true" />
            Oracle: {health ? health.oracle : "…"}
          </span>
          <button className="help-btn" onClick={() => setHelp(true)} title="Ayuda" aria-label="Ayuda">?</button>
        </div>
      </header>

      {/* Ambos módulos permanecen montados para preservar su estado al alternar. */}
      <div className={`modwrap ${modulo === "indisp" ? "" : "modwrap--hidden"}`}><IndispModule /></div>
      <div className={`modwrap ${modulo === "smec" ? "" : "modwrap--hidden"}`}><SmecModule /></div>

      {help && <HelpModal onClose={() => setHelp(false)} />}
    </div>
  );
}
