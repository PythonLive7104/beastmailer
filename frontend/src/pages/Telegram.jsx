import { useEffect, useState } from "react";
import { api } from "../api";
import { Icon } from "../icons";
import { Field, Loader, Switch, useToast } from "../components/ui";

export default function Telegram() {
  const [cfg, setCfg] = useState(null);
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const toast = useToast();

  useEffect(() => { api.telegram.get().then(setCfg); }, []);

  const save = async () => {
    setBusy(true);
    try {
      const body = { ...cfg };
      delete body.has_token;
      if (token) body.bot_token = token;
      const saved = await api.telegram.update(body);
      setCfg(saved);
      setToken("");
      toast("Telegram settings saved");
    } catch { toast("Save failed", "err"); }
    finally { setBusy(false); }
  };

  const test = async () => {
    setTesting(true);
    try {
      const r = await api.telegram.test(token ? { bot_token: token, chat_id: cfg.chat_id } : {});
      r.ok ? toast("✓ Test message sent — check Telegram") : toast(`Failed: ${r.error}`, "err");
    } catch (e) { toast(`Failed: ${e.detail?.error || "error"}`, "err"); }
    finally { setTesting(false); }
  };

  if (!cfg) return <Loader />;

  return (
    <div className="grid" style={{ maxWidth: 680 }}>
      <div className="card card-pad">
        <div className="between" style={{ marginBottom: 18 }}>
          <div>
            <h3>Telegram notifications</h3>
            <div className="page-sub">Get pinged when replies are sent or a mailbox errors out</div>
          </div>
          <Switch checked={cfg.enabled} onChange={(v) => setCfg({ ...cfg, enabled: v })} />
        </div>

        <Field label={cfg.has_token ? "Bot token (saved — leave blank to keep)" : "Bot token (from @BotFather)"}>
          <input className="input" type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder={cfg.has_token ? "••••••••" : "123456:ABC-DEF…"} />
        </Field>
        <Field label="Chat ID (your @userinfobot value or group ID)">
          <input className="input" value={cfg.chat_id} onChange={(e) => setCfg({ ...cfg, chat_id: e.target.value })} placeholder="123456789" />
        </Field>

        <div style={{ marginTop: 8 }}>
          <div className="page-sub" style={{ marginBottom: 10 }}>Notify me when…</div>
          {[
            ["notify_on_sent", "A reply is sent"],
            ["notify_on_received", "New mail is received"],
            ["notify_on_error", "A mailbox or send fails"],
          ].map(([k, label]) => (
            <div className="row" key={k} style={{ marginBottom: 10 }}>
              <Switch checked={cfg[k]} onChange={(v) => setCfg({ ...cfg, [k]: v })} />
              <span>{label}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="card card-pad">
        <h4 style={{ marginBottom: 8 }}>Setup</h4>
        <ol className="page-sub" style={{ lineHeight: 1.9, paddingLeft: 18 }}>
          <li>Message <b>@BotFather</b> on Telegram → <code>/newbot</code> → copy the token.</li>
          <li>Message your new bot once, then get your chat ID from <b>@userinfobot</b>.</li>
          <li>Paste both above, save, and hit <b>Send test</b>.</li>
        </ol>
      </div>

      <div className="row">
        <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save settings"}</button>
        <button className="btn" onClick={test} disabled={testing}><Icon.telegram /> {testing ? "Sending…" : "Send test"}</button>
      </div>
    </div>
  );
}
