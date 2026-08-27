import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import { Loader } from "./components/ui";
import Auth from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import Campaigns from "./pages/Campaigns";
import Audience from "./pages/Audience";
import Senders from "./pages/Senders";
import Mailboxes from "./pages/Mailboxes";
import AutoReply from "./pages/AutoReply";
import Rules from "./pages/Rules";
import Configuration from "./pages/Configuration";
import Listeners from "./pages/Listeners";
import Placeholders from "./pages/Placeholders";
import Links from "./pages/Links";
import Attachments from "./pages/Attachments";
import Proxies from "./pages/Proxies";
import Telegram from "./pages/Telegram";
import Security from "./pages/Security";
import Team from "./pages/Team";
import Settings from "./pages/Settings";
import Billing from "./pages/Billing";

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <Loader label="Loading…" />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

function PublicOnly({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <Loader label="Loading…" />;
  if (user) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<PublicOnly><Auth mode="login" /></PublicOnly>} />
        <Route path="/signup" element={<PublicOnly><Auth mode="signup" /></PublicOnly>} />
        <Route element={<Protected><Layout /></Protected>}>
          <Route index element={<Dashboard />} />
          <Route path="campaigns" element={<Campaigns />} />
          <Route path="audience" element={<Audience />} />
          <Route path="senders" element={<Senders />} />
          <Route path="mailboxes" element={<Mailboxes />} />
          <Route path="auto-reply" element={<AutoReply />} />
          <Route path="rules" element={<Rules />} />
          <Route path="configuration" element={<Configuration />} />
          <Route path="listeners" element={<Listeners />} />
          <Route path="placeholders" element={<Placeholders />} />
          <Route path="links" element={<Links />} />
          <Route path="attachments" element={<Attachments />} />
          <Route path="proxies" element={<Proxies />} />
          <Route path="team" element={<Team />} />
          <Route path="billing" element={<Billing />} />
          <Route path="security" element={<Security />} />
          <Route path="telegram" element={<Telegram />} />
          <Route path="settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
