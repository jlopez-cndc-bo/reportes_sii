import { useRef, useState } from "react";

// Gráfico de líneas SVG sin dependencias, para series temporales SMEC
// (potencia por intervalo, energía por día/mes/año).
// Paleta categórica validada (CVD ΔE 24.2 sobre blanco); el orden de los
// slots es fijo — los colores siguen al orden de las series, nunca se ciclan.
export const CHART_COLORS = [
  "#2a78d6", "#1baf7a", "#eda100", "#008300",
  "#4a3aa7", "#e34948", "#e87ba4", "#eb6834",
];

const W = 920, H = 340;
const M = { top: 16, right: 110, bottom: 30, left: 70 };
const INK_MUTED = "#898781", GRID = "#e1e0d9", BASELINE = "#c3c2b7";

function niceTicks(min, max, n = 5) {
  const span = max - min || 1;
  const raw = span / n;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 5, 10].map((m) => m * mag)
    .reduce((a, b) => (Math.abs(b - raw) < Math.abs(a - raw) ? b : a));
  const out = [];
  for (let t = Math.ceil(min / step) * step; t <= max + 1e-9; t += step) out.push(t);
  return out;
}

const nf = new Intl.NumberFormat("es-BO", { maximumFractionDigits: 1 });

export default function Chart({ series, labels, unit, omitidas }) {
  const [hover, setHover] = useState(null);
  const svgRef = useRef(null);

  const nums = series.flatMap((s) => s.values.filter((v) => typeof v === "number"));
  if (nums.length === 0) {
    return <div className="results-state results-state--muted">Sin valores numéricos para graficar.</div>;
  }
  let yMin = Math.min(0, ...nums), yMax = Math.max(0, ...nums);
  if (yMin === yMax) yMax = yMin + 1;
  const pad = (yMax - yMin) * 0.06;
  yMax += pad;
  if (yMin < 0) yMin -= pad;

  const innerW = W - M.left - M.right, innerH = H - M.top - M.bottom;
  const x = (i) => M.left + (labels.length <= 1 ? innerW / 2 : (i * innerW) / (labels.length - 1));
  const y = (v) => M.top + ((yMax - v) * innerH) / (yMax - yMin);

  const yTicks = niceTicks(yMin, yMax);
  const xStep = Math.max(1, Math.ceil(labels.length / 8));
  const xTicks = labels.map((_, i) => i).filter((i) => i % xStep === 0);
  const conMarcadores = labels.length <= 40;

  const path = (vals) => {
    let d = "", pen = false;
    vals.forEach((v, i) => {
      if (typeof v !== "number") { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    return d;
  };

  const onMove = (e) => {
    const rect = svgRef.current.getBoundingClientRect();
    const px = ((e.clientX - rect.left) * W) / rect.width;
    const i = Math.round(((px - M.left) / innerW) * (labels.length - 1));
    setHover(Math.max(0, Math.min(labels.length - 1, i)));
  };

  // Tooltip: valores en el índice bajo el cursor, mayores primero (máx. 6).
  const tip = hover === null ? null : series
    .map((s, si) => ({ name: s.name, v: s.values[hover], color: CHART_COLORS[si] }))
    .filter((t) => typeof t.v === "number")
    .sort((a, b) => b.v - a.v)
    .slice(0, 6);
  const tipW = 230, tipH = tip ? 20 + tip.length * 16 : 0;
  const tipX = hover !== null && x(hover) + 12 + tipW > W - M.right + 100
    ? x(hover) - tipW - 12 : (hover !== null ? x(hover) + 12 : 0);

  return (
    <div className="chart-wrap">
      <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="chart-svg" role="img"
        aria-label={`Gráfico de líneas (${unit})`}
        onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
        {/* Grilla y eje Y */}
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)}
              stroke={t === 0 ? BASELINE : GRID} strokeWidth={t === 0 ? 1.2 : 1} />
            <text x={M.left - 8} y={y(t) + 3.5} textAnchor="end" fontSize="11" fill={INK_MUTED}>
              {nf.format(t)}
            </text>
          </g>
        ))}
        <text x={M.left - 8} y={M.top - 4} textAnchor="end" fontSize="10" fill={INK_MUTED}>{unit}</text>
        {/* Eje X */}
        {xTicks.map((i) => (
          <text key={i} x={x(i)} y={H - 8} textAnchor="middle" fontSize="11" fill={INK_MUTED}>
            {labels[i]}
          </text>
        ))}
        {/* Series */}
        {series.map((s, si) => (
          <g key={s.name}>
            <path d={path(s.values)} fill="none" stroke={CHART_COLORS[si]} strokeWidth="2"
              strokeLinejoin="round" strokeLinecap="round" />
            {conMarcadores && s.values.map((v, i) =>
              typeof v === "number" ? (
                <circle key={i} cx={x(i)} cy={y(v)} r="4"
                  fill={CHART_COLORS[si]} stroke="#fff" strokeWidth="2" />
              ) : null)}
            {/* Etiqueta directa al final (sólo con pocas series) */}
            {series.length <= 4 && (() => {
              let last = -1;
              s.values.forEach((v, i) => { if (typeof v === "number") last = i; });
              if (last < 0) return null;
              return (
                <text x={x(last) + 7} y={y(s.values[last]) + 4} fontSize="11"
                  fill="#52514e" fontWeight="600">{s.name}</text>
              );
            })()}
          </g>
        ))}
        {/* Crosshair + tooltip */}
        {hover !== null && (
          <g pointerEvents="none">
            <line x1={x(hover)} x2={x(hover)} y1={M.top} y2={H - M.bottom}
              stroke={BASELINE} strokeDasharray="3 3" />
            {tip && tip.length > 0 && (
              <g transform={`translate(${tipX},${M.top + 4})`}>
                <rect width={tipW} height={tipH} rx="6" fill="#fff"
                  stroke={GRID} filter="drop-shadow(0 1px 3px rgba(0,0,0,.15))" />
                <text x="10" y="15" fontSize="11" fontWeight="700" fill="#0b0b0b">
                  {labels[hover]}
                </text>
                {tip.map((t, k) => (
                  <g key={t.name} transform={`translate(10,${28 + k * 16})`}>
                    <rect width="9" height="9" y="-8" rx="2" fill={t.color} />
                    <text x="14" fontSize="11" fill="#52514e">
                      {t.name.length > 20 ? t.name.slice(0, 19) + "…" : t.name}
                    </text>
                    <text x={tipW - 20} fontSize="11" textAnchor="end" fill="#0b0b0b"
                      fontVariant="tabular-nums">{nf.format(t.v)}</text>
                  </g>
                ))}
              </g>
            )}
          </g>
        )}
      </svg>
      {/* Leyenda (identidad nunca sólo por color: chip + texto en tinta) */}
      {series.length >= 2 && (
        <div className="chart-legend">
          {series.map((s, si) => (
            <span key={s.name} className="chart-legend-item">
              <span className="chart-chip" style={{ background: CHART_COLORS[si] }} />
              {s.name}
            </span>
          ))}
          {omitidas > 0 && (
            <span className="chart-legend-item chart-legend-note">
              +{omitidas} serie(s) no graficada(s) — reduzca la selección o use la Tabla
            </span>
          )}
        </div>
      )}
    </div>
  );
}
