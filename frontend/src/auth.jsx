import { createContext, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // On boot, if we have a token, confirm it's still valid by fetching the user.
  useEffect(() => {
    if (!getToken()) { setLoading(false); return; }
    api.auth.me()
      .then(setUser)
      .catch(() => { setToken(null); setUser(null); })
      .finally(() => setLoading(false));
  }, []);

  const login = async (username, password) => {
    const data = await api.auth.login({ username, password });
    setToken(data.token);
    setUser(data.user);
    return data.user;
  };

  const register = async (username, email, password) => {
    const data = await api.auth.register({ username, email, password });
    setToken(data.token);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    try { await api.auth.logout(); } catch { /* ignore */ }
    setToken(null);
    setUser(null);
  };

  const refreshUser = async () => {
    const me = await api.auth.me();
    setUser(me);
    return me;
  };

  const updateProfile = async (patch) => {
    const updated = await api.auth.updateProfile(patch);
    setUser(updated);
    return updated;
  };

  // Mark the setup guide seen. Optimistically flip the flag so it won't reopen,
  // then persist; ignore network errors — worst case it shows once more.
  const completeOnboarding = async () => {
    setUser((u) => (u ? { ...u, onboarding_completed: true } : u));
    try { await api.auth.completeOnboarding(); } catch { /* ignore */ }
  };

  const deleteAccount = async (password) => {
    await api.auth.deleteAccount({ password });
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, refreshUser, updateProfile, completeOnboarding, deleteAccount }}>
      {children}
    </AuthContext.Provider>
  );
}
