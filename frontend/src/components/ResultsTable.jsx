import { useEffect, useMemo, useState } from "react";
import { formatNumber, isNumericFmt, calcTotales } from "../numFormat";
import { Chevron } from "../icons";

// Filas renderizadas inicialmente; con cientos de columnas el DOM crece
// rápido, así que se pagina el render.
const PAGE = 300;
// Tope de celdas renderizadas: 300 filas × ~670 columnas ya se dibuja bien. shortcut: estimado, no medido en el
// equipo más lento; ajustar si «Mostrar más» se siente pesado.
const MAX_CELDAS = 200_000;

function fmt(value, format) {
  if (value === null || value === undefined) return "-";
  if (format === "datetime") {
    const d = new Date(value);
    if (isNaN(d)) return String(value);
    const p = (n) => String(n).padStart(2, "0");
    return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  if (isNumericFmt(format) && typeof value === "number") {
    return formatNumber(value, format);
  }
  return String(value);
}

export default function ResultsTable({ result, loading, showTotals, emptyHint, placeholder, rowAction }) {
  const [sort, setSort] = useState({ key: null, dir: 1 });
  const [limit, setLimit] = useState(PAGE);
  // Filas expandidas en modo jerárquico (índices sobre result.rows).
  const [expanded, setExpanded] = useState(new Set());
  const [filtro, setFiltro] = useState("");

  useEffect(() => {
    setLimit(PAGE); setExpanded(new Set()); setSort({ key: null, dir: 1 }); setFiltro("");
  }, [result]);

  const cols = result ? result.columns.filter((c) => !c.hidden) : [];
  const maxFilas = Math.max(PAGE, Math.floor(MAX_CELDAS / Math.max(1, cols.length)));
  // Modo drill-down: filas planas en orden de árbol con _nivel (0/1/2).
  const drill = !!(result && result.rows.length > 0 && result.rows[0]._nivel !== undefined);

  const rows = useMemo(() => {
    if (!result) return [];
    if (drill || !sort.key) return result.rows;
    const col = cols.find((c) => c.key === sort.key);
    const num = col && col.format && col.format !== "datetime";
    return [...result.rows].sort((a, b) => {
      let va = a[sort.key], vb = b[sort.key];
      if (va == null) return 1;
      if (vb == null) return -1;
      if (num) { va = Number(va); vb = Number(vb); }
      else { va = String(va); vb = String(vb); }
      return (va < vb ? -1 : va > vb ? 1 : 0) * sort.dir;
    });
  }, [result, sort, cols, drill]);

  // ¿La fila i (en orden de árbol) tiene hijas?
  const hasChildren = (i) =>
    i + 1 < rows.length && rows[i + 1]._nivel > rows[i]._nivel;

  const q = filtro.trim().toLowerCase();

  // Índices visibles: filtro de texto (columnas no numéricas) + expansión.
  const view = useMemo(() => {
    const textKeys = cols.filter((c) => !c.format && !c.resumen).map((c) => c.key);
    const coincide = (r) =>
      !q || textKeys.some((k) => r[k] != null && String(r[k]).toLowerCase().includes(q));

    if (!drill) {
      const out = [];
      for (let i = 0; i < rows.length; i++) if (coincide(rows[i])) out.push(i);
      return out;
    }
    if (q) {
      // Con filtro: coincidencias + sus ancestros, todo expandido.
      const keep = new Set();
      const ancestros = [];
      for (let i = 0; i < rows.length; i++) {
        const nv = rows[i]._nivel;
        ancestros[nv] = i;
        ancestros.length = nv + 1;
        if (coincide(rows[i])) ancestros.forEach((ix) => keep.add(ix));
      }
      return [...keep].sort((a, b) => a - b);
    }
    const out = [];
    let collapseAt = null; // nivel del ancestro colapsado
    for (let i = 0; i < rows.length; i++) {
      const nv = rows[i]._nivel;
      if (collapseAt !== null && nv > collapseAt) continue;
      collapseAt = null;
      out.push(i);
      if (hasChildren(i) && !expanded.has(i)) collapseAt = nv;
    }
    return out;
  }, [drill, rows, expanded, q, cols]);

  const totales = useMemo(
    () => (showTotals && result ? calcTotales(result) : null),
    [showTotals, result]);

  if (loading) {
    return <div className="results-state" role="status"><span className="spinner" /> Generando reporte…</div>;
  }
  if (!result) {
    return <div className="results-state results-state--muted">{placeholder || "Configure los filtros y pulse «Generar reporte»."}</div>;
  }
  if (result.rows.length === 0) {
    return <div className="results-state results-state--muted">{emptyHint || "La consulta no devolvió filas."}</div>;
  }

  const onSort = (key) => {
    if (drill) return; // el orden jerárquico no se reordena
    setSort((s) => s.key !== key ? { key, dir: 1 } : s.dir === 1 ? { key, dir: -1 } : { key: null, dir: 1 });
  };

  const toggleRow = (i) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });

  const expandAll = (on) => {
    if (!on) { setExpanded(new Set()); return; }
    const all = new Set();
    for (let i = 0; i < rows.length; i++) if (hasChildren(i)) all.add(i);
    setExpanded(all);
  };

  return (
    <div className="results-wrap">
      <div className="results-tools">
        <input className="results-filter" type="search" aria-label="Filtrar resultados" placeholder="Filtrar resultados…"
          value={filtro} onChange={(e) => setFiltro(e.target.value)} />
        <span className="results-filter-info" role="status">{q ? `${view.length} coincidencia(s)` : ""}</span>
        {view.length > limit && (
          <div className="results-page-actions">
            <span>Mostrando {limit.toLocaleString("es-BO")} de {view.length.toLocaleString("es-BO")}</span>
            {limit < maxFilas ? (
              <>
                <button type="button" className="mini-btn" onClick={() => setLimit((l) => Math.min(l + PAGE * 2, maxFilas))}>Mostrar más</button>
                {view.length <= maxFilas && (
                  <button type="button" className="mini-btn" onClick={() => setLimit(view.length)}>Mostrar todas</button>
                )}
              </>
            ) : (
              <span>Para ver todas las filas, use «Copiar» o exporte a Excel.</span>
            )}
          </div>
        )}
        {drill && (
          <>
            <span className="results-tools-hint">Expanda {cols[0].label.split(" / ").join(" → ")}</span>
            <button type="button" className="mini-btn" onClick={() => expandAll(true)}>Expandir todo</button>
            <button type="button" className="mini-btn" onClick={() => expandAll(false)}>Colapsar todo</button>
          </>
        )}
      </div>
      <div className="results-scroll">
      <table className="results-table">
        <thead>
          <tr>
            {cols.map((c, idx) => {
              const sorted = !drill && sort.key === c.key;
              return (
                <th key={c.key} className={`${idx === 0 ? "sticky-col" : ""} ${drill ? "" : "th-sort"}`} title={c.label}
                  aria-sort={sorted ? (sort.dir === 1 ? "ascending" : "descending") : undefined}>
                  {drill ? c.label : (
                    <button type="button" className="th-sort-btn" onClick={() => onSort(c.key)}>
                      {c.label}
                      {sorted && <Chevron size={10} dir={sort.dir === 1 ? "up" : "down"} className="sort-ind" />}
                    </button>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {view.slice(0, limit).map((ri) => {
            const row = rows[ri];
            return (
              <tr key={ri} className={drill ? `drill-row drill-row--n${row._nivel}` : ""}>
                {cols.map((c, idx) => {
                  const numeric = c.format && c.format !== "datetime";
                  const v = row[c.key];
                  const neg = numeric && typeof v === "number" && v < 0;
                  const cls = [idx === 0 ? "sticky-col" : "", numeric ? "num" : "", neg ? "neg" : "",
                    numeric && v === 0 ? "zero" : ""]
                    .filter(Boolean).join(" ");
                  if (drill && idx === 0) {
                    return (
                      <td key={c.key} className={cls}>
                        <span className="drill-cell" style={{ paddingLeft: row._nivel * 18 }}>
                          {hasChildren(ri) ? (
                            <button type="button" className="drill-toggle" onClick={() => toggleRow(ri)}
                              aria-label={`Expandir ${v}`} aria-expanded={expanded.has(ri)}>
                              <Chevron className="toggle-chev" />
                            </button>
                          ) : (
                            <span className="drill-toggle drill-toggle--empty" />
                          )}
                          {fmt(v, c.format)}
                        </span>
                      </td>
                    );
                  }
                  // Celda corregida por un operador (row._corr: {clave: nota}): fondo + «*» + texto
                  // para lectores de pantalla; Copiar y Excel siguen usando sólo el número.
                  const nota = row._corr?.[c.key];
                  return (
                    <td key={c.key} className={nota ? `${cls} cell-edited` : cls} title={nota}>
                      {fmt(v, c.format)}
                      {nota && <><span className="cell-edited-mark" aria-hidden="true">*</span>
                        <span className="sr-only">{nota}</span></>}
                      {idx === 0 && rowAction?.(row)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
        {totales && (
          <tfoot>
            <tr className="totals-row">
              {cols.map((c, idx) => (
                <td key={c.key} className={`${idx === 0 ? "sticky-col" : ""} ${isNumericFmt(c.format) ? "num" : ""}`}>
                  {idx === 0 ? "TOTAL" : c.key in totales ? fmt(totales[c.key], c.format) : ""}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
      </div>
    </div>
  );
}
