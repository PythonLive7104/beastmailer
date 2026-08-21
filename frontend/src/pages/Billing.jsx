import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, StatusBadge, useToast } from "../components/ui";

function fmtDate(v) {
  return v ? new Date(v).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : "—";
}

export default function Billing() {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ wallet: "", currency: "", tx_reference: "", note: "" });
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  const load = () => api.billing.get().then((d) => {
    setData(d);
    // Default the payment form to the first wallet.
    setForm((f) => ({ ...f, wallet: f.wallet || (d.wallets[0]?.id ?? ""), currency: f.currency || (d.wallets[0]?.currency ?? "") }));
  });
  useEffect(() => { load(); }, []);

  const submit = async () => {
    setBusy(true);
    try {
      await api.billing.pay({ ...form, amount_usd: data.fee_usd });
      toast("Payment submitted — awaiting confirmation");
      setForm({ wallet: data.wallets[0]?.id ?? "", currency: data.wallets[0]?.currency ?? "", tx_reference: "", note: "" });
      load();
    } catch (e) { toast(`Submit failed: ${JSON.stringify(e.detail)}`, "err"); }
    finally { setBusy(false); }
  };

  if (!data) return <Loader />;

  const copy = (text) => { navigator.clipboard?.writeText(text); toast("Copied"); };

  // Nothing to pay for when the paywall is off or the user is exempt.
  if (!data.enabled || data.exempt) {
    return (
      <div className="grid">
        <div className="card card-pad">
          <div className="row" style={{ gap: 10 }}>
            <span className="badge badge-sent">Active</span>
            <b>{data.exempt ? "Your account is exempt from billing." : "Subscriptions are currently disabled — the service is free."}</b>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="grid">
      {/* Status */}
      <div className="card card-pad">
        <div className="between">
          <div>
            <div className="page-sub">Subscription status</div>
            <h2 style={{ margin: "4px 0" }}>
              {data.active
                ? <span style={{ color: "var(--success)" }}>Active</span>
                : <span style={{ color: "var(--danger)" }}>Not active</span>}
            </h2>
            <div className="muted">
              {data.active
                ? <>Access until <b>{fmtDate(data.expires_at)}</b>.</>
                : <>Auto-replies are paused until a payment is confirmed.</>}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="page-sub">Monthly fee</div>
            <h2 style={{ margin: "4px 0" }}>${data.fee_usd}</h2>
            <div className="muted">{data.period_days} days per payment</div>
          </div>
        </div>
      </div>

      {!data.active && (
        <div className="card card-pad" style={{ borderColor: "var(--warning)" }}>
          <b>How to activate</b>
          <div className="muted" style={{ marginTop: 6 }}>
            Send <b>${data.fee_usd}</b> to one of the wallets below, then submit the transaction
            reference. The superuser confirms it and your access begins.
          </div>
          {data.instructions && <div className="muted" style={{ marginTop: 8, whiteSpace: "pre-wrap" }}>{data.instructions}</div>}
        </div>
      )}

      {/* Wallets */}
      <div className="card">
        <div className="card-pad"><h3>Payment wallets</h3></div>
        <div style={{ overflowX: "auto" }}>
          <table className="table">
            <thead><tr><th>Wallet</th><th>Network</th><th>Address</th><th></th></tr></thead>
            <tbody>
              {data.wallets.map((w) => (
                <tr key={w.id}>
                  <td className="subj">{w.label} <span className="muted">({w.currency})</span></td>
                  <td className="muted">{w.network || "—"}</td>
                  <td className="mono" style={{ overflowWrap: "anywhere" }}>{w.address}{w.memo && <div className="muted">memo: {w.memo}</div>}</td>
                  <td><button className="btn btn-sm" onClick={() => copy(w.address)}><Icon.copy /> Copy</button></td>
                </tr>
              ))}
              {data.wallets.length === 0 && <tr><td colSpan={4}><div className="empty">No wallets configured yet. Ask the admin to add one.</div></td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Submit payment */}
      {data.wallets.length > 0 && (
        <div className="card card-pad">
          <h3 style={{ marginBottom: 12 }}>I've paid — submit for confirmation</h3>
          <div className="field-row">
            <Field label="Wallet paid to">
              <select className="input" value={form.wallet}
                onChange={(e) => {
                  const w = data.wallets.find((x) => String(x.id) === e.target.value);
                  setForm({ ...form, wallet: e.target.value, currency: w?.currency ?? form.currency });
                }}>
                {data.wallets.map((w) => <option key={w.id} value={w.id}>{w.label} ({w.currency})</option>)}
              </select>
            </Field>
            <Field label="Currency sent"><input className="input" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} /></Field>
          </div>
          <Field label="Transaction hash / reference">
            <input className="input" value={form.tx_reference} onChange={(e) => setForm({ ...form, tx_reference: e.target.value })} placeholder="0x… or txid" />
          </Field>
          <Field label="Note (optional)">
            <input className="input" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="Anything the reviewer should know" />
          </Field>
          <div className="row" style={{ justifyContent: "flex-end", marginTop: 4 }}>
            <button className="btn btn-primary" onClick={submit} disabled={busy}>{busy ? "Submitting…" : `Submit $${data.fee_usd} payment`}</button>
          </div>
        </div>
      )}

      {/* History */}
      <div className="card">
        <div className="card-pad"><h3>Payment history</h3></div>
        <div style={{ overflowX: "auto" }}>
          <table className="table">
            <thead><tr><th>Submitted</th><th>Amount</th><th>Reference</th><th>Status</th><th>Access until</th></tr></thead>
            <tbody>
              {data.payments.map((p) => (
                <tr key={p.id}>
                  <td className="mono">{fmtDate(p.created_at)}</td>
                  <td>${p.amount_usd} {p.currency}</td>
                  <td className="mono" style={{ overflowWrap: "anywhere" }}>{p.tx_reference || "—"}</td>
                  <td><StatusBadge status={p.status} /></td>
                  <td className="mono">{fmtDate(p.period_end)}</td>
                </tr>
              ))}
              {data.payments.length === 0 && <tr><td colSpan={5}><div className="empty">No payments yet.</div></td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
