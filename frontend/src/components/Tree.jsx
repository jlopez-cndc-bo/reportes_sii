import { useEffect, useRef, useState } from "react";
import { nodeState, countLeaves, leafKeysUnder } from "../treeUtils";
import { Chevron } from "../icons";

// ¿El nodo o alguno de sus descendientes coincide con el filtro?
function matches(node, q) {
  if (!q) return true;
  if (node.label && node.label.toLowerCase().includes(q)) return true;
  return (node.children || []).some((c) => matches(c, q));
}

function TreeNodeRow({ node, checked, onToggle, depth, q, bigTree, collapsed, unaRaiz }) {
  // collapsed: todo arranca cerrado (salvo una raíz única). Si no, en árboles
  // grandes sólo las raíces arrancan abiertas y en chicos se expande todo.
  const [open, setOpen] = useState(collapsed ? unaRaiz && depth === 0 : !bigTree || depth === 0);
  const ref = useRef(null);
  const hasChildren = node.children && node.children.length > 0;
  const estado = nodeState(node, checked);
  const selfMatch = q && node.label && node.label.toLowerCase().includes(q);
  const visibleChildren = (node.children || []).filter((c) => matches(c, q));
  const expanded = q ? true : open;
  // Con grupos cerrados, «marcados/total» deja ver la selección guardada.
  const hojas = collapsed && hasChildren ? leafKeysUnder(node) : null;

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = estado === "partial";
  }, [estado]);

  return (
    <div className="tree-node">
      <div className="tree-row" style={{ paddingLeft: depth * 14 }}>
        {hasChildren ? (
          <button type="button" className="tree-toggle" onClick={() => setOpen((o) => !o)}
            aria-label={`Expandir ${node.label}`} aria-expanded={expanded}>
            <Chevron className="toggle-chev" />
          </button>
        ) : (
          <span className="tree-toggle tree-toggle--empty" />
        )}
        <label className="tree-label">
          <input ref={ref} type="checkbox" checked={estado === "on"}
            onChange={() => onToggle(node)} />
          <span
            className={`tree-text tree-text--${node.tipo} ${selfMatch ? "tree-text--hit" : ""} ${node.vigente === false ? "tree-text--novig" : ""}`}
            title={node.vigente === false ? "Fuera de vigencia en el rango de fechas" : undefined}>
            {node.label}
          </span>
          {hojas && <span className="tree-sum">{hojas.filter((k) => checked.has(k)).length}/{hojas.length}</span>}
        </label>
      </div>
      {hasChildren && expanded && (
        <div className="tree-children">
          {visibleChildren.map((c) => (
            <TreeNodeRow key={c.key} node={c} checked={checked} onToggle={onToggle} depth={depth + 1} q={q} bigTree={bigTree} collapsed={collapsed} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function Tree({ nodes, checked, onToggle, filter, collapsed = false }) {
  const q = (filter || "").trim().toLowerCase();
  if (!nodes || nodes.length === 0) {
    return <div className="tree-empty">Sin componentes para el rango seleccionado.</div>;
  }
  const visible = nodes.filter((n) => matches(n, q));
  if (visible.length === 0) {
    return <div className="tree-empty">Ningún componente coincide con «{filter}».</div>;
  }
  const bigTree = countLeaves(nodes) > 400;
  return (
    <div className="tree">
      {visible.map((n) => (
        <TreeNodeRow key={n.key} node={n} checked={checked} onToggle={onToggle} depth={0} q={q} bigTree={bigTree}
          collapsed={collapsed} unaRaiz={nodes.length === 1} />
      ))}
    </div>
  );
}
