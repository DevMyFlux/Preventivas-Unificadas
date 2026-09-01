/**
 * HTTP client genérico que aceita prefixo de unidade.
 * Exemplo: buildUnitClient('/api/grandmassif') ou buildUnitClient('/api/brasilandia')
 */
import type {
  PreventivaResponse,
  PlanoResponse,
  ColaboradorResponse,
  ColaboradorDetail,
  HabilidadeResponse,
  StatusColaborador,
} from './types'

export type UnitApiPrefix = '/api/grandmassif' | '/api/brasilandia'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''

function buildUrl(prefix: UnitApiPrefix, path: string, dataIni?: string, dataFim?: string): string {
  const params = new URLSearchParams()
  if (dataIni) params.set('data_ini', dataIni)
  if (dataFim) params.set('data_fim', dataFim)
  const qs = params.toString()
  const full = `${API_BASE}${prefix}${path}`
  return qs ? `${full}?${qs}` : full
}

async function apiFetch<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API error ${res.status}: ${body}`)
  }
  return res.json() as Promise<T>
}

export function buildUnitClient(prefix: UnitApiPrefix) {
  return {
    fetchPreventivas: (dataIni?: string, dataFim?: string) =>
      apiFetch<PreventivaResponse>(buildUrl(prefix, '/preventivas', dataIni, dataFim)),

    fetchPlanos: () =>
      apiFetch<PlanoResponse>(buildUrl(prefix, '/planos')),

    fetchColaboradores: () =>
      apiFetch<ColaboradorResponse>(buildUrl(prefix, '/colaboradores')),

    fetchColaborador: (nome: string, dataIni?: string, dataFim?: string) =>
      apiFetch<ColaboradorDetail>(buildUrl(prefix, `/colaborador/${encodeURIComponent(nome)}`, dataIni, dataFim)),

    fetchHabilidades: () =>
      apiFetch<HabilidadeResponse>(buildUrl(prefix, '/habilidades')),

    atualizarStatusColaborador: async (nome: string, status: StatusColaborador) => {
      const res = await fetch(`${API_BASE}${prefix}/colaborador/${encodeURIComponent(nome)}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status }),
      })
      if (!res.ok) throw new Error(`Erro ${res.status}`)
      return res.json() as Promise<{ funcionario: string; status: StatusColaborador }>
    },

    atualizarBloqueioColaborador: async (nome: string, bloqueado: boolean, aviso?: string) => {
      const res = await fetch(`${API_BASE}${prefix}/colaborador/${encodeURIComponent(nome)}/bloqueio`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bloqueado, aviso: aviso ?? null }),
      })
      if (!res.ok) throw new Error(`Erro ${res.status}`)
      return res.json() as Promise<{ funcionario: string; bloqueado: boolean; aviso: string | null }>
    },

    adicionarHabilidade: async (nome: string, habilidadeId: string) => {
      const res = await fetch(`${API_BASE}${prefix}/colaborador/${encodeURIComponent(nome)}/habilidades`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ habilidade_id: habilidadeId }),
      })
      if (!res.ok) throw new Error(`Erro ${res.status}`)
      return res.json() as Promise<{ funcionario: string; habilidades: string[] }>
    },

    removerHabilidade: async (nome: string, habilidadeId: string) => {
      const res = await fetch(
        `${API_BASE}${prefix}/colaborador/${encodeURIComponent(nome)}/habilidades/${encodeURIComponent(habilidadeId)}`,
        { method: 'DELETE' },
      )
      if (!res.ok) throw new Error(`Erro ${res.status}`)
      return res.json() as Promise<{ funcionario: string; habilidades: string[] }>
    },

    exportarPreventivas: async (itens: unknown[], dataIni?: string, dataFim?: string) => {
      const params = new URLSearchParams()
      if (dataIni) params.set('data_ini', dataIni)
      if (dataFim) params.set('data_fim', dataFim)
      const qs = params.toString()
      const url = qs ? `${API_BASE}${prefix}/exportar_preventivas?${qs}` : `${API_BASE}${prefix}/exportar_preventivas`
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ itens }),
      })
      if (!res.ok) throw new Error(`Erro ${res.status}`)
      return res
    },

    limparCache: () =>
      fetch(`${API_BASE}${prefix}/limpar_cache`, { method: 'POST' }),
  }
}
