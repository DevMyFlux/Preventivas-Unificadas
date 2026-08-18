// Tipos base compartilhados entre todas as unidades

export interface Preventiva {
  data_prev: string;
  dia_par: string;
  atrasada: boolean;
  plano: string;
  tipo: string;
  oficina: string;
  equipamento: string;
  setor: string;
  os_vinculada: string;
  os_situacao: string;
  recomendado: string | null;
  cargo: string;
  escala: string;
  score: number;
}

export interface PreventivaResponse {
  total: number;
  com_recomendacao: number;
  em_atraso: number;
  itens: Preventiva[];
}

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

export interface ColaboradorDetail {
  funcionario: string;
  cargo: string;
  turno: string;
  regime: string;
  horario: string;
  status: StatusColaborador;
  habilidades: string[];
  bloqueado: boolean;
  aviso: string | null;
  os_abertas: OSAberta[];
  total_abertas: number;
  total_historico: number;
  tipos_servico: TipoServico[];
  equipamentos: Equipamento[];
}
