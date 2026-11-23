// Cliente HTTP mínimo hacia el backend FastAPI.

// El error lleva `status` para distinguir, p. ej., la sesión vencida (401).
async function send(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `Error ${res.status}`;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch { /* sin JSON: queda el "Error <status>" */ }
    throw Object.assign(new Error(detail), { status: res.status });
  }
  return res.json();
}

const post = (path, body) => send("POST", path, body);

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
    } catch { /* sin JSON: queda el "Error <status>" */ }
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
  // SCADA HFD
  hfdRegistros: (body) => post("/api/hfd/registros", body),
  hfdExportar: (body) => download("/api/hfd/exportar", body),
  hfdConsolidado: (id, body) => post(`/api/hfd/consolidados/${id}`, body),
  hfdConsolidadoExportar: (id, body) => download(`/api/hfd/consolidados/${id}/exportar`, body),
  // Correcciones HFD (operadores SCADA): sesión por cookie HttpOnly
  hfdSesion: () => send("GET", "/api/hfd/sesion"),
  hfdLogin: (usuario, password) => post("/api/hfd/sesion", { usuario, password }),
  hfdLogout: () => send("DELETE", "/api/hfd/sesion"),
  hfdPropuestaSmec: (idObj, fecha) =>
    send("GET", `/api/hfd/correcciones/propuesta-smec?${new URLSearchParams({ id_obj: idObj, fecha })}`),
  hfdGuardarCorrecciones: (body) => post("/api/hfd/correcciones", body),
  hfdRecargarUrl: (fecha) => `/api/hfd/correcciones/recargar?${new URLSearchParams({ fecha })}`,
};
