/**
 * Clientes da API. O prefixo da unidade vem do cadastro do usuário (AuthUser.units), nunca é
 * escolhido livremente: o backend de qualquer forma recusa (403) um prefixo que não seja o do usuário.
 */
import { del, download, get, patch, post, put } from './http';
import type { Query } from './http';
import type {
  AtribuicoesResponse,
  AuthState,
  EstadoSessao,
  ColaboradorDetail,
  ColaboradorResponse,
  HabilidadeResponse,
  PlanoResponse,
  PreventivasQuery,
  PreventivasResponse,
  RegrasResponse,
  RevisaoResponse,
  StatusColaborador,
  StatusProposta,
  SuporteStatus,
  Transferencia,
  TransferenciasResponse,
  TipoSuporte,
  UnitInfo,
} from './types';

export type UnitApiPrefix = UnitInfo['prefixo'];

export function preventivasQuery(q: PreventivasQuery): Query {
  return {
    data_ini: q.dataIni,
    data_fim: q.dataFim,
    incluir_atrasadas: q.incluirAtrasadas === false ? '0' : '1',
    dias: q.dias,
    f_ini: q.fIni,
    f_fim: q.fFim,
    status: q.status,
    atrasada: q.atrasada ? '1' : undefined,
    turno: q.turno,
    paridade: q.paridade,
    responsavel: q.responsavel?.trim(),
    busca: q.busca?.trim(),
    revisao: q.revisao ? '1' : undefined,
    sem_candidato: q.semCandidato ? '1' : undefined,
    origem: q.origem,
    oficina: q.oficina,
    page: q.page,
    page_size: q.pageSize,
    refresh: q.refresh ? '1' : undefined,
  };
}

export function buildUnitClient(prefix: UnitApiPrefix) {
  const enc = encodeURIComponent;
  return {
    prefix,
    fetchPreventivas: (q: PreventivasQuery, signal?: AbortSignal) =>
      get<PreventivasResponse>(`${prefix}/preventivas`, preventivasQuery(q), signal),
    exportarPreventivas: (q: PreventivasQuery) =>
      download('GET', `${prefix}/exportar_preventivas`, preventivasQuery({ ...q, page: undefined, pageSize: undefined }),
        'preventivas.xlsx'),

    fetchPlanos: () => get<PlanoResponse>(`${prefix}/planos`),
    exportarPlanos: (itens: unknown[]) => download('POST', `${prefix}/exportar_planos`, undefined, 'planos.xlsx', { itens }),

    fetchColaboradores: () => get<ColaboradorResponse>(`${prefix}/colaboradores`),
    fetchColaborador: (nome: string, dataIni?: string, dataFim?: string) =>
      get<ColaboradorDetail>(`${prefix}/colaborador/${enc(nome)}`, { data_ini: dataIni, data_fim: dataFim }),
    fetchHabilidades: () => get<HabilidadeResponse>(`${prefix}/habilidades`),
    atualizarStatusColaborador: (nome: string, status: StatusColaborador) =>
      patch<{ funcionario: string; status: StatusColaborador }>(`${prefix}/colaborador/${enc(nome)}/status`, { status }),
    atualizarVinculoColaborador: (nome: string, v: { data_admissao?: string | null; data_desligamento?: string | null }) =>
      patch<{ funcionario: string }>(`${prefix}/colaborador/${enc(nome)}/vinculo`, v),
    atualizarBloqueioColaborador: (nome: string, bloqueado: boolean, aviso?: string) =>
      patch<{ funcionario: string; bloqueado: boolean; aviso: string | null }>(
        `${prefix}/colaborador/${enc(nome)}/bloqueio`, { bloqueado, aviso: aviso ?? null }),
    adicionarHabilidade: (nome: string, habilidadeId: string) =>
      post<{ funcionario: string; habilidades: string[] }>(`${prefix}/colaborador/${enc(nome)}/habilidades`,
        { habilidade_id: habilidadeId }),
    removerHabilidade: (nome: string, habilidadeId: string) =>
      del<{ funcionario: string; habilidades: string[] }>(
        `${prefix}/colaborador/${enc(nome)}/habilidades/${enc(habilidadeId)}`),

    fetchRevisao: () => get<RevisaoResponse>(`${prefix}/revisao`),
    fetchTransferencias: (os?: string) => get<TransferenciasResponse>(`${prefix}/transferencias`, { os }),
    anotarMotivoTransferencia: (id: number, motivo: string) =>
      put<Transferencia>(`${prefix}/transferencias/${id}/motivo`, { motivo }),

    fetchRegras: () => get<RegrasResponse>(`${prefix}/regras`),
    confirmarRegra: (alias: string, funcionario: string) =>
      put<{ ok: boolean }>(`${prefix}/regras/resolucoes`, { alias, funcionario }),
    removerConfirmacaoRegra: (alias: string) => del<{ removidas: number }>(`${prefix}/regras/resolucoes`, { alias }),

    fetchAtribuicoes: (dataIni: string, dataFim: string) =>
      get<AtribuicoesResponse>(`${prefix}/atribuicoes`, { data_ini: dataIni, data_fim: dataFim }),
    criarPropostas: (dataIni: string, dataFim: string, osIds: number[]) =>
      post<{ resultado: { os_numero: string; criada: boolean; motivo?: string; id?: number }[] }>(
        `${prefix}/atribuicoes/propostas`, { data_ini: dataIni, data_fim: dataFim, os_ids: osIds }),
    decidirPropostas: (ids: number[], acao: 'aprovar' | 'rejeitar') =>
      post<{ atualizadas: number }>(`${prefix}/atribuicoes/decisao`, { ids, acao }),
    processarPropostas: (ids: number[], modo: 'simular' | 'aplicar') =>
      post<{ resultado: { id: number; os_numero?: string; status: StatusProposta; mensagem: string }[] }>(
        `${prefix}/atribuicoes/processar`, { ids, modo }),

    limparCache: () => post<{ removidas: number }>(`${prefix}/limpar_cache`),
  };
}

export type UnitApiClient = ReturnType<typeof buildUnitClient>;

// ── Autenticação ───────────────────────────────────────────────────────────

export const authApi = {
  login: (username: string, password: string) =>
    post<AuthState>('/api/auth/login', { username, password }, { skipUnauthorized: true }),
  me: () => get<AuthState>('/api/auth/me'),
  logout: () => post<{ ok: boolean }>('/api/auth/logout'),
  /** Consulta o prazo da sessão SEM renová-la (o servidor não conta esta chamada como atividade). */
  sessao: () => get<EstadoSessao>('/api/auth/session'),
  /** Batimento: só renova a sessão quando `interagiu` é true (houve clique/tecla/rolagem de verdade). */
  ping: (interagiu = false) => post<{ ok: boolean; expira_em_s: number }>('/api/auth/ping', { interagiu }),
  activity: (module: string, unit?: string) => post<{ ok: boolean }>('/api/auth/activity', { module, unit }),
  changePassword: (currentPassword: string, newPassword: string) =>
    post<{ ok: boolean; relogin: boolean }>('/api/auth/password',
      { current_password: currentPassword, new_password: newPassword }),
};

// ── Sugestões e Suporte ────────────────────────────────────────────────────

export const suporteApi = {
  status: () => get<SuporteStatus>('/api/suporte/status'),
  enviar: (m: { nome: string; email: string; tipo: TipoSuporte; mensagem: string }) =>
    post<{ ok: boolean; id: number; mensagem: string }>('/api/suporte', m),
};
