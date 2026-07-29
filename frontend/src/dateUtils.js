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
    { label: "7 días", ini: isoDaysAgo(7), fin: hoy },
    { label: "30 días", ini: isoDaysAgo(30), fin: hoy },
    { label: "Mes actual", ini: mesIni, fin: hoy },
    { label: "Mes anterior", ini: mesAntIni, fin: mesAntFin },
  ];
}
