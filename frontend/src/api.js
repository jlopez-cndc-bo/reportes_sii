// Cliente HTTP mínimo hacia el backend FastAPI.

async function post(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Error ${res.status}`;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

// Descarga un .xlsx generado por el backend.
async function download(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Error ${res.status}`;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  const filename = m ? decodeURIComponent(m[1]) : "reporte.xlsx";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const api = {
  health: () => fetch("/health").then((r) => r.json()),
  // Indisponibilidades
  arbol: (body) => post("/api/arbol", body),
  reporte: (endpoint, body) => post(`/api/reportes/${endpoint}`, body),
  exportar: (endpoint, body) => download(`/api/exportar/${endpoint}`, body),
  // SMEC
  smecEstructura: () => fetch("/api/smec/estructura").then((r) => r.json()),
  smecReporte: (body) => post("/api/smec/reporte", body),
  smecExportar: (body) => download("/api/smec/exportar", body),
  smecExportarConjunto: (body) => download("/api/smec/exportar-conjunto", body),
  // Sisfalla
  sisfallaReporte: (endpoint, body) => post(`/api/sisfalla/reportes/${endpoint}`, body),
  sisfallaReporteGet: (endpoint) => fetch(`/api/sisfalla/reportes/${endpoint}`).then((r) => r.json()),
  sisfallaExportar: (endpoint, body) => download(`/api/sisfalla/exportar/${endpoint}`, body),
  sisfallaBuscarFallas: (q, limite = 30) =>
    fetch(`/api/sisfalla/fallas/buscar?${new URLSearchParams({ q: q || "", limite })}`).then((r) => r.json()),
};
