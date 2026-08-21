import { createContext, useCallback, useContext, useState } from "react";

// ---- Toast ----
const ToastCtx = createContext(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null);
  const show = useCallback((message, kind = "ok") => {
    setToast({ message, kind });
    setTimeout(() => setToast(null), 3200);
  }, []);
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast && <div className={`toast ${toast.kind === "err" ? "err" : ""}`}>{toast.message}</div>}
    </ToastCtx.Provider>
  );
}

// ---- Modal ----
export function Modal({ title, onClose, children, footer, wide }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className={`modal${wide ? " modal-wide" : ""}`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head between">
          <h3>{title}</h3>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

// ---- Switch ----
export function Switch({ checked, onChange }) {
  return (
    <label className="switch">
      <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="slider" />
    </label>
  );
}

// ---- Badge ----
export function StatusBadge({ status }) {
  const map = { sent: "badge-sent", received: "badge-received", scheduled: "badge-scheduled", failed: "badge-failed", confirmed: "badge-sent", pending: "badge-scheduled", rejected: "badge-failed" };
  return <span className={`badge ${map[status] || "badge-neutral"}`}>{status}</span>;
}

export function Loader({ label = "Loading…" }) {
  return <div className="loader">{label}</div>;
}

export function Field({ label, children }) {
  return (
    <div className="field">
      {label && <label>{label}</label>}
      {children}
    </div>
  );
}
