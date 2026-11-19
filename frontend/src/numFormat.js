// Formato numérico compartido por la grilla, el gráfico y "Copiar".
//
// Formatos de columna que envía el backend:
//   "0.0", "0.00", …  → decimales fijos (INDISP, SISFALLA, factor de carga).
//   "num"             → valor tal cual viene de la base: todos sus decimales,
//                       sin redondear ni rellenar con ceros (SMEC).

const FIJO = /^0\.0+$/;
// 20 es el máximo portable de Intl; con él se emite la representación más
// corta del número, es decir, exactamente el valor recibido.
const MAX_DEC = 20;

export function isNumericFmt(format) {
  return !!format && (format === "num" || FIJO.test(format));
}

function opciones(format) {
  if (format === "num") return { maximumFractionDigits: MAX_DEC };
  const dec = format.split(".")[1].length;
  return { minimumFractionDigits: dec, maximumFractionDigits: dec };
}

const cache = new Map();
function formateador(locale, format, extra) {
  const key = `${locale}|${format}`;
  let f = cache.get(key);
  if (!f) {
    f = new Intl.NumberFormat(locale, { ...opciones(format), ...extra });
    cache.set(key, f);
  }
  return f;
}

// Para pantalla: separador de miles y coma decimal (es-BO).
export function formatNumber(value, format) {
  return formateador("es-BO", format).format(value);
}

// Para TSV/Excel: coma decimal, sin miles ni notación exponencial.
export function formatNumberPlain(value, format) {
  return formateador("en-US", format, { useGrouping: false }).format(value).replace(".", ",");
}

// Suma de valores ya exactos: quita el ruido binario de la suma en punto
// flotante (0,1 + 0,2 = 0,30000000000000004; con totales de millones el ruido
// aparece antes del décimo decimal). El resultado no puede tener más
// decimales que el sumando que más trae.
const decimales = (v) => {
  const s = String(v);
  if (s.includes("e")) return 10;
  const i = s.indexOf(".");
  return i < 0 ? 0 : s.length - i - 1;
};
export function sumaLimpia(valores) {
  let s = 0, dec = 0;
  for (const v of valores) {
    if (typeof v !== "number") continue;
    s += v;
    dec = Math.max(dec, decimales(v));
  }
  return Number(s.toFixed(Math.min(dec, 10)));
}

// Fila TOTAL: suma cada columna numérica salvo las `sinTotal`. En grillas
// jerárquicas sólo suman los agentes (nivel 0): las hijas repetirían valores.
export function calcTotales(result) {
  const cols = result.columns.filter((c) => !c.hidden);
  const drill = result.rows.length > 0 && result.rows[0]._nivel !== undefined;
  const base = drill ? result.rows.filter((r) => r._nivel === 0) : result.rows;
  const t = {};
  for (const c of cols) {
    if (isNumericFmt(c.format) && !c.sinTotal) t[c.key] = sumaLimpia(base.map((r) => r[c.key]));
  }
  return t;
}
