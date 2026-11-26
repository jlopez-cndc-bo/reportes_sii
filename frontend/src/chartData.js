// Series para Chart a partir de un resultado tabular: columnas numéricas como eje X, una serie
// por fila (en drill sólo el primer nivel). Se grafican hasta 8 (las de mayor magnitud),
// manteniendo el orden original para que el color siga a la entidad y no a su rango.
export function seriesDeResultado(result) {
  if (!result || result.rows.length === 0) return null;
  // "resumen": Total/Máx/Mín/Promedio no son un período del eje X.
  const numCols = result.columns.filter((c) => c.format && c.format !== "datetime" && !c.hidden && !c.resumen);
  if (numCols.length < 2) return null;
  const textKeys = result.columns.filter((c) => !c.format && !c.resumen).map((c) => c.key);
  let rows = result.rows;
  if (rows[0]?._nivel !== undefined) rows = rows.filter((r) => r._nivel === 0);
  const todas = rows.map((r, i) => ({
    i,
    name: textKeys.map((k) => r[k]).filter(Boolean).join(" · ") || `fila ${i + 1}`,
    values: numCols.map((c) => (typeof r[c.key] === "number" ? r[c.key] : null)),
  }));
  const score = (s) => Math.max(0, ...s.values.map((v) => Math.abs(v ?? 0)));
  const top = [...todas].sort((a, b) => score(b) - score(a)).slice(0, 8)
    .sort((a, b) => a.i - b.i);
  return { series: top, omitidas: todas.length - top.length, labels: numCols.map((c) => c.label) };
}
