// Copia un resultado tabular al portapapeles como TSV, pegable directo en
// Excel con configuración regional española (decimal con coma, sin miles).

function cell(v, format) {
  if (v === null || v === undefined) return "";
  if (format === "datetime") {
    const d = new Date(v);
    if (isNaN(d)) return String(v);
    const p = (n) => String(n).padStart(2, "0");
    return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }
  if (format && /^0\.0+$/.test(format) && typeof v === "number") {
    return v.toFixed(format.split(".")[1].length).replace(".", ",");
  }
  return String(v).replace(/[\t\r\n]+/g, " ");
}

export async function copyResultTsv(result) {
  const cols = result.columns.filter((c) => !c.hidden);
  const lines = [cols.map((c) => c.label).join("\t")];
  for (const r of result.rows) {
    lines.push(cols.map((c, i) => {
      const v = cell(r[c.key], c.format);
      // Grillas jerárquicas: sangría por nivel en la primera columna.
      return i === 0 && r._nivel ? "    ".repeat(r._nivel) + v : v;
    }).join("\t"));
  }
  const text = lines.join("\r\n");

  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  // Fallback para HTTP plano en la red interna (clipboard API requiere
  // contexto seguro).
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  const ok = document.execCommand("copy");
  ta.remove();
  if (!ok) throw new Error("el navegador bloqueó el acceso al portapapeles");
}
