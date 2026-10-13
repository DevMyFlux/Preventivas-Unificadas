import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { authApi } from '../shared/api/client';
import { setCsrfToken, setUnauthorizedHandler } from '../shared/api/http';
import type { AuthUser } from '../shared/api/types';

interface AuthContextValue {
  user: AuthUser | null;
  /** true enquanto a sessão existente está sendo verificada no carregamento da página */
  loading: boolean;
  /** true quando uma sessão que estava ativa deixou de valer (expirou/foi encerrada) */
  expired: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  reset: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [expired, setExpired] = useState(false);

  const limpar = useCallback(() => {
    setCsrfToken('');
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setCsrfToken('');
      setUser((atual) => {
        if (atual) setExpired(true);   // só avisa "expirou" se havia sessão; o login inicial não conta
        return null;
      });
    });
    let vivo = true;
    authApi.me()
      .then((s) => { if (vivo) { setCsrfToken(s.csrf_token); setUser(s.user); } })
      .catch(() => { /* sem sessão: mostra o login */ })
      .finally(() => { if (vivo) setLoading(false); });
    return () => { vivo = false; setUnauthorizedHandler(null); };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const s = await authApi.login(username, password);
    setCsrfToken(s.csrf_token);
    setExpired(false);
    setUser(s.user);
  }, []);

  const logout = useCallback(async () => {
    try { await authApi.logout(); } catch { /* mesmo que falhe, descarta o estado local */ }
    setExpired(false);
    limpar();
  }, [limpar]);

  const value = useMemo(() => ({ user, loading, expired, login, logout, reset: limpar }), [user, loading, expired, login, logout, limpar]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth deve ser usado dentro de <AuthProvider>');
  return ctx;
}
