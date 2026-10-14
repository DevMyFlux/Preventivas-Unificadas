/**
 * Acompanhamento da sessão no navegador. Quem DECIDE se a sessão vale é sempre o servidor (limite de
 * 25 min sem atividade válida); aqui só se mostra o aviso antes de cair e se informa atividade real.
 *
 *  - A cada 30 s consulta `GET /api/auth/session`, que NÃO conta como atividade (nenhuma chamada
 *    automática mantém a sessão viva). Se a sessão já caiu, a resposta 401 leva ao login (em todas as
 *    abas, via BroadcastChannel no AuthContext).
 *  - Se houve interação real (clique, tecla, toque, rolagem) desde o último batimento, em vez de só
 *    consultar envia `POST /api/auth/ping {interagiu:true}`: é isso que renova o prazo.
 *  - Faltando ~2 min, mostra o aviso com contagem regressiva e o botão "Continuar conectado".
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { authApi } from '../shared/api/client';
import { Button } from '../shared/ui/ui';

const INTERVALO_MS = 30_000;
const EVENTOS = ['mousedown', 'keydown', 'touchstart', 'scroll', 'wheel'] as const;

export interface PrazoSessao {
  /** instante (ms desde 1970) em que o servidor derruba a sessão se nada acontecer */
  prazoMs: number | null;
  avisoAntesS: number;
}

export function useSessaoMonitor(): PrazoSessao & { continuar: () => Promise<void>; verificar: () => void } {
  const [estado, setEstado] = useState<PrazoSessao>({ prazoMs: null, avisoAntesS: 120 });
  const interagiu = useRef(false);
  const ocupado = useRef(false);
  const estadoRef = useRef(estado);
  estadoRef.current = estado;

  const sincronizar = useCallback(async (renovar: boolean) => {
    if (ocupado.current) return;
    ocupado.current = true;
    try {
      if (renovar) {
        interagiu.current = false;
        const r = await authApi.ping(true);
        setEstado((e) => ({ ...e, prazoMs: Date.now() + r.expira_em_s * 1000 }));
      } else {
        const r = await authApi.sessao();
        setEstado({ prazoMs: Date.now() + r.expira_em_s * 1000, avisoAntesS: r.aviso_antes_s });
      }
    } catch {
      /* 401 já foi tratado globalmente (volta ao login); falha de rede: tenta de novo no próximo ciclo */
    } finally {
      ocupado.current = false;
    }
  }, []);

  useEffect(() => {
    const marcar = () => {
      interagiu.current = true;
      // com o aviso na tela, qualquer interação real renova na hora (sem esperar o próximo ciclo)
      const { prazoMs, avisoAntesS } = estadoRef.current;
      if (prazoMs !== null && prazoMs - Date.now() <= avisoAntesS * 1000) void sincronizar(true);
    };
    EVENTOS.forEach((e) => window.addEventListener(e, marcar, { passive: true }));
    const ciclo = () => {
      if (document.visibilityState !== 'visible') return;
      void sincronizar(interagiu.current);
    };
    const id = window.setInterval(ciclo, INTERVALO_MS);
    document.addEventListener('visibilitychange', ciclo);   // ao voltar para a aba: confere já
    return () => {
      EVENTOS.forEach((e) => window.removeEventListener(e, marcar));
      document.removeEventListener('visibilitychange', ciclo);
      window.clearInterval(id);
    };
  }, [sincronizar]);

  const continuar = useCallback(() => sincronizar(true), [sincronizar]);
  const verificar = useCallback(() => { void sincronizar(false); }, [sincronizar]);
  return { ...estado, continuar, verificar };
}

function formatar(s: number): string {
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, '0')}`;
}

/** Aviso de expiração iminente. Fica oculto enquanto há tempo de sobra. */
export function AvisoSessao({ prazoMs, avisoAntesS, onContinuar, onZerou }: PrazoSessao & {
  onContinuar: () => void; onZerou: () => void;
}) {
  const [agora, setAgora] = useState(() => Date.now());
  useEffect(() => {
    if (prazoMs === null) return undefined;
    const id = window.setInterval(() => setAgora(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [prazoMs]);
  const restante = prazoMs === null ? null : Math.max(0, Math.ceil((prazoMs - agora) / 1000));
  useEffect(() => {
    if (restante === 0) onZerou();   // o servidor confirma (401 → login); nada é assumido aqui
  }, [restante, onZerou]);
  if (restante === null || restante > avisoAntesS) return null;
  return (
    <div className="session-warning" role="alertdialog" aria-live="assertive" aria-label="Sessão prestes a expirar">
      <div>
        <strong>Sua sessão vai expirar por inatividade</strong>
        <div>Você será desconectado em <span className="session-count">{formatar(restante)}</span>. Alterações não salvas serão perdidas.</div>
      </div>
      <Button variant="primary" size="sm" onClick={onContinuar}>Continuar conectado</Button>
    </div>
  );
}
