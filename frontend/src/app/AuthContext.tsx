import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { authApi } from '../shared/api/client';
import { setCsrfToken, setUnauthorizedHandler } from '../shared/api/http';
import type { InfoNaoAutenticado } from '../shared/api/http';
import type { AuthUser } from '../shared/api/types';

/** Por que a pessoa voltou para a tela de login (null = nunca esteve logada nesta página / saiu por conta própria). */
export interface MotivoSaida {
  mensagem: string;
  motivo?: string;
  /** a última operação alterava dados e NÃO foi salva */
  mutacao: boolean;
}

interface AuthContextValue {
  user: AuthUser | null;
  /** true enquanto a sessão existente está sendo verificada no carregamento da página */
  loading: boolean;
  /** true quando uma sessão que estava ativa deixou de valer (expirou/foi encerrada) */
  expired: boolean;
  /** detalhes da queda da sessão (inatividade, desativação…), para a tela de login explicar */
  saida: MotivoSaida | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  reset: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const CANAL = 'myflux-auth';
type MensagemCanal = { tipo: 'saiu'; saida: MotivoSaida | null } | { tipo: 'entrou' };

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [saida, setSaida] = useState<MotivoSaida | null>(null);
  const canal = useRef<BroadcastChannel | null>(null);

  const limpar = useCallback(() => {
    setCsrfToken('');
    setUser(null);
  }, []);

  useEffect(() => {
    // Várias abas compartilham o mesmo cookie de sessão: quando UMA cai (ou sai), as outras mostram o
    // login na hora, sem esperar a próxima requisição. A decisão de validade continua sendo do servidor.
    if (typeof BroadcastChannel !== 'undefined') {
      const bc = new BroadcastChannel(CANAL);
      bc.onmessage = (ev: MessageEvent<MensagemCanal>) => {
        if (ev.data?.tipo === 'saiu') {
          setCsrfToken('');
          setUser((atual) => {
            if (atual) setSaida(ev.data && 'saida' in ev.data ? ev.data.saida : null);
            return null;
          });
        }
      };
      canal.current = bc;
    }
    setUnauthorizedHandler((info: InfoNaoAutenticado) => {
      setCsrfToken('');
      setUser((atual) => {
        if (atual) {   // só avisa "expirou" se havia sessão; o login inicial não conta
          const s: MotivoSaida = { mensagem: info.mensagem, motivo: info.motivo, mutacao: info.mutacao };
          setSaida(s);
          canal.current?.postMessage({ tipo: 'saiu', saida: s } satisfies MensagemCanal);
        }
        return null;
      });
    });
    let vivo = true;
    authApi.me()
      .then((s) => { if (vivo) { setCsrfToken(s.csrf_token); setUser(s.user); } })
      .catch(() => { /* sem sessão: mostra o login */ })
      .finally(() => { if (vivo) setLoading(false); });
    return () => {
      vivo = false;
      setUnauthorizedHandler(null);
      canal.current?.close();
      canal.current = null;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const s = await authApi.login(username, password);
    setCsrfToken(s.csrf_token);
    setSaida(null);
    setUser(s.user);
  }, []);

  const logout = useCallback(async () => {
    try { await authApi.logout(); } catch { /* mesmo que falhe, descarta o estado local */ }
    setSaida(null);
    limpar();
    canal.current?.postMessage({ tipo: 'saiu', saida: null } satisfies MensagemCanal);
  }, [limpar]);

  const value = useMemo(
    () => ({ user, loading, expired: saida !== null, saida, login, logout, reset: limpar }),
    [user, loading, saida, login, logout, limpar]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth deve ser usado dentro de <AuthProvider>');
  return ctx;
}
