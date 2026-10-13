import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

type Kind = 'success' | 'error' | 'info';
interface ToastItem { id: number; kind: Kind; text: string }

interface ToastApi {
  success: (t: string) => void;
  error: (t: string) => void;
  info: (t: string) => void;
}

const Ctx = createContext<ToastApi>({ success: () => {}, error: () => {}, info: () => {} });

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(0);

  const push = useCallback((kind: Kind, text: string) => {
    const id = ++seq.current;
    setItems((cur) => [...cur.slice(-3), { id, kind, text }]);
    window.setTimeout(() => setItems((cur) => cur.filter((x) => x.id !== id)), kind === 'error' ? 8000 : 4500);
  }, []);

  const api = useMemo<ToastApi>(() => ({
    success: (t) => push('success', t),
    error: (t) => push('error', t),
    info: (t) => push('info', t),
  }), [push]);

  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="toasts" aria-live="polite" aria-atomic="false">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.kind}`} role={t.kind === 'error' ? 'alert' : 'status'}>
            {t.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
