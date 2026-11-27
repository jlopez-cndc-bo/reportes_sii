import { useCallback, useEffect, useId, useMemo, useState } from "react";
import { api } from "./api";
import IndispModule from "./modules/IndispModule";
import SmecModule from "./modules/SmecModule";
import SisfallaModule from "./modules/SisfallaModule";
import ScadaModule from "./modules/ScadaModule";
import MonitoresModule from "./modules/MonitoresModule";
import ImpModule from "./modules/ImpModule";
import { ShellContext } from "./shell";
import { usePersisted } from "./usePersisted";
import { useDialog } from "./useDialog";
import { Close } from "./icons";

const MODULOS = [
  { id: "monitores", label: "Monitores", nombre: "Tablero ejecutivo del SIN", beta: true },
  { id: "indisp", label: "Reporte de la Operación" },
  { id: "smec", label: "Sistema de Medición Comercial", nombre: "SMEC" },
  { id: "sisfalla", label: "Sistema de Fallas", beta: true },
  { id: "scada", label: "SCADA HFD", nombre: "Historical File Data", beta: true },
  { id: "imp", label: "Informe de Mediano Plazo", nombre: "IMP", beta: true },
];

function HelpModal({ onClose }) {
  const ref = useDialog(onClose);
  const titleId = useId();
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div ref={ref} className="modal" onClick={(e) => e.stopPropagation()} role="dialog"
        aria-modal="true" aria-labelledby={titleId}>
        <div className="modal-head">
          <h2 id={titleId}>Guía rápida</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Cerrar"><Close /></button>
        </div>
        <div className="modal-body">
          <h3>Monitores</h3>
          <p><b>Operación del día</b> (hoy por defecto; elija otra fecha arriba): demanda del SIN
             (HFD), potencia de punta (SMEC; si aún no tiene el día, muestra el último cargado con su
             fecha), unidades indisponibles, potencia del parque estimada a la temperatura real,
             temperatura por zona térmica, curvas del día y alertas. Debajo, los
             <b> indicadores del período</b> elegido, independientes de esa fecha, con su
             comparación contra el periodo anterior y el mismo del año anterior y la tendencia de 12 meses. Cada cifra dice de qué dato sale (SMEC oficial, HFD operativo o registro
             de eventos) y a qué fecha. Sin una meta aprobada se lee «Meta por definir».
             El enlace <b>…/#/</b> abre siempre esta pantalla.</p>

          <h3>Jerarquía de elementos</h3>
          <p><b>Agente → Central → Unidad/Medidor.</b> Marque en el árbol el nivel que desea;
             al marcar un padre se marcan sus hijos.</p>

          <h3>Sistema de Medición Comercial · Inyección vs. Retiro</h3>
          <p><b>Inyección</b>: energía/potencia que la central entrega al sistema.
             <b> Retiro</b>: la que consume. Elija la dirección en el panel izquierdo;
             el árbol muestra sólo las centrales de esa dirección. Potencia en <b>kW</b>,
             energía en <b>kWh</b>.</p>
          <p>Los datos de cada día se cargan al cerrar la transacción diaria, y la
             transacción mensual recarga el mes completo: hasta ese cierre, los
             valores del mes en curso pueden cambiar.</p>

          <h3>Reporte de la Operación · Tipos de operación</h3>
          <ul className="codes">
            <li><b>152</b> Operación Normal</li>
            <li><b>153</b> Potencia Limitada</li>
            <li><b>155</b> Programada</li>
            <li><b>156</b> Forzada</li>
            <li><b>158</b> Prueba</li>
            <li><b>192</b> Reprogramación</li>
          </ul>

          <h3>Reporte de la Operación · Temperatura</h3>
          <p>Temperatura horaria de las <b>zonas térmicas</b> (POSTDES): horas en columnas, una fila por fecha y zona.
             «Potencia de punta y temperatura» cruza, día por día, la potencia de punta del SIN
             (retiros SMEC) con la temperatura de cada zona a esa hora.</p>

          <h3>Reporte de la Operación · Potencia térmica por temperatura</h3>
          <p>La potencia de una térmica baja cuando sube la temperatura. Se evalúa la curva
             potencia–temperatura vigente de cada unidad en la temperatura horaria de su zona y se
             compara con la potencia efectiva oficial (a temperatura media). Los demás generadores
             mantienen la potencia efectiva del Excel.</p>

          <h3>Sistema de Medición Comercial · Indicadores de potencia</h3>
          <p><b>Servicio local</b> es la energía de los intervalos con potencia
             negativa (la central consume); <b>energía bruta</b>, la de los
             positivos; <b>neta</b>, la suma de ambas.</p>

          <h3>Sistema de Medición Comercial · SIN</h3>
          <p><b>Potencia de punta</b>: para cada día, el intervalo de 15 min con el mayor retiro
             total del SIN (la punta que publica el CNDC) y la generación de las centrales marcadas
             en ese intervalo (las demás van en «Resto»; juntas suman la generación, no la punta). <b>Conciliación</b>: inyección menos
             retiro por día, es decir, pérdidas y desbalance de medición.
             <b> Potencia limitada</b>: cada evento de limitación con su límite
             frente a la potencia efectiva de la unidad y a lo que midió su
             medidor propio.</p>

          <h3>Sistema de Medición Comercial · Nivel «Jerárquico»</h3>
          <p>En Potencia, el nivel <b>Jerárquico</b> muestra una grilla
             expandible Agente → Central → Medidor (use la flecha de cada fila).</p>

          <h3>Sistema de Fallas</h3>
          <p>Reportes de fallas del sistema eléctrico. No usa árbol de
             componentes: filtre por <b>falla</b> (código puntual), <b>agente</b>
             (de la lista) y/o rango de fechas — todos opcionales. Los
             reportes de <b>Análisis de fallas</b> y <b>EDAC › Operación</b> sólo muestran
             fallas cuyo informe FINAL o RECTIFICATORIO del CNDC ya fue emitido.</p>

          <h3>SCADA HFD (Historical File Data)</h3>
          <p>Registros crudos del HFD de SCADA por archivo (generadores,
             transferencias, tensiones, embalses, taps y bancos de capacitores): una fila por medida y
             día, con la lectura de cada 15 minutos de <b>00:00 a 23:45</b>, igual
             que el archivo del HFD. Hasta 31 días por
             consulta; «Estación» acota lo que se trae de la base. Los
             <b>Consolidados</b> (generación y energía por tecnología, demanda
             por departamento) bajan hasta cada unidad o elemento medido.</p>

          <h3>Informe de Mediano Plazo</h3>
          <p>Genera los anexos 2, 4, 5 y 6 del informe con su formato final, a partir de los
             archivos que entrega Planificación. Cada estudio es una carpeta <b>AAAA-MM</b> (mes 05 u 11)
             en el servidor, con las subcarpetas <b>Anexo2</b> a <b>Anexo6</b>: los CSV y XLSX de
             siempre, el Mapa (.jpeg) y las imágenes <b>Anexo2B</b> y <b>Anexo4B</b> (.png o .jpg).
             El formato sale del <b>ANEXOn.xlsx</b> de la carpeta; si falta, del estudio anterior más
             reciente que lo tenga. No se modifica nada en el servidor: sólo se descarga el .xlsx.
             El anexo 3 queda pendiente de la base IMP.</p>

          <h3>Tips</h3>
          <ul>
            <li>Click en un encabezado de columna para <b>ordenar</b>.</li>
            <li>Marque «Totales» para sumar las columnas numéricas.</li>
            <li>«Copiar» deja la tabla lista para pegar en Excel.</li>
            <li>Estando en un campo de fecha, <b>Enter</b> genera el reporte.</li>
            <li>Los valores negativos se muestran en rojo.</li>
            <li>Pase el mouse sobre un reporte del menú para ver qué muestra.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [health, setHealth] = useState(null);
  // Entrada: «#/» abre siempre Monitores (enlace para Presidencia); si no, el último
  // módulo usado, y sin módulo guardado, Monitores.
  const [modulo, setModuloState] = useState(() => {
    if (location.hash === "#/") return "monitores";
    try { return localStorage.getItem("modulo") || "monitores"; } catch { return "monitores"; }
  });
  const setModulo = useCallback((m) => {
    setModuloState(m);
    const hash = m === "monitores" ? "#/" : "";
    if (location.hash !== hash) history.replaceState(null, "", hash || location.pathname + location.search);
  }, []);
  const [help, setHelp] = useState(false);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ oracle: "desconocido" }));
  }, []);

  useEffect(() => {
    const onHash = () => { if (location.hash === "#/") setModuloState("monitores"); };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    try { localStorage.setItem("modulo", modulo); } catch { /* almacenamiento bloqueado: no se recuerda */ }
  }, [modulo]);

  // Paneles comprimibles: se recuerda entre sesiones y es común a los módulos.
  // v2: reinicia la preferencia guardada con el umbral viejo (1400) para que
  // las laptops de 1366/1536 vean la navegación abierta al menos una vez.
  const [railOpen, setRailOpen] = usePersisted("ui.railOpen.v2", window.innerWidth >= 1280);
  const [queryOpen, setQueryOpen] = usePersisted("ui.queryOpen", true);

  const shell = useMemo(() => ({
    modulos: MODULOS, modulo, setModulo, health,
    openHelp: () => setHelp(true),
    railOpen, toggleRail: () => setRailOpen((o) => !o),
    queryOpen, toggleQuery: () => setQueryOpen((o) => !o),
  }), [modulo, setModulo, health, railOpen, queryOpen, setRailOpen, setQueryOpen]);

  return (
    <ShellContext.Provider value={shell}>
      <div className="app">
        {/* Los módulos permanecen montados para preservar su estado al alternar. */}
        <div className={`modwrap ${modulo === "monitores" ? "" : "modwrap--hidden"}`}><MonitoresModule /></div>
        <div className={`modwrap ${modulo === "indisp" ? "" : "modwrap--hidden"}`}><IndispModule /></div>
        <div className={`modwrap ${modulo === "smec" ? "" : "modwrap--hidden"}`}><SmecModule /></div>
        <div className={`modwrap ${modulo === "sisfalla" ? "" : "modwrap--hidden"}`}><SisfallaModule /></div>
        <div className={`modwrap ${modulo === "scada" ? "" : "modwrap--hidden"}`}><ScadaModule /></div>
        <div className={`modwrap ${modulo === "imp" ? "" : "modwrap--hidden"}`}><ImpModule /></div>

        {help && <HelpModal onClose={() => setHelp(false)} />}
      </div>
    </ShellContext.Provider>
  );
}
