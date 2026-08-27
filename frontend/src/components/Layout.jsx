import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Icon } from "../icons";
import { useTheme } from "../theme";
import { useAuth } from "../auth";
import WorkspaceSwitcher from "./WorkspaceSwitcher";
import OnboardingGuide from "./OnboardingGuide";

const NAV = [
  { section: "Main", items: [["/", "Dashboard", "dashboard", true]] },
  // Sending infrastructure sits above both features because both depend on it:
  // a mailbox polls for auto-reply *and* sends campaigns, and a sending route
  // carries campaigns *and* auto-reply overflow. Filing either under one feature
  // would misrepresent what it belongs to.
  {
    section: "Sending",
    items: [
      ["/mailboxes", "Mailboxes", "mailbox"],
      ["/senders", "Sending routes", "tower"],
    ],
  },
  {
    section: "Campaigns",
    items: [
      ["/campaigns", "Campaigns", "megaphone"],
      ["/audience", "Audience", "audience"],
    ],
  },
  {
    section: "Automation",
    items: [
      ["/auto-reply", "Auto-reply", "reply"],
      ["/rules", "Rules", "rules"],
      ["/configuration", "Configuration", "config"],
      ["/listeners", "Listeners", "listeners"],
    ],
  },
  {
    section: "Tools",
    items: [
      ["/placeholders", "Placeholders", "placeholders"],
      ["/links", "Links", "links"],
      ["/attachments", "Attachments", "attachments"],
      ["/proxies", "Proxies", "proxy"],
    ],
  },
  {
    section: "System",
    items: [
      ["/team", "Team", "team"],
      ["/billing", "Subscription", "bolt"],
      ["/security", "Security", "security"],
      ["/telegram", "Telegram", "telegram"],
      ["/settings", "Settings", "settings"],
    ],
  },
];

const TITLES = {
  "/": ["Dashboard", "How your email has been doing today"],
  "/campaigns": ["Campaigns", "Send one email to a whole list of people"],
  "/audience": ["Audience", "The people your campaigns go to"],
  "/senders": ["Sending routes", "The ways this app can send your email"],
  "/mailboxes": ["Mailboxes", "The email accounts this app signs into"],
  "/auto-reply": ["Auto-reply", "The ready-made replies sent on your behalf"],
  "/rules": ["Rules", "Decides which reply each email gets"],
  "/configuration": ["Configuration", "Timing and signature for automatic replies"],
  "/listeners": ["Listeners", "Check that mail is arriving as it should"],
  "/placeholders": ["Placeholders", "Your own reusable snippets of text"],
  "/team": ["Team", "People who share this workspace with you"],
  "/billing": ["Subscription", "Your plan & payments"],
  "/links": ["Links", "Links you can add to emails, with click counts"],
  "/attachments": ["Attachments", "Files to send along with a reply"],
  "/proxies": ["Proxies", "Optional — send through different connections"],
  "/security": ["Security", "Account history and your password"],
  "/telegram": ["Telegram", "Get alerts on your phone via Telegram"],
  "/settings": ["Settings", "Your account & app preferences"],
};

export default function Layout() {
  const { theme, toggle } = useTheme();
  const { user, logout, completeOnboarding } = useAuth();
  const nav = useNavigate();
  const { pathname } = useLocation();
  const [title, sub] = TITLES[pathname] || ["BeastMailer Auto-Reply", ""];
  const [navOpen, setNavOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => { setNavOpen(false); }, [pathname]);

  // Auto-open the setup guide on first login (until it's completed or skipped).
  useEffect(() => {
    if (user && !user.onboarding_completed) setGuideOpen(true);
  }, [user?.id, user?.onboarding_completed]);

  // Closing the guide (Finish or Skip) marks it seen so it won't reopen next login.
  const closeGuide = () => {
    setGuideOpen(false);
    if (user && !user.onboarding_completed) completeOnboarding();
  };

  const handleLogout = async () => { await logout(); nav("/login"); };

  return (
    <div className="app">
      <div className={`nav-backdrop ${navOpen ? "show" : ""}`} onClick={() => setNavOpen(false)} />
      <aside className={`sidebar ${navOpen ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-logo"><Icon.mailbox /></div>
          <div>
            <div className="brand-name">BeastMailer <span className="nowrap">Auto-Reply</span></div>
            <div className="brand-sub">Admin Panel</div>
          </div>
          <button className="btn icon-btn nav-close" onClick={() => setNavOpen(false)} title="Close menu">
            <Icon.close />
          </button>
        </div>

        {NAV.map((group) => (
          <div className="nav-group" key={group.section}>
            <div className="nav-label">{group.section}</div>
            {group.items.map(([to, label, icon, end]) => {
              const IconCmp = Icon[icon];
              return (
                <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
                  <IconCmp />
                  <span>{label}</span>
                </NavLink>
              );
            })}
          </div>
        ))}

        <div className="sidebar-footer">
          <div className="nav-item" style={{ pointerEvents: "none" }}>
            <span className="status-dot" />
            <span style={{ fontSize: 12.5 }}>Listening · 30s</span>
          </div>
          {user && (
            <div className="nav-item" style={{ pointerEvents: "none", gap: 10 }}>
              <div className="brand-logo" style={{ width: 26, height: 26, fontSize: 12, borderRadius: 8 }}>
                {user.username?.[0]?.toUpperCase()}
              </div>
              <span style={{ fontSize: 12.5, overflow: "hidden", textOverflow: "ellipsis" }}>{user.username}</span>
            </div>
          )}
          <div className="nav-item" onClick={handleLogout}><Icon.logout /><span>Logout</span></div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="topbar-lead">
            <button className="btn icon-btn nav-toggle" onClick={() => setNavOpen(true)} title="Menu">
              <Icon.menu />
            </button>
            <div className="topbar-titles">
              <h1 className="page-title">{title}</h1>
              {sub && <div className="page-sub">{sub}</div>}
            </div>
          </div>
          <div className="topbar-actions">
            <WorkspaceSwitcher current={user?.workspace} />
            <button className="btn icon-btn" onClick={toggle} title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
              {theme === "dark" ? <Icon.sun /> : <Icon.moon />}
            </button>
            <span className="badge badge-live"><span className="pulse" />Active · 30s poll</span>
          </div>
        </header>
        <main className="content">
          <Outlet context={{ openGuide: () => setGuideOpen(true) }} />
        </main>
      </div>

      <OnboardingGuide open={guideOpen} onClose={closeGuide} />
    </div>
  );
}
