/**
 * HTTP client genérico que aceita prefixo de unidade.
 * Exemplo: buildUnitClient('/api/grandmassif') ou buildUnitClient('/api/brasilandia')
 */
import type {
  PreventivaResponse,
  PlanoResponse,
  ColaboradorResponse,
  ColaboradorDetail,
} from './types'

export type UnitApiPrefix = '/api/grandmassif' | '/api/brasilandia'

function buildUrl(prefix: UnitApiPrefix, path: string, dataIni?: string, dataFim?: string): string {
  const params = new URLSearchParams()
  if (dataIni) params.set('data_ini', dataIni)
  if (dataFim) params.set('data_fim', dataFim)
  const qs = params.toString()
  return qs ? `${prefix}${path}?${qs}` : `${prefix}${path}`
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

    fetchColaborador: (nome: string) =>
      apiFetch<ColaboradorDetail>(`${prefix}/colaborador/${encodeURIComponent(nome)}`),

    exportarPreventivas: async (itens: unknown[], dataIni?: string, dataFim?: string) => {
      const params = new URLSearchParams()
      if (dataIni) params.set('data_ini', dataIni)
      if (dataFim) params.set('data_fim', dataFim)
      const qs = params.toString()
      const url = qs ? `${prefix}/exportar_preventivas?${qs}` : `${prefix}/exportar_preventivas`
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ itens }),
      })
      if (!res.ok) throw new Error(`Erro ${res.status}`)
      return res
    },

    limparCache: () =>
      fetch(`${prefix}/limpar_cache`, { method: 'POST' }),
  }
}
