/**
 * Roteamento por hash (#/u/HMB/preventivas, #/admin/auditoria): sem biblioteca, sobrevive a
 * recarregar a página e permite compartilhar o link. A rota é só NAVEGAÇÃO — quem decide o que o
 * usuário pode ver é o backend (uma rota proibida aqui apenas recebe 403).
 */
import { useCallback, useEffect, useState } from 'react';

export const PAGINAS_UNIDADE = ['preventivas', 'planos', 'colaboradores', 'revisao', 'atribuicoes', 'regras'] as const;
export type PaginaUnidade = (typeof PAGINAS_UNIDADE)[number];

export const PAGINAS_ADMIN = ['usuarios', 'utilizacao'] as const;
// links antigos (#/admin/auditoria, #/admin/relatorios) continuam funcionando: ambos viraram abas de Utilização
const ADMIN_LEGADO: Record<string, PaginaAdmin> = { auditoria: 'utilizacao', relatorios: 'utilizacao' };
export type PaginaAdmin = (typeof PAGINAS_ADMIN)[number];

export type Rota =
  | { tipo: 'unidade'; unidade: string; pagina: PaginaUnidade }
  | { tipo: 'admin'; pagina: PaginaAdmin }
  | { tipo: 'geral'; pagina: 'suporte' };

export function parseRota(hash: string, unidadePadrao: string): Rota {
  const partes = hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  if (partes[0] === 'admin' && (PAGINAS_ADMIN as readonly string[]).includes(partes[1])) {
    return { tipo: 'admin', pagina: partes[1] as PaginaAdmin };
  }
  if (partes[0] === 'admin' && ADMIN_LEGADO[partes[1]]) return { tipo: 'admin', pagina: ADMIN_LEGADO[partes[1]] };
  if (partes[0] === 'suporte') return { tipo: 'geral', pagina: 'suporte' };
  if (partes[0] === 'u' && partes[1]) {
    const pagina = (PAGINAS_UNIDADE as readonly string[]).includes(partes[2]) ? (partes[2] as PaginaUnidade) : 'preventivas';
    return { tipo: 'unidade', unidade: partes[1], pagina };
  }
  return { tipo: 'unidade', unidade: unidadePadrao, pagina: 'preventivas' };
}

export function hashDa(rota: Rota): string {
  if (rota.tipo === 'geral') return `#/${rota.pagina}`;
  return rota.tipo === 'admin' ? `#/admin/${rota.pagina}` : `#/u/${rota.unidade}/${rota.pagina}`;
}

export function useRota(unidadePadrao: string): [Rota, (r: Rota) => void] {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  const navegar = useCallback((r: Rota) => {
    const h = hashDa(r);
    if (window.location.hash !== h) window.location.hash = h;
    else setHash(h);
  }, []);
  return [parseRota(hash, unidadePadrao), navegar];
}
