import { useId, useRef } from "react";
import { useDialog } from "../useDialog";

// Confirmación propia (nunca confirm()): Escape o «cancelar» vuelven atrás; el clic
// en el fondo no cierra, para no perder una decisión por un clic accidental.
export default function ConfirmDialog({ titulo, children, confirmar, cancelar = "Volver", onConfirm, onCancel }) {
  const cancelRef = useRef(null);
  const ref = useDialog(onCancel, cancelRef);
  const titleId = useId();
  return (
    <div className="modal-overlay">
      <div ref={ref} className="modal" role="alertdialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="modal-head"><h2 id={titleId}>{titulo}</h2></div>
        <div className="modal-body">{children}</div>
        <div className="modal-foot">
          <span />
          <div className="acciones">
            <button ref={cancelRef} type="button" className="btn" onClick={onCancel}>{cancelar}</button>
            <button type="button" className="btn btn--primary" onClick={onConfirm}>{confirmar}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
