import { useEffect, useRef } from "react";

const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), select, textarea, a[href], [tabindex]:not([tabindex="-1"])';

// Diálogo modal accesible: enfoca el primer control (o `initialFocus`), atrapa
// Tab dentro del diálogo, cierra con Escape y devuelve el foco al cerrar.
// onClose se lee por ref: los padres lo pasan en línea y no debe re-disparar
// el efecto (re-enfocaría en cada render).
export function useDialog(onClose, initialFocus) {
  const ref = useRef(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const previo = document.activeElement;
    const dlg = ref.current;
    (initialFocus?.current || dlg?.querySelector(FOCUSABLE))?.focus();

    const onKey = (e) => {
      if (e.key === "Escape") { e.stopPropagation(); onCloseRef.current(); return; }
      if (e.key !== "Tab" || !dlg) return;
      // Se recalcula en cada Tab: el contenido (p. ej. resultados) cambia.
      const items = [...dlg.querySelectorAll(FOCUSABLE)];
      if (items.length === 0) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previo?.focus?.();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return ref;
}
