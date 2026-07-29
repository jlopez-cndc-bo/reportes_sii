// Utilidades compartidas para el árbol de componentes (Indisp y SMEC).

export function collectIds(nodes, checked, tipo, acc = []) {
  for (const n of nodes) {
    if (n.tipo === tipo && checked.has(n.key) && n.id_objeto != null) acc.push(n.id_objeto);
    if (n.children) collectIds(n.children, checked, tipo, acc);
  }
  return acc;
}

export function descendantKeys(node, acc = []) {
  acc.push(node.key);
  if (node.children) node.children.forEach((c) => descendantKeys(c, acc));
  return acc;
}

export function allKeys(nodes, acc = []) {
  for (const n of nodes) {
    acc.push(n.key);
    if (n.children) allKeys(n.children, acc);
  }
  return acc;
}

// Claves de las hojas bajo un nodo (para el estado tri-state).
export function leafKeysUnder(node, acc = []) {
  if (!node.children || node.children.length === 0) {
    acc.push(node.key);
  } else {
    node.children.forEach((c) => leafKeysUnder(c, acc));
  }
  return acc;
}

// Estado visual de un nodo derivado de sus hojas: "on" | "off" | "partial".
export function nodeState(node, checked) {
  const lk = leafKeysUnder(node);
  const on = lk.filter((k) => checked.has(k)).length;
  if (on === 0) return "off";
  if (on === lk.length) return "on";
  return "partial";
}

// Poda el árbol dejando sólo las hojas que cumplen pred (y los padres con
// al menos una hoja visible). Los nodos devueltos son copias superficiales.
export function pruneTree(nodes, pred) {
  const out = [];
  for (const n of nodes) {
    if (!n.children || n.children.length === 0) {
      if (pred(n)) out.push(n);
    } else {
      const children = pruneTree(n.children, pred);
      if (children.length > 0) out.push({ ...n, children });
    }
  }
  return out;
}

// Cuenta las hojas del árbol que cumplen pred (pred omitido = todas).
export function countLeaves(nodes, pred) {
  let c = 0;
  for (const n of nodes) {
    if (!n.children || n.children.length === 0) {
      if (!pred || pred(n)) c++;
    } else {
      c += countLeaves(n.children, pred);
    }
  }
  return c;
}

// Toggle de un nodo y toda su rama (padre + descendientes).
// Si todas las hojas estaban marcadas → desmarca la rama; si no → la marca.
export function toggleNode(prev, node) {
  const rama = descendantKeys(node);
  const hojas = leafKeysUnder(node);
  const todasOn = hojas.every((k) => prev.has(k));
  const next = new Set(prev);
  rama.forEach((k) => (todasOn ? next.delete(k) : next.add(k)));
  return next;
}
