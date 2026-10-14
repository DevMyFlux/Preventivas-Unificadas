/**
 * Camada HTTP única: cookie de sessão (HttpOnly, mesma origem), token CSRF em toda requisição
 * que altera estado, e tratamento uniforme de erros. Nenhum segredo fica em storage do browser.
 */
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '';

export class ApiError extends Error {
  status: number;
  codigo?: string;
  campo?: string;
  /** 401: por que a sessão caiu (inatividade, tempo_maximo, conta_desativada…), conforme o servidor */
  motivo?: string;
  /** 401: a requisição que falhou ALTERAVA dados (POST/PATCH/DELETE) — portanto não foi salva */
  mutacao?: boolean;

  constructor(status: number, mensagem: string, codigo?: string, campo?: string, motivo?: string, mutacao?: boolean) {
    super(mensagem);
    this.name = 'ApiError';
    this.status = status;
    this.codigo = codigo;
    this.campo = campo;
    this.motivo = motivo;
    this.mutacao = mutacao;
  }
}

let csrfToken = '';
export interface InfoNaoAutenticado {
  mensagem: string;
  motivo?: string;
  mutacao: boolean;
}
let onUnauthorized: ((info: InfoNaoAutenticado) => void) | null = null;

export function setCsrfToken(token: string): void {
  csrfToken = token;
}

/** Registrado pelo AuthProvider: chamado quando uma requisição autenticada volta 401 (sessão expirada). */
export function setUnauthorizedHandler(fn: ((info: InfoNaoAutenticado) => void) | null): void {
  onUnauthorized = fn;
}

export type Query = Record<string, string | number | boolean | undefined | null | string[]>;

export function buildQuery(query?: Query): string {
  if (!query) return '';
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === '' || v === false) continue;
    if (Array.isArray(v)) {
      if (v.length > 0) params.set(k, v.join(','));
      continue;
    }
    params.set(k, String(v));
  }
  const s = params.toString();
  return s ? `?${s}` : '';
}

interface Options {
  query?: Query;
  body?: unknown;
  signal?: AbortSignal;
  /** login não deve disparar o tratamento global de 401 */
  skipUnauthorized?: boolean;
}

async function send(method: string, path: string, opts: Options = {}): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET' && csrfToken) headers['X-CSRF-Token'] = csrfToken;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}${buildQuery(opts.query)}`, {
      method,
      headers,
      credentials: 'same-origin',
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
    });
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err;
    throw new ApiError(0, 'Sem conexão com o servidor. Verifique sua rede e tente novamente.', 'rede');
  }

  if (!res.ok) {
    let mensagem = `Erro ${res.status}`;
    let codigo: string | undefined;
    let campo: string | undefined;
    let motivo: string | undefined;
    let mutacao = method !== 'GET';
    try {
      const corpo = await res.clone().json();
      mensagem = corpo.erro ?? mensagem;
      codigo = corpo.codigo;
      campo = corpo.campo;
      motivo = corpo.motivo;
      if (typeof corpo.mutacao === 'boolean') mutacao = corpo.mutacao;
    } catch {
      /* corpo não-JSON: mantém a mensagem genérica */
    }
    if (res.status === 401 && !opts.skipUnauthorized) onUnauthorized?.({ mensagem, motivo, mutacao });
    throw new ApiError(res.status, mensagem, codigo, campo, motivo, mutacao);
  }
  return res;
}

export async function request<T>(method: string, path: string, opts: Options = {}): Promise<T> {
  const res = await send(method, path, opts);
  return (await res.json()) as T;
}

export const get = <T>(path: string, query?: Query, signal?: AbortSignal) =>
  request<T>('GET', path, { query, signal });
export const post = <T>(path: string, body?: unknown, opts: Options = {}) =>
  request<T>('POST', path, { ...opts, body: body ?? {} });
export const patch = <T>(path: string, body?: unknown) => request<T>('PATCH', path, { body: body ?? {} });
export const put = <T>(path: string, body?: unknown) => request<T>('PUT', path, { body: body ?? {} });
export const del = <T>(path: string, query?: Query) => request<T>('DELETE', path, { query });

/** Baixa um arquivo gerado pelo servidor (Excel/CSV) e dispara o download no browser. */
export async function download(
  method: 'GET' | 'POST',
  path: string,
  query: Query | undefined,
  nomePadrao: string,
  body?: unknown,
): Promise<string> {
  const res = await send(method, path, { query, body });
  const blob = await res.blob();
  const disposition = res.headers.get('Content-Disposition') ?? '';
  const m = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
  const nome = m ? decodeURIComponent(m[1]) : nomePadrao;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return nome;
}

export function mensagemDeErro(err: unknown, padrao = 'Não foi possível concluir a operação.'): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error && err.name !== 'AbortError') return err.message || padrao;
  return padrao;
}
