// Tablero «Monitores»: la operación de un día (HFD, punta SMEC, indisponibilidades), cómo fue el periodo
// (tres monitores con comparaciones y tendencia) y si los datos están al día.
// Cada cifra lleva su nivel de dato y su fecha; sin meta aprobada no hay semáforo.
import { useCallback, useContext, useEffect, useState } from "react";
import { Rail, ShellContext } from "../shell";
import Chart from "../components/Chart";
import { Refresh } from "../icons";

const REFRESCO_MS = 5 * 60 * 1000;
const PERIODOS = [
  { id: "ayer", label: "Ayer" },
  { id: "mes_en_curso", label: "Mes en curso" },
  { id: "", label: "Último mes completo" },
  { id: "anio", label: "Año" },
];

const num = (v, dec) => (v == null ? "-"
  : new Intl.NumberFormat("es-BO", { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(v));
const fecha = (iso, conHora) => {
  if (!iso) return "-";
  const [d, t] = iso.split("T");
  const f = d.split("-").reverse().join("/");
  return conHora && t && !t.startsWith("00:00:00") ? `${f} ${t.slice(0, 5)}` : f;
};
const hora = (iso) => (iso ? iso.split("T")[1].slice(0, 5) : "-");
const minutosDesde = (iso, ahora) => Math.max(0, Math.round((new Date(ahora) - new Date(iso)) / 60000) - 15);

async function getJson(url) {
  const r = await fetch(url);
  if (!r.ok) {
    let detail = `Error ${r.status}`;
    try { detail = (await r.json()).detail || detail; } catch { /* sin JSON */ }
    throw new Error(detail);
  }
  return r.json();
}

// ───────────────────────────── Día ─────────────────────────────

const hoyLocal = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

// Refresco cada 5 min: sólo para hoy, con Monitores a la vista y la pestaña visible.
function useRefresco(activo, cargar) {
  useEffect(() => {
    if (!activo) return undefined;
    const t = setInterval(() => { if (!document.hidden) cargar(); }, REFRESCO_MS);
    const vis = () => { if (!document.hidden) cargar(); };
    document.addEventListener("visibilitychange", vis);
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", vis); };
  }, [activo, cargar]);
}

function Dia() {
  // Los módulos quedan montados: sólo se refresca si Monitores está a la vista.
  const visible = useContext(ShellContext).modulo === "monitores";
  const [dia, setDia] = useState(hoyLocal);
  const [data, setData] = useState(null);
  const [ahoraData, setAhoraData] = useState(null);
  const [error, setError] = useState(null);
  const [pausado, setPausado] = useState(false);
  const [cargando, setCargando] = useState(false);
  const hoy = hoyLocal();
  const esHoy = dia === hoy;

  const cargar = useCallback(() => {
    setCargando(true);
    Promise.all([getJson(`/api/tablero/dia?fecha=${dia}`), getJson("/api/tablero/ahora")])
      .then(([d, a]) => { setData(d); setAhoraData(a); setError(null); })
      .catch((e) => setError(e.message))   // conserva el último valor
      .finally(() => setCargando(false));
  }, [dia]);

  useEffect(() => { cargar(); }, [cargar]);
  useRefresco(esHoy && visible && !pausado, cargar);

  const hfd = data?.hfd;
  const ind = data?.indisponibles;
  return (
    <section className="mon-ahora" aria-labelledby="mon-dia-t">
      <header className="mon-sec-head">
        <h2 id="mon-dia-t">Operación del día</h2>
        <label className="mon-fecha"><span className="sr-only">Fecha</span>
          <input type="date" value={dia} max={hoy} onChange={(e) => e.target.value && setDia(e.target.value)} /></label>
        {ahoraData?.smec_ultimo_dia && dia !== ahoraData.smec_ultimo_dia && (
          <button type="button" className="pill-btn" onClick={() => setDia(ahoraData.smec_ultimo_dia)}>Último día SMEC</button>
        )}
        {!esHoy && <button type="button" className="pill-btn" onClick={() => setDia(hoy)}>Hoy</button>}
        <span className="mon-meta">
          {data ? `Consultado ${hora(data.generado)}` : "Cargando…"}
          {esHoy && pausado && " · actualización automática en pausa"}
        </span>
        <span className="mon-acciones">
          <button type="button" className="pill-btn" onClick={cargar} disabled={cargando}>
            <Refresh size={12} /> {cargando ? "Actualizando…" : "Actualizar"}</button>
          {esHoy && <button type="button" className="pill-btn" onClick={() => setPausado((p) => !p)}>
            {pausado ? "Reanudar" : "Pausar"}</button>}
        </span>
      </header>
      {error && <div className="error-box" role="alert">No se pudo actualizar: {error}
        {data && " Se muestra el último valor."}</div>}
      <div aria-live="polite">
        {ahoraData?.alertas.length > 0 && (
          <ul className="mon-alertas">
            {ahoraData.alertas.map((a) => (
              <li key={a.texto} className={a.nivel === "alta" ? "error-box" : "warn-box"}>
                <span aria-hidden="true">{"⚠︎"}</span> {a.texto}</li>
            ))}
          </ul>
        )}
      </div>
      {data && data.fecha === dia && (
        <>
          <div className="mon-ahora-grid">
            <div className="mon-bloque">
              <div className="mon-etq">Demanda del SIN</div>
              {hfd ? <>
                {esHoy ? (
                  <div className="mon-cifra">{num(hfd.ultima.mw, 0)} <span className="mon-unidad">MW</span>
                    <span className="mon-cifra-2">demanda actual ({hora(hfd.ultima.hora)})</span></div>
                ) : (
                  <div className="mon-cifra">{num(hfd.maxima.mw, 0)} <span className="mon-unidad">MW</span>
                    <span className="mon-cifra-2">máx. del día</span></div>
                )}
                <div className="mon-sub">Máx. del día <b>{num(hfd.maxima.mw, 0)} MW</b> a las {hora(hfd.maxima.hora)}
                  {" · "}Mín. del día <b>{num(hfd.minima.mw, 0)} MW</b> a las {hora(hfd.minima.hora)}</div>
                <Fuente rotulo="HFD operativo"
                  fecha={esHoy ? `intervalo ${hora(hfd.fecha_dato)} · hace ${minutosDesde(hfd.fecha_dato, data.generado)} min`
                    : `${hfd.intervalos} de 96 intervalos · ${fecha(data.fecha)}`} />
              </> : <p className="mon-nota">HFD sin datos para este día.</p>}
            </div>
            <div className="mon-bloque">
              <div className="mon-etq">Potencia de punta{data.dia_smec === data.fecha ? " del día"
                : data.punta.valor != null ? ` · ${fecha(data.dia_smec)}` : ""}</div>
              {data.dia_smec !== data.fecha && data.punta.valor != null && (
                <p className="mon-aviso-smec">Último dato SMEC: {fecha(data.dia_smec)}. El día {fecha(data.fecha)} se
                  carga al cerrar la transacción diaria.</p>
              )}
              {data.punta.valor != null ? <>
                <div className={`mon-cifra${data.dia_smec !== data.fecha ? " mon-cifra--previa" : ""}`}>
                  <Cifra k={{ ...data.punta, unidad: "MW" }}>
                  {num(data.punta.valor, 1)} <span className="mon-unidad">MW</span></Cifra></div>
                <div className="mon-sub">a las {hora(data.punta.detalle.fecha_hora)}
                  {data.energia.valor != null && <> · Demanda de energía <b>{num(data.energia.valor * 1000, 1)} MWh</b></>}</div>
                <Fuente rotulo="SMEC oficial" fecha={`retiros del ${fecha(data.dia_smec)}`} />
              </> : <>
                <p className="mon-nota">SMEC todavía no tiene este día: se carga al cerrar la transacción diaria.</p>
                <Fuente rotulo="SMEC oficial" fecha={`último día cargado ${fecha(ahoraData?.smec_ultimo_dia)}`} />
              </>}
            </div>
            <div className="mon-bloque">
              <div className="mon-etq">{esHoy ? "Unidades indisponibles ahora" : "Unidades con indisponibilidad en el día"}</div>
              <div className="mon-cifra">{ind.unidades.length} <span className="mon-unidad">unidades</span>
                {esHoy && <span className="mon-cifra-2">{num(ind.mw, 0)} MW</span>}</div>
              <Indisponibles ind={ind} esHoy={esHoy} />
              <Fuente rotulo="Registro de eventos"
                fecha={esHoy ? `Indisponibilidad Programada y Forzada abierta al ${fecha(ind.fecha_dato, true)}` : `Indisponibilidad Programada y Forzada del ${fecha(data.fecha)}`} />
            </div>
          </div>
          <PotenciaParque p={data.potencia} esHoy={esHoy} />
          <Temperaturas temps={data.temperaturas} fechaDia={data.fecha} esHoy={esHoy}
            punta={data.dia_smec === data.fecha ? data.punta : { valor: null }} />
          {hfd && (
            <div className="mon-curvas">
              <figure className="mon-curva">
                <figcaption>Curva de demanda del SIN (MW, HFD operativo)</figcaption>
                <Chart series={[{ name: "Demanda del SIN", values: hfd.demanda }]} labels={hfd.etiquetas} unit="MW" />
              </figure>
              <figure className="mon-curva">
                <figcaption>Curva de generación por fuente (MW, HFD operativo; no se grafica la Exportación)</figcaption>
                <Chart series={hfd.generacion.map((g) => ({ name: g.nombre, values: g.valores }))}
                  labels={hfd.etiquetas} unit="MW" />
              </figure>
            </div>
          )}
        </>
      )}
      {ahoraData && <div className="mon-hoy"><Salud data={ahoraData} /></div>}
    </section>
  );
}

function PotenciaParque({ p, esHoy }) {
  if (!p) return null;
  const cuando = p.punta != null ? `a la hora de punta (${hora(p.instante)})` : `${esHoy ? "ahora" : "a las"} (${p.hora})`;
  return (
    <div className="mon-bloque mon-temp">
      <div className="mon-etq">Potencia del parque {cuando}</div>
      <dl className="mon-ecuacion">
        <div><dt>Potencia efectiva oficial (temperatura media)</dt><dd>{num(p.total_excel, 0)} MW</dd></div>
        <div><dt>Térmicas por la temperatura real</dt><dd>{conSigno(p.total - p.total_excel)} MW</dd></div>
        <div><dt>Unidades con Indisponibilidad Programada o Forzada (a temperatura real)</dt>
          <dd>{conSigno(-p.indisponible)} MW</dd></div>
        <div className="mon-ecuacion-total"><dt>Disponible</dt><dd>{num(p.disponible, 0)} MW</dd></div>
      </dl>
      {p.margen != null && <div className="mon-sub">Margen sobre la punta de {num(p.punta, 0)} MW: <b>{num(p.margen, 0)} MW</b></div>}
      <Fuente rotulo="Analítico · estimado"
        fecha={`${p.unidades_curva} térmicas con curva potencia–temperatura de su zona; el resto, potencia efectiva oficial. `
          + "Los MW indisponibles difieren del bloque «Unidades indisponibles», que usa la potencia oficial. "
          + "No descuenta potencia limitada ni recurso renovable real."} />
    </div>
  );
}

// «−88», «+12» o «0», sin «−0» ni «−-12».
function conSigno(v) {
  const r = Math.round(v);
  return r === 0 ? "0" : `${r < 0 ? "−" : "+"}${num(Math.abs(r), 0)}`;
}

function Temperaturas({ temps, punta, fechaDia, esHoy }) {
  if (!temps || temps.length === 0) {
    return <div className="mon-bloque mon-temp"><div className="mon-etq">Temperatura por zona térmica</div>
      <p className="mon-nota">Sin lecturas de temperatura para este día.</p></div>;
  }
  const hp = punta.valor != null ? hora(punta.detalle.fecha_hora) : null;
  const consolidado = temps.every((t) => t.consolidado);
  return (
    <div className="mon-bloque mon-temp">
      <div className="mon-etq">Temperatura por zona térmica (°C)</div>
      <div className="mon-tabla-wrap mon-tabla-wrap--auto">
        <table className="mon-tabla">
          <thead>
            <tr><td />{temps.map((t) => <th key={t.zona} scope="col" className="n">{t.zona}</th>)}</tr>
          </thead>
          <tbody>
            {esHoy && (() => {
              const ult = temps.map((t) => t.valores.findLastIndex((v) => v != null));
              const comun = ult.every((i) => i === ult[0]);
              const hh = (i) => `${String(i).padStart(2, "0")}:00`;
              return <tr><th scope="row">Última lectura{comun && ` (${hh(ult[0])})`}</th>{temps.map((t, k) => (
                <td key={t.zona} className="n">{num(t.valores[ult[k]], 0)}
                  {!comun && <> <span className="mon-meta">{hh(ult[k])}</span></>}</td>))}</tr>;
            })()}
            <tr><th scope="row">{esHoy ? "Máx. hasta ahora" : "Máx. del día"}</th>{temps.map((t) => (
              <td key={t.zona} className="n">{num(t.maxima, 0)} <span className="mon-meta">{t.hora_max}</span></td>))}</tr>
            {hp && <tr><th scope="row">A la hora de punta ({hp})</th>{temps.map((t) => (
              <td key={t.zona} className="n">{num(t.a_la_punta, 0)}</td>))}</tr>}
          </tbody>
        </table>
      </div>
      <Fuente rotulo="Temperatura" fecha={`zonas térmicas (POSTDES), ${fecha(fechaDia)}${consolidado ? "" : " · sin consolidar"}`} />
    </div>
  );
}

function Indisponibles({ ind, esHoy }) {
  if (ind.unidades.length === 0) {
    return <p className="mon-nota">{esHoy ? "Ninguna unidad con evento abierto." : "Ninguna unidad con Indisponibilidad Programada o Forzada ese día."}</p>;
  }
  const cc = ind.unidades.filter((u) => u.estado_cc).length;
  return (
    <details className="mon-det">
      <summary>Ver cuáles ({ind.unidades.length})</summary>
      <div className="mon-tabla-wrap">
        <table className="mon-tabla">
          <thead>{esHoy
            ? <tr><th>Unidad</th><th>Central</th><th>Tipo</th><th className="n">MW</th><th>Desde</th><th>Causa</th></tr>
            : <tr><th>Unidad</th><th>Central</th><th className="n">MW</th><th className="n">Horas forzada</th><th className="n">Horas programada</th></tr>}
          </thead>
          <tbody>
            {ind.unidades.map((u) => (
              <tr key={u.unidad}>
                <td>{u.unidad}{u.estado_cc && <span className="mon-tag" title="Estado de ciclo combinado: no suma MW">CC</span>}</td>
                <td>{u.central || "-"}</td>
                {esHoy ? <>
                  <td>{u.tipo}</td>
                  <td className="n">{num(u.mw, 1)}</td>
                  <td>{u.desde_limite ? "antes del " : ""}{fecha(u.desde, true)}</td>
                  <td>{u.causa || "-"}</td>
                </> : <>
                  <td className="n">{num(u.mw, 1)}</td>
                  <td className="n">{num(u.horas_forzada, 2)}</td>
                  <td className="n">{num(u.horas_programada, 2)}</td>
                </>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mon-nota">MW = potencia efectiva oficial vigente.
        {cc > 0 && ` ${cc} estado(s) de ciclo combinado (CC): ${esHoy ? "no suman MW para no contar el bloque dos veces" : "se muestran aparte del bloque"}.`}
        {ind.sin_mw > 0 && ` ${ind.sin_mw} unidad(es) sin potencia efectiva en la tabla.`}</p>
    </details>
  );
}

function Salud({ data }) {
  const cong = data.hfd?.congeladas || [];
  const smecDias = data.smec_ultimo_dia
    ? Math.round((new Date(data.generado.slice(0, 10)) - new Date(data.smec_ultimo_dia)) / 86400000) : null;
  return (
    <div className="mon-salud" role="group" aria-label="Salud de los datos">
      <b>Salud de los datos</b>
      <span>SMEC: último día cargado {fecha(data.smec_ultimo_dia)}{smecDias != null && ` (hace ${smecDias} día${smecDias === 1 ? "" : "s"})`}</span>
      <span>HFD: {data.hfd ? `hace ${minutosDesde(data.hfd.fecha_dato, data.generado)} min` : "sin datos"}</span>
      {cong.length > 0 ? (
        <details className="mon-det mon-det--inline">
          <summary>{cong.length} señal(es) HFD sin cambio</summary>
          <ul>{cong.map((c) => <li key={c.unidad}>{c.unidad} · {c.central} · {num(c.mw, 2)} MW</li>)}</ul>
        </details>
      ) : <span>Sin señales HFD congeladas</span>}
    </div>
  );
}

// ───────────────────────────── Monitores ─────────────────────────────

function Fuente({ rotulo, fecha: f }) {
  return <div className="mon-fuente"><span className="mon-nivel">{rotulo}</span> · {f}</div>;
}

function Sparkline({ tendencia, dec, unidad }) {
  const vals = tendencia.map((t) => t.valor);
  const nums = vals.filter((v) => v != null);
  if (nums.length < 2) return null;
  const W = 220, H = 40, P = 3;
  const min = Math.min(...nums), max = Math.max(...nums), span = max - min || 1;
  const x = (i) => P + (i * (W - 2 * P)) / (vals.length - 1);
  const y = (v) => H - P - ((v - min) * (H - 2 * P)) / span;
  let d = "", pen = false;
  vals.forEach((v, i) => {
    if (v == null) { pen = false; return; }
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
    pen = true;
  });
  const ult = vals.length - 1;
  const label = `${tendencia.length} meses (${tendencia[0].etiqueta} a ${tendencia[ult].etiqueta}): `
    + `mínimo ${num(min, dec)}, máximo ${num(max, dec)} ${unidad}`;
  return (
    <svg className="mon-spark" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      <title>{label}</title>
      <path d={d} fill="none" stroke="var(--brand)" strokeWidth="1.6" />
      {vals[ult] != null && <circle cx={x(ult)} cy={y(vals[ult])} r="2.6" fill="var(--brand-dark)" />}
    </svg>
  );
}

function Comparaciones({ k, compacto }) {
  return (
    <ul className={`mon-comp ${compacto ? "mon-comp--compacto" : ""}`}>
      {k.comparaciones.map((c) => {
        if (c.delta == null) {
          return <li key={c.etiqueta} className="mon-comp-sin">Sin comparación con {c.etiqueta}:
            {c.valor == null ? " sin dato" : " el valor anterior es 0"}</li>;
        }
        const flecha = c.delta > 0 ? "▲" : c.delta < 0 ? "▼" : "=";
        const delta = k.comparar === "puntos" ? `${num(Math.abs(c.delta), 2)} pp` : `${num(Math.abs(c.delta), 1)} %`;
        return (
          <li key={c.etiqueta}>
            <span aria-hidden="true">{flecha}</span>
            <span className="sr-only">{c.delta > 0 ? "sube" : "baja"}</span> {delta} vs {c.etiqueta}
            {!compacto && <span className="mon-comp-ant"> ({num(c.valor, k.decimales)} {k.unidad})</span>}
          </li>
        );
      })}
    </ul>
  );
}

function Semaforo({ s }) {
  if (!s) return <div className="mon-meta-def">Meta por definir</div>;
  const txt = { verde: "En meta", ambar: "Cerca de la meta", rojo: "Fuera de meta" }[s.estado];
  return <div className={`mon-sem mon-sem--${s.estado}`}>{txt} · meta {s.meta}</div>;
}

// Valor sin redondear (D-K: la tarjeta redondea): kW/kWh de SMEC o el número tal cual.
const exacto = (k) => (k.valor == null ? null
  : k.detalle?.kw != null ? `${num(k.detalle.kw, 2)} kW`
    : k.detalle?.kwh != null ? `${num(k.detalle.kwh, 2)} kWh`
      : `${new Intl.NumberFormat("es-BO", { maximumFractionDigits: 6 }).format(k.valor)} ${k.unidad}`);

function Cifra({ k, className, children }) {
  if (k.valor == null) return <span className={className}>Sin dato</span>;
  const ex = exacto(k);
  return (
    <span className={className} title={`Valor exacto: ${ex}`} tabIndex={0}>
      {children}<span className="sr-only"> (valor exacto: {ex})</span>
    </span>
  );
}

const fechaDato = (k) => (fecha(k.fecha_dato, true) === "-" ? "sin dato en el periodo" : `dato al ${fecha(k.fecha_dato, true)}`);

function Tarjeta({ k }) {
  const h = k.maximo_historico;
  const esMaximo = h && k.valor != null && Math.abs(k.valor - h.valor) < 1e-6;
  return (
    <div className="mon-principal">
      <h3 className="mon-ind" title={k.descripcion}>{k.nombre}</h3>
      <div className="mon-cifra">
        <Cifra k={k}>{num(k.valor, k.decimales)} <span className="mon-unidad">{k.unidad}</span></Cifra>
        {k.calidad === "parcial" && <span className="mon-tag mon-tag--warn">parcial</span>}
      </div>
      {k.detalle?.fecha_hora && <div className="mon-sub">el {fecha(k.detalle.fecha_hora, true)}</div>}
      {h && (
        <div className={`mon-hist ${esMaximo ? "mon-hist--nuevo" : ""}`}>
          {esMaximo ? "Nuevo máximo histórico" : "Máximo histórico"}: <b>{num(h.valor, k.decimales)} {k.unidad}</b>
          {" "}el {fecha(h.fecha_hora, true)} <span className="mon-meta">(serie desde {fecha(h.desde)})</span>
        </div>
      )}
      <Comparaciones k={k} />
      <Sparkline tendencia={k.tendencia} dec={k.decimales} unidad={k.unidad} />
      <Semaforo s={k.semaforo} />
      {k.nota && <p className="mon-nota">{k.nota}</p>}
      <Fuente rotulo={k.nivel.rotulo} fecha={fechaDato(k)} />
    </div>
  );
}

function Secundaria({ k, principal }) {
  // D-22: pastilla de nivel y fecha sólo si difieren de los de la cifra principal.
  const distinto = k.nivel.id !== principal.nivel.id
    || (principal.fecha_dato != null && k.fecha_dato !== principal.fecha_dato);
  return (
    <div className="mon-sec">
      <div className="mon-sec-fila">
        <span className="mon-sec-nombre" title={k.descripcion}>{k.nombre}</span>
        <span className="mon-sec-valor">
          <Cifra k={k}>{num(k.valor, k.decimales)} {k.unidad}</Cifra>
          {k.calidad === "parcial" && <span className="mon-tag mon-tag--warn">parcial</span>}</span>
      </div>
      {distinto && <span className="mon-tag">{k.nivel.rotulo} · {fechaDato(k)}</span>}
      <Comparaciones k={k} compacto />
      {k.nota && <p className="mon-nota">{k.nota}</p>}
    </div>
  );
}

function Monitor({ m, irA }) {
  const modulo = useContext(ShellContext).modulos.find((x) => x.id === m.modulo);
  return (
    <article className="mon-card" aria-labelledby={`mon-${m.dominio}`}>
      <h2 id={`mon-${m.dominio}`} className="mon-dom">{m.nombre}</h2>
      <Tarjeta k={m.principal} />
      {m.secundarios.map((k) => <Secundaria key={k.id} k={k} principal={m.principal} />)}
      {modulo && (
        <button type="button" className="mon-ir" onClick={() => irA(m.modulo)}>
          Ver el detalle en {modulo.label} ›</button>
      )}
    </article>
  );
}

function Periodo({ periodo, setPeriodo, etiqueta }) {
  return (
    <div className="mon-periodo" role="group" aria-label="Periodo">
      <span className="mon-etq">Periodo</span>
      {PERIODOS.map((p) => (
        <button key={p.id} type="button" className="mon-seg" aria-pressed={periodo === p.id}
          onClick={() => setPeriodo(p.id)}>{p.label}</button>
      ))}
      {etiqueta && <span className="mon-meta">{etiqueta}</span>}
    </div>
  );
}

export default function MonitoresModule() {
  const sh = useContext(ShellContext);
  const [periodo, setPeriodo] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [cargando, setCargando] = useState(false);

  useEffect(() => {
    let vivo = true;
    setCargando(true);
    getJson(`/api/tablero/inicio${periodo ? `?periodo=${periodo}` : ""}`)
      .then((d) => { if (vivo) { setData(d); setError(null); } })
      .catch((e) => { if (vivo) setError(e.message); })
      .finally(() => { if (vivo) setCargando(false); });
    return () => { vivo = false; };
  }, [periodo]);

  const niveles = data?.niveles || [];
  return (
    <div className="layout">
      <Rail grupos={[]} reports={[]} activeId={null} onPick={() => {}} />
      <main className="content mon-content">
        <h1 className="mon-titulo">Monitores del SIN</h1>
        <Dia />
        <header className="mon-sec-head mon-sec-head--periodo">
          <h2>Indicadores del período</h2>
          <span className="mon-meta">No dependen de la fecha de «Operación del día».</span>
        </header>
        <Periodo periodo={periodo} setPeriodo={setPeriodo} etiqueta={data?.periodo.etiqueta} />
        {data?.metas_cargadas === 0 && (
          <p className="mon-nota">Las metas se cargan a medida que las gerencias las aprueban.</p>
        )}
        {error && <div className="error-box" role="alert">{error}</div>}
        {cargando && !data && <div className="results-state"><span className="spinner" /> Calculando indicadores…</div>}
        {data && (
          <div className={`mon-grid ${cargando ? "mon-grid--cargando" : ""}`} aria-busy={cargando}>
            {data.monitores.map((m) => <Monitor key={m.dominio} m={m} irA={sh.setModulo} />)}
          </div>
        )}
        {niveles.length > 0 && (
          <footer className="mon-niveles">
            {niveles.map((n) => (
              <span key={n.id}><span className="mon-nivel">{n.rotulo}</span> {n.descripcion}</span>
            ))}
            <span>Cifras redondeadas; el valor exacto aparece al pasar el mouse o enfocar la cifra.</span>
          </footer>
        )}
      </main>
    </div>
  );
}
