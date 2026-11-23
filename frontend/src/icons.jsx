// Íconos de la app: SVG en currentColor, trazo 1.6, decorativos (el nombre
// accesible lo pone el botón que los contiene).
const base = {
  fill: "none", stroke: "currentColor", strokeWidth: 1.6,
  strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true,
};

// Doble chevron de los paneles comprimibles.
export function Chevrons({ dir }) {
  const d = dir === "left"
    ? "M8 3.5L3.5 8 8 12.5M12.5 3.5L8 8l4.5 4.5"
    : "M8 3.5L12.5 8 8 12.5M3.5 3.5L8 8l-4.5 4.5";
  return <svg width="16" height="16" viewBox="0 0 16 16" {...base}><path d={d} /></svg>;
}

// Chevron simple apuntando a la derecha; se rota por CSS (expandir) o por `dir`.
const ROT = { right: 0, down: 90, left: 180, up: 270 };
export function Chevron({ size = 12, dir = "right", className }) {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" className={className}
      style={ROT[dir] ? { transform: `rotate(${ROT[dir]}deg)` } : undefined} {...base}>
      <path d="M4.5 2.5L8 6 4.5 9.5" />
    </svg>
  );
}

export function Refresh({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" {...base}>
      <path d="M11.5 7a4.5 4.5 0 11-1.3-3.2M11.5 2v2.8H8.7" />
    </svg>
  );
}

// Ayuda: signo de pregunta dentro de un círculo.
export function Help({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" {...base}>
      <circle cx="8" cy="8" r="6.2" />
      <path d="M6.2 6.3a1.9 1.9 0 113 1.5c-.7.4-1.2.8-1.2 1.6" />
      <path d="M8 11.4v.1" />
    </svg>
  );
}

export function Close({ size = 14 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 14 14" {...base}>
      <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" />
    </svg>
  );
}
