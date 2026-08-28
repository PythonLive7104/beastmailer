import { useEffect, useState } from "react";
import { api } from "../api";
import { Field, Loader, PageIntro, Switch, useToast } from "../components/ui";

export default function Configuration() {
  const [cfg, setCfg] = useState(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();

  useEffect(() => { api.config.get().then(setCfg); }, []);

  const save = async () => {
    setBusy(true);
    try {
      const saved = await api.config.update(cfg);
      setCfg(saved);
      toast("Configuration saved");
    } catch { toast("Save failed", "err"); }
    finally { setBusy(false); }
  };

  if (!cfg) return <Loader />;

  return (
    <div className="grid" style={{ maxWidth: 680 }}>
      <PageIntro id="configuration" lead="The overall settings for automatic replying — how often the app checks for new mail, how long it waits before answering, and the signature added to the bottom of every reply. Individual accounts can override the timings on the Mailboxes page." />
      <div className="card card-pad">
        <div className="between" style={{ marginBottom: 18 }}>
          <div>
            <h3>Auto-reply</h3>
            <div className="page-sub">Master switch for automatic replies</div>
          </div>
          <Switch checked={cfg.auto_reply_enabled} onChange={(v) => setCfg({ ...cfg, auto_reply_enabled: v })} />
        </div>
        <div className="field-row">
          <Field label="Reply delay (minutes)">
            <input className="input" type="number" min="0" value={cfg.reply_delay_minutes}
              onChange={(e) => setCfg({ ...cfg, reply_delay_minutes: Number(e.target.value) })} />
          </Field>
          <Field label="Poll interval (seconds)">
            <input className="input" type="number" min="5" value={cfg.poll_interval_seconds}
              onChange={(e) => setCfg({ ...cfg, poll_interval_seconds: Number(e.target.value) })} />
          </Field>
        </div>
        <Field label="Signature (appended to every auto-reply)">
          <textarea className="textarea" value={cfg.signature} onChange={(e) => setCfg({ ...cfg, signature: e.target.value })}
            placeholder="— Sent automatically by BeastMailer Auto-Reply" />
        </Field>
      </div>

      <div className="card card-pad">
        <h3 style={{ marginBottom: 8 }}>How it works</h3>
        <ol className="page-sub" style={{ lineHeight: 1.9, paddingLeft: 18 }}>
          <li>Every <b>{cfg.poll_interval_seconds}s</b> the app checks each active mailbox over IMAP.</li>
          <li>New mail is matched against your active <b>Rules</b> by subject.</li>
          <li>On a match, a reply is drafted from the template and scheduled.</li>
          <li>After the <b>{cfg.reply_delay_minutes}-minute</b> delay, the reply is sent.</li>
          <li>Replies are threaded back to the original sent email by subject.</li>
        </ol>
      </div>

      <div className="row">
        <button className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save configuration"}</button>
      </div>
    </div>
  );
}
