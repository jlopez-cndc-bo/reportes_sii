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

// Suma de valores ya exactos: quita sólo el ruido binario de la suma en
// punto flotante (p. ej. 0,1 + 0,2 = 0,30000000000000004).
export function sumaLimpia(valores) {
  let s = 0;
  for (const v of valores) if (typeof v === "number") s += v;
  return Number(s.toFixed(10));
}
