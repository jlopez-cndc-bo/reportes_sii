// Fechas en hora LOCAL (toISOString usa UTC y después de las 20:00 en
// Bolivia devolvería la fecha de mañana).

export function isoLocal(d) {
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function isoDaysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return isoLocal(d);
}

// Rangos rápidos [inicio, fin] para los presets de fecha.
export function rangosRapidos() {
  const now = new Date();
  const hoy = isoLocal(now);
  const ayer = isoDaysAgo(1);
  const mesIni = isoLocal(new Date(now.getFullYear(), now.getMonth(), 1));
  const mesAntIni = isoLocal(new Date(now.getFullYear(), now.getMonth() - 1, 1));
  const mesAntFin = isoLocal(new Date(now.getFullYear(), now.getMonth(), 0));
  return [
    { label: "Hoy", ini: hoy, fin: hoy },
    { label: "Ayer", ini: ayer, fin: ayer },
    // Últimos N días contando hoy (7 d = hoy y los 6 anteriores).
    { label: "7 d", ini: isoDaysAgo(6), fin: hoy },
    { label: "30 d", ini: isoDaysAgo(29), fin: hoy },
    { label: "Mes", ini: mesIni, fin: hoy },
    { label: "Mes ant.", ini: mesAntIni, fin: mesAntFin },
  ];
}
