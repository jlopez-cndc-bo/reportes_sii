import { useId, useRef, useState } from "react";
import { api } from "../api";
import { useDialog } from "../useDialog";
import { Close } from "../icons";

// Login de editores de correcciones HFD (usuario del dominio CNDC, validado en AD).
// Los reportes siguen sin sesión: esto sólo habilita corregir valores.
export default function HfdLoginDialog({ onClose, onOk }) {
  const [usuario, setUsuario] = useState("");
  const [password, setPassword] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState(null);
  const userRef = useRef(null);
  const ref = useDialog(onClose, userRef);
  const titleId = useId();

  const enviar = async (e) => {
    e.preventDefault();
    if (enviando) return;
    setEnviando(true); setError(null);
    try {
      const r = await api.hfdLogin(usuario, password);
      onOk(r.usuario);
    } catch (err) {
      setError(err.message);
      setPassword("");  // el usuario se conserva; sólo se borra la contraseña
    } finally { setEnviando(false); }
  };

  return (
    <div className="modal-overlay">
      <div ref={ref} className="modal" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="modal-head">
          <h2 id={titleId}>Iniciar sesión para corregir</h2>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Cerrar"><Close /></button>
        </div>
        <form className="modal-body" onSubmit={enviar}>
          <p>La sesión sólo habilita corregir valores del HFD; los reportes no la necesitan.</p>
          {error && <div className="error-box" role="alert">{error}</div>}
          <label className="dfield"><span>Usuario del dominio CNDC</span>
            <input ref={userRef} autoComplete="username" value={usuario} required
              onChange={(e) => setUsuario(e.target.value)} />
          </label>
          <label className="dfield dfield--sep"><span>Contraseña</span>
            <input type="password" autoComplete="current-password" value={password} required
              onChange={(e) => setPassword(e.target.value)} />
          </label>
          <div className="form-acciones">
            <button type="button" className="btn" onClick={onClose}>Cancelar</button>
            <button type="submit" className="btn btn--primary" disabled={enviando}>
              {enviando ? "Verificando…" : "Iniciar sesión"}</button>
          </div>
        </form>
      </div>
    </div>
  );
}
