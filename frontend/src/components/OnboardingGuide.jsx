import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon } from "../icons";

// The full A-to-Z of BeastMailer. Each step maps to a real page so the user can
// jump straight there. Order mirrors the natural setup flow.
const STEPS = [
  {
    icon: "sparkle",
    title: "Welcome to BeastMailer",
    lead: "Auto-reply to incoming mail, on autopilot.",
    body: "BeastMailer watches your mailboxes and sends automatic replies based on subject-matching rules — so one person can manage many inboxes from a single dashboard. This quick tour walks you through setup from start to finish. You can replay it any time from Settings.",
  },
  {
    icon: "mailbox",
    title: "1. Connect a mailbox",
    lead: "Add an email account to watch.",
    body: "On the Mailbox page, add an account with its IMAP (incoming) and SMTP (outgoing) details, then hit Test to confirm the connection. Passwords are encrypted at rest. You can add as many mailboxes as you like.",
    to: "/mailboxes",
    cta: "Open Mailbox",
  },
  {
    icon: "placeholders",
    title: "2. Create placeholders (optional)",
    lead: "Reusable variables for your replies.",
    body: "Placeholders like {{first_name}} or {{company}} let you personalise replies without rewriting each template. Define them once and reuse everywhere.",
    to: "/placeholders",
    cta: "Open Placeholders",
  },
  {
    icon: "reply",
    title: "3. Write a reply template",
    lead: "The message that gets sent back.",
    body: "On the Auto-reply page, craft the templates BeastMailer sends. Drop in your placeholders, and optionally attach files or tracked links. These are the bodies your rules will send.",
    to: "/auto-reply",
    cta: "Open Auto-reply",
  },
  {
    icon: "rules",
    title: "4. Define your rules",
    lead: "Match a subject → pick a template.",
    body: "Rules are the brain. Each rule matches incoming subjects (contains / equals / regex), picks a reply template, and sets a delay before sending. Incoming mail that matches gets a reply scheduled automatically.",
    to: "/rules",
    cta: "Open Rules",
  },
  {
    icon: "config",
    title: "5. Configure the engine",
    lead: "Poll interval & send timing.",
    body: "The Configuration page controls how often mailboxes are polled and the default delays before replies go out. Sensible defaults are set for you — tune them when you're ready.",
    to: "/configuration",
    cta: "Open Configuration",
  },
  {
    icon: "attachments",
    title: "6. Attachments & links",
    lead: "Add files and trackable links.",
    body: "Upload reusable files to attach to replies, and create tracked links that count clicks — handy for measuring engagement from your auto-replies.",
    to: "/attachments",
    cta: "Open Attachments",
  },
  {
    icon: "listeners",
    title: "7. Watch it work",
    lead: "Live status & activity feed.",
    body: "The Listeners page shows each mailbox's polling status and a live feed of received mail. The Dashboard rolls up sent / scheduled / received stats so you can see the engine working in real time.",
    to: "/listeners",
    cta: "Open Listeners",
  },
  {
    icon: "team",
    title: "8. Invite your team",
    lead: "Share a workspace.",
    body: "All your data lives in a workspace. Invite teammates by username or email and they'll see and manage the same mailboxes, rules and templates. Switch between workspaces from the top bar.",
    to: "/team",
    cta: "Open Team",
  },
  {
    icon: "telegram",
    title: "9. Get notified (optional)",
    lead: "Telegram alerts.",
    body: "Connect a Telegram bot to get pinged when mail is received, replies are sent, or errors occur — so you don't have to keep the dashboard open.",
    to: "/telegram",
    cta: "Open Telegram",
  },
  {
    icon: "security",
    title: "10. Stay secure",
    lead: "Encryption & your password.",
    body: "The Security page shows your encryption posture and audit log, and lets you change your password. Manage your personal details and account under Settings.",
    to: "/security",
    cta: "Open Security",
  },
  {
    icon: "check",
    title: "You're all set!",
    lead: "That's the whole flow, A to Z.",
    body: "Connect a mailbox, add templates and rules, and BeastMailer handles the rest. You can reopen this guide any time from Settings → Setup guide. Happy automating!",
  },
];

export default function OnboardingGuide({ open, onClose }) {
  const [step, setStep] = useState(0);
  const nav = useNavigate();

  // Always restart from the top each time the guide is opened.
  useEffect(() => { if (open) setStep(0); }, [open]);

  if (!open) return null;

  const s = STEPS[step];
  const IconCmp = Icon[s.icon] || Icon.sparkle;
  const isFirst = step === 0;
  const isLast = step === STEPS.length - 1;

  const goTo = (path) => { onClose(); nav(path); };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal onboard" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 560 }}>
        <div className="modal-head between">
          <span className="page-sub">Setup guide · Step {step + 1} of {STEPS.length}</span>
          <button className="btn btn-ghost btn-sm" onClick={onClose} title="Skip">Skip ✕</button>
        </div>

        <div className="modal-body" style={{ textAlign: "center", paddingTop: 8 }}>
          <div className="brand-logo" style={{ width: 56, height: 56, borderRadius: 16, margin: "6px auto 16px" }}>
            <IconCmp />
          </div>
          <h2 style={{ margin: "0 0 4px" }}>{s.title}</h2>
          <div className="page-sub" style={{ marginBottom: 14 }}>{s.lead}</div>
          <p style={{ color: "var(--text-muted, #94a3b8)", lineHeight: 1.6, maxWidth: 440, margin: "0 auto" }}>{s.body}</p>

          {s.to && (
            <button className="btn btn-ghost btn-sm" style={{ marginTop: 16 }} onClick={() => goTo(s.to)}>
              {s.cta || "Take me there"} <Icon.arrowRight style={{ width: 15, height: 15 }} />
            </button>
          )}

          <div className="onboard-dots" style={{ display: "flex", gap: 6, justifyContent: "center", marginTop: 20 }}>
            {STEPS.map((_, i) => (
              <span
                key={i}
                onClick={() => setStep(i)}
                title={`Step ${i + 1}`}
                style={{
                  width: i === step ? 20 : 8, height: 8, borderRadius: 4, cursor: "pointer",
                  background: i === step ? "var(--accent, #7c5cff)" : "var(--border, #33415588)",
                  transition: "all .2s",
                }}
              />
            ))}
          </div>
        </div>

        <div className="modal-foot between">
          <button className="btn btn-ghost" onClick={() => setStep((n) => Math.max(0, n - 1))} disabled={isFirst}>
            <Icon.arrowLeft style={{ width: 15, height: 15 }} /> Back
          </button>
          {isLast ? (
            <button className="btn btn-primary" onClick={onClose}>
              <Icon.check style={{ width: 16, height: 16 }} /> Finish
            </button>
          ) : (
            <button className="btn btn-primary" onClick={() => setStep((n) => Math.min(STEPS.length - 1, n + 1))}>
              Next <Icon.arrowRight style={{ width: 15, height: 15 }} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
