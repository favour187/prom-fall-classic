import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken } from "./api";
import { useApi } from "./useApi";

export interface User {
  id: string;
  email: string;
  display_name: string;
  created_at?: string | null;
}

interface AuthContextValue {
  user: User | null;
  booting: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => getToken());
  const [user, setUser] = useState<User | null>(null);

  // Resolve the session on boot (and whenever the token changes).
  const me = useApi<User | null>(token ? "/auth/me" : "", [token]);

  useEffect(() => {
    if (me.data) setUser(me.data);
    if (me.error && me.error.isAuthError) {
      setToken(null);
      setTokenState(null);
      setUser(null);
    }
    if (!token) setUser(null);
  }, [me.data, me.error, token]);

  const login = useCallback(async (email: string, password: string) => {
    const session = await api<{ token: string; user: User }>("/auth/login", {
      method: "POST",
      body: { email, password },
    });
    setToken(session.token);
    setTokenState(session.token);
    setUser(session.user);
  }, []);

  const register = useCallback(async (email: string, password: string, displayName: string) => {
    const session = await api<{ token: string; user: User }>("/auth/register", {
      method: "POST",
      body: { email, password, display_name: displayName },
    });
    setToken(session.token);
    setTokenState(session.token);
    setUser(session.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } catch {
      // local logout proceeds regardless
    }
    setToken(null);
    setTokenState(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, booting: me.loading && !me.data, login, register, logout }),
    [user, me.loading, me.data, login, register, logout]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
