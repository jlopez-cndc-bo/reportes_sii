// Informe de Mediano Plazo: genera los anexos (.xlsx) desde los archivos de cada estudio.
// No consulta Oracle ni escribe en el servidor: sólo descarga lo generado.
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { Rail } from "../shell";
import { Refresh } from "../icons";

const PENDIENTE_3 = { anexo: 3, contenido: "Energía y potencia histórica y proyectada (requiere la base IMP)" };

function Archivos({ faltan }) {
  if (!faltan.length) return <span><span aria-hidden="true">✓ </span>Completo</span>;
  return (
    <span className="imp-falta">
      Falta {faltan.length === 1 ? "1 archivo" : `${faltan.length} archivos`}: {faltan.join(" · ")}
    </span>
  );
}

export default function ImpModule() {
  const [estudios, setEstudios] = useState(null);
  const [error, setError] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [sel, setSel] = useState("");
  const [generando, setGenerando] = useState(null);
  const [porAnexo, setPorAnexo] = useState({}); // anexo → { error } | { avisos }

  const cargar = useCallback(() => {
    setCargando(true);
    api.impEstudios()
      .then((d) => {
        setEstudios(d);
        setError(null);
        // Siempre el más reciente salvo que el elegido siga existiendo.
        setSel((s) => (d.some((e) => e.id === s) ? s : d[0]?.id || ""));
      })
      .catch((e) => setError(e.message))
      .finally(() => setCargando(false));
  }, []);

  useEffect(() => { cargar(); }, [cargar]);

  const estudio = estudios?.find((e) => e.id === sel);

  const descargar = async (n) => {
    setGenerando(n);
    setPorAnexo((p) => ({ ...p, [n]: null }));
    try {
      const avisos = await api.impAnexo({ estudio: sel, anexo: n });
      setPorAnexo((p) => ({ ...p, [n]: { avisos: avisos ? avisos.split(" | ") : [] } }));
    } catch (e) {
      setPorAnexo((p) => ({ ...p, [n]: { error: e.message } }));
    } finally {
      setGenerando(null);
    }
  };

  const filas = estudio ? [...estudio.anexos, PENDIENTE_3].sort((a, b) => a.anexo - b.anexo) : [];

  return (
    <div className="layout">
      <Rail grupos={[]} reports={[]} activeId={null} onPick={() => {}} />
      <main className="content imp-content">
        <h1 className="mon-titulo">Informe de Mediano Plazo{estudio ? ` ${estudio.periodo}` : ""}</h1>
        <div className="imp-barra">
          <label className="imp-estudio">
            Estudio
            <select value={sel} disabled={!estudios?.length} onChange={(e) => { setSel(e.target.value); setPorAnexo({}); }}>
              {!estudios && <option value="">Cargando estudios…</option>}
              {estudios?.map((e) => <option key={e.id} value={e.id}>{e.periodo} ({e.id})</option>)}
            </select>
          </label>
          <button type="button" className="pill-btn" onClick={cargar} disabled={cargando}>
            <Refresh /> Actualizar
          </button>
          <span className="mon-meta">Vuelve a revisar los archivos de la carpeta del estudio.</span>
        </div>

        {error && <div className="error-box" role="alert">{error}</div>}
        {!estudios && !error && <div className="results-state"><span className="spinner" /> Cargando estudios…</div>}
        {estudios && !estudios.length && (
          <div className="results-state results-state--muted">
            No hay estudios. Cada estudio es una carpeta AAAA-MM (mes 05 u 11) en el directorio IMP del servidor.
          </div>
        )}

        {estudio && (
          <div className="imp-scroll">
            <table className="results-table imp-tabla">
              <thead>
                <tr>
                  <th scope="col">Anexo</th>
                  <th scope="col">Contenido</th>
                  <th scope="col">Archivos de entrada</th>
                  <th scope="col"><span className="sr-only">Descarga</span></th>
                </tr>
              </thead>
              <tbody>
                {filas.map((a) => {
                  const r = porAnexo[a.anexo];
                  const pendiente = a.anexo === 3;
                  const avisos = [...(a.avisos || []), ...(r?.avisos || [])];
                  return (
                    <tr key={a.anexo}>
                      <th scope="row">Anexo {a.anexo}</th>
                      <td>
                        {a.contenido}
                        {avisos.map((t) => <div key={t} className="imp-aviso">{t}</div>)}
                        {r?.error && <div className="error-box imp-error" role="alert">Anexo {a.anexo}: {r.error}</div>}
                      </td>
                      <td>{pendiente ? <span className="imp-pendiente">Pendiente</span> : <Archivos faltan={a.faltan} />}</td>
                      <td>
                        {!pendiente && (
                          <button type="button" className="btn" disabled={a.faltan.length > 0 || generando === a.anexo}
                            onClick={() => descargar(a.anexo)}>
                            {generando === a.anexo ? "Generando…" : `Descargar ANEXO${a.anexo}.xlsx`}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
