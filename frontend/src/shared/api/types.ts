// Tipos compartilhados com a API (backend Flask). Mantidos em um único lugar.

export type Role = 'dev' | 'user';
export type UnitCode = 'HETRIN' | 'HMB';

export interface UnitInfo {
  codigo: UnitCode;
  nome: string;
  prefixo: '/api/grandmassif' | '/api/brasilandia';
}

export interface AuthUser {
  id: number;
  username: string;
  display_name: string;
  role: Role;
  is_dev: boolean;
  unit: UnitCode | null;
  unit_name: string | null;
  must_change_password: boolean;
  units: UnitInfo[];
}

export interface AuthState {
  user: AuthUser;
  csrf_token: string;
}

// ── Preventivas ────────────────────────────────────────────────────────────

export type StatusExecucao =
  | 'Concluída'
  | 'Em andamento'
  | 'Pendente'
  | 'Prevista'
  | 'Sem OS gerada'
  | 'Cancelada';

export type StatusResponsavel =
  | 'Atribuída'
  | 'Sem responsável'
  | 'Gestão'
  | 'Genérico'
  | 'Desligado'
  | 'Bloqueado'
  | '—';

export interface Preventiva {
  id: string;
  origem: 'OS' | 'Plano';
  data_prev: string; // dd/mm/aaaa
  data_iso: string; // aaaa-mm-dd
  dia_par: 'Par' | 'Ímpar';
  turno: 'Diurno' | 'Noturno' | '—';
  status: StatusExecucao;
  atrasada: boolean;
  plano: string;
  tipo: string;
  oficina: string;
  equipamento: string;
  setor: string;
  os_vinculada: string;
  os_id: number | null;
  os_situacao: string;
  responsavel_atual: string | null;
  responsavel_status: StatusResponsavel;
  responsavel_cadastro: string | null;
  recomendado: string | null;
  recomendados: string[];
  cargo: string;
  escala: string;
  score: number;
  revisao: boolean;
  sem_candidato: boolean;
  motivo_sem_candidato: string | null;
  regra: { id: string; status: 'aplicada' | 'pendente'; mensagem: string } | null;
  alertas: string[];
}

export interface TotaisPreventivas {
  total: number;
  por_status: Record<string, number>;
  por_dia: Record<string, number>;
  atrasadas: number;
  revisao: number;
  sem_candidato: number;
  com_recomendacao: number;
}

export interface PendenciaRegra {
  regra: string;
  turno: string;
  paridade: string;
  alias: string;
  status: 'ambiguo' | 'nao_encontrado';
  motivo: string;
  candidatos: string[];
}

export interface PreventivasResponse {
  total: number;
  com_recomendacao: number;
  em_atraso: number;
  pagina: number;
  por_pagina: number;
  itens: Preventiva[];
  totais: TotaisPreventivas;
  totais_periodo: TotaisPreventivas;
  periodo: { data_ini: string; data_fim: string; hoje: string };
  gerado_em: string;
  pendencias_regras: PendenciaRegra[];
}

export interface PreventivasQuery {
  dataIni: string;
  dataFim: string;
  incluirAtrasadas?: boolean;
  dias?: string[];
  fIni?: string;
  fFim?: string;
  status?: string[];
  atrasada?: boolean;
  turno?: string;
  paridade?: string;
  responsavel?: string;
  busca?: string;
  revisao?: boolean;
  semCandidato?: boolean;
  origem?: string;
  oficina?: string;
  page?: number;
  pageSize?: number;
  refresh?: boolean;
}

// ── Planos ─────────────────────────────────────────────────────────────────

export interface Plano {
  id: number | string;
  descricao: string;
  tipo: string;
  periodicidade: string;
  oficina: string;
  procedimento: string;
  ativo: boolean;
}

export interface PlanoResponse {
  total: number;
  itens: Plano[];
}

// ── Colaboradores ──────────────────────────────────────────────────────────

export type StatusColaborador = 'Ativo' | 'Desligado';

export interface Colaborador {
  funcionario: string;
  cargo: string;
  turno: string;
  regime: string;
  horario: string;
  status: StatusColaborador;
  habilidades: string[];
  bloqueado: boolean;
  aviso: string | null;
  data_admissao: string | null;
  data_desligamento: string | null;
  fora_da_escala: boolean;
  executa_os: boolean;
  especialidade: string | null;
  limite_diario: number | null;
}

export interface ColaboradorResponse {
  total: number;
  itens: Colaborador[];
}

export interface Habilidade {
  id: string;
  nome: string;
  categoria: string;
  peso: number;
}

export interface HabilidadeResponse {
  itens: Habilidade[];
}

export interface TipoServico {
  tipo: string;
  qtd: number;
}

export interface Equipamento {
  ativo: string;
  qtd: number;
}

export interface OSAberta {
  numero: string;
  abertura: string;
  tipo: string;
  setor: string;
  situacao: string;
}

export interface ColaboradorDetail extends Colaborador {
  os_abertas: OSAberta[];
  total_abertas: number;
  total_historico: number;
  tipos_servico: TipoServico[];
  equipamentos: Equipamento[];
}

// ── Revisão / regras / atribuições ────────────────────────────────────────

export interface ItemRevisao {
  os_numero: string;
  data_prev: string;
  plano: string;
  oficina: string;
  situacao: string;
  atrasada: boolean;
  responsavel_atual: string | null;
  responsavel_status: StatusResponsavel;
  responsavel_cadastro: string | null;
  data_desligamento: string | null;
}

export interface RevisaoResponse {
  total: number;
  por_status: Record<string, number>;
  por_responsavel: { status: string; responsavel: string; ordens: number }[];
  itens: ItemRevisao[];
  nota: string;
}

export interface RegraResponsavel {
  alias: string;
  status: 'ok' | 'ambiguo' | 'nao_encontrado';
  escolhido: string | null;
  origem: 'unico' | 'confirmado' | null;
  candidatos: string[];
  motivo: string;
}

export interface RegraLinha {
  turno: string;
  paridade: string;
  status: 'ok' | 'pendente';
  alertas: string[];
  responsaveis: RegraResponsavel[];
}

export interface Regra {
  id: string;
  titulo: string;
  descricao: string;
  linhas: RegraLinha[];
}

export interface RegrasResponse {
  regras: Regra[];
  quadro_ativo: string[];
}

export interface FilaItem {
  os_id: number;
  os_numero: string;
  data_iso: string;
  plano: string;
  responsavel_atual: string | null;
  responsavel_status: StatusResponsavel;
  proposto: string | null;
  propostos: string[];
  cargo: string;
  neovero_funcionario_id: number | null;
  automatizavel: boolean;
  motivo: string | null;
  alertas: string[];
}

export type StatusProposta = 'proposta' | 'aprovada' | 'rejeitada' | 'simulada' | 'aplicada' | 'conflito' | 'falha';

export interface Proposta {
  id: number;
  os_numero: string;
  data_prevista: string;
  plano: string | null;
  responsavel_original: string | null;
  funcionario_proposto: string;
  status: StatusProposta;
  mensagem: string | null;
  criado_por: string | null;
  criado_em: string;
  aprovado_por: string | null;
  processado_em: string | null;
}

export interface AtribuicoesResponse {
  fila: FilaItem[];
  propostas: Proposta[];
  integracao: { escrita_habilitada: boolean; simulacao: boolean; aviso: string };
}

// ── Administração ──────────────────────────────────────────────────────────

export interface AdminUser extends AuthUser {
  is_active: boolean;
  created_at: string;
  created_by: string | null;
  last_login_at: string | null;
  deactivated_at: string | null;
  locked_until: string | null;
  sessoes_abertas: number;
}

export interface AuditEvent {
  id: number;
  ts: string;
  user_id: number | null;
  username: string | null;
  unit: string | null;
  session_id: number | null;
  event: string;
  module: string | null;
  action: string | null;
  resource: string | null;
  result: 'success' | 'failure' | 'denied';
  status_code: number | null;
  method: string | null;
  path: string | null;
  ip: string | null;
  user_agent: string | null;
  details: Record<string, unknown> | null;
}

export interface AuditPage {
  total: number;
  pagina: number;
  por_pagina: number;
  itens: AuditEvent[];
}

export interface AuditFilters {
  dataIni?: string;
  dataFim?: string;
  userId?: number;
  username?: string;
  unit?: string;
  module?: string;
  event?: string;
  result?: string;
  page?: number;
  pageSize?: number;
}

export interface UsageSummary {
  periodo: { data_ini: string | null; data_fim: string | null };
  totais: {
    eventos: number;
    usuarios_ativos: number;
    logins: number;
    logins_falhos: number;
    acessos_negados: number;
    falhas: number;
    sessoes: number;
    sessoes_em_andamento: number;
    sessoes_por_encerramento: Record<string, number>;
    tempo_medio_sessao_min: number;
  };
  por_dia: { data: string; eventos: number; logins: number; usuarios_ativos: number }[];
  por_modulo: { modulo: string; eventos: number }[];
  por_usuario: { username: string; unit: string | null; eventos: number; escritas: number; exportacoes: number; falhas: number; ultimo_evento: string }[];
  falhas_relevantes: { evento: string; modulo: string | null; status: number | null; ocorrencias: number }[];
  cobertura_desde: string | null;
  nota: string;
  limite_inatividade_min: number;
}

export interface UsageRow {
  username: string;
  nome: string;
  perfil: string;
  unidade: string;
  conta_ativa: boolean;
  sessoes: number;
  tempo_em_sessao_min: number;
  eventos: number;
  escritas: number;
  exportacoes: number;
  falhas: number;
  dias_com_registro: number;
  primeiro_evento: string | null;
  ultimo_evento: string | null;
  ultimo_login: string | null;
  situacao: string;
}

export interface SessionRow {
  id: number;
  user_id: number;
  username: string;
  unit: string | null;
  inicio: string;
  ultima_atividade: string;
  fim: string | null;
  encerramento: string;
  duracao_min: number;
  ip: string | null;
}
