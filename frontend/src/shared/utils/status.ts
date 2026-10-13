import type { StatusExecucao, StatusProposta, StatusResponsavel } from '../api/types';

export type Tone = 'success' | 'info' | 'warning' | 'danger' | 'purple' | 'neutral' | 'primary';

export const STATUS_EXECUCAO: { status: StatusExecucao; tone: Tone; hint: string }[] = [
  { status: 'Pendente', tone: 'warning', hint: 'OS aberta, ainda não iniciada' },
  { status: 'Em andamento', tone: 'info', hint: 'OS em execução' },
  { status: 'Concluída', tone: 'success', hint: 'OS fechada' },
  { status: 'Prevista', tone: 'neutral', hint: 'Projeção do plano; OS ainda não gerada' },
  { status: 'Sem OS gerada', tone: 'purple', hint: 'Data passada sem OS no Neovero (não é atraso)' },
  { status: 'Cancelada', tone: 'neutral', hint: 'OS cancelada' },
];

export function toneDoStatus(s: string): Tone {
  return STATUS_EXECUCAO.find((x) => x.status === s)?.tone ?? 'neutral';
}

export function toneDoResponsavel(s: StatusResponsavel | string): Tone {
  switch (s) {
    case 'Atribuída': return 'success';
    case 'Gestão': return 'warning';
    case 'Genérico': return 'warning';
    case 'Desligado': return 'danger';
    case 'Bloqueado': return 'danger';
    case 'Sem responsável': return 'purple';
    default: return 'neutral';
  }
}

export const HINT_RESPONSAVEL: Record<string, string> = {
  'Atribuída': 'Executante válido do quadro',
  'Gestão': 'OS em nome de quem gerencia (padrão do plano no Neovero) — não é executante',
  'Genérico': 'Nome genérico do Neovero (ex.: "ELÉTRICA - DIURNO"), não é uma pessoa',
  'Desligado': 'Executante já desligado nesta data',
  'Bloqueado': 'Executante com aptidão pendente',
  'Sem responsável': 'Campo de responsável vazio',
};

export function toneDaProposta(s: StatusProposta): Tone {
  switch (s) {
    case 'aplicada': return 'success';
    case 'simulada': return 'info';
    case 'aprovada': return 'primary';
    case 'proposta': return 'neutral';
    case 'rejeitada': return 'neutral';
    case 'conflito': return 'warning';
    case 'falha': return 'danger';
  }
}

export const NOME_MODULO: Record<string, string> = {
  preventivas: 'Preventivas',
  planos: 'Planos',
  colaboradores: 'Colaboradores',
  distribuicao: 'Distribuição',
  regras: 'Regras',
  exportacao: 'Exportação',
  admin: 'Administração',
  auth: 'Autenticação',
  sistema: 'Sistema',
};
