import type { OSResponse, RecomendacaoResponse, FuncionarioTaskResponse } from './types';

const PREFIX = '/api/grandmassif';

function buildUrl(path: string, dataIni?: string, dataFim?: string): string {
  const params = new URLSearchParams();
  if (dataIni) params.set('data_ini', dataIni);
  if (dataFim) params.set('data_fim', dataFim);
  const qs = params.toString();
  return qs ? `${PREFIX}${path}?${qs}` : `${PREFIX}${path}`;
}

async function apiFetch<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API error ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export function fetchOS(dataIni?: string, dataFim?: string): Promise<OSResponse> {
  return apiFetch<OSResponse>(buildUrl('/os', dataIni, dataFim));
}

export function fetchRecomendacoes(dataIni?: string, dataFim?: string): Promise<RecomendacaoResponse> {
  return apiFetch<RecomendacaoResponse>(buildUrl('/recomendacoes', dataIni, dataFim));
}

export function fetchTasksPorFuncionario(dataIni?: string, dataFim?: string): Promise<FuncionarioTaskResponse> {
  return apiFetch<FuncionarioTaskResponse>(buildUrl('/tasks_por_funcionario', dataIni, dataFim));
}

export function exportarRecomendacoes(): void {
  window.open(`${PREFIX}/exportar`, '_blank');
}
