export interface OSItem {
  numero: string;
  abertura: string;
  tipo: string;
  setor: string;
  prioridade: string;
  situacao: number;
  sit_label: string;
  responsavel: string | null;
  reclamacao: string;
}

export interface OSResponse {
  total: number;
  com_responsavel: number;
  sem_responsavel: number;
  abertas: number;
  em_andamento: number;
  fechadas: number;
  pendencia: number;
  itens: OSItem[];
}

export interface RecomendacaoItem {
  numero: string;
  tipo: string;
  setor: string;
  ativo: string;
  situacao: string;
  prioridade: string;
  reclamacao: string;
  responsavel_atual: string | null;
  recomendado: string | null;
  cargo: string;
  escala: string;
  score: number;
  status: string;
  data_os: string;
  hora_os: number;
  turno_os: string;
  dia_par: string;
}

export interface RecomendacaoResponse {
  total: number;
  com_responsavel: number;
  sem_responsavel: number;
  bate_atual: number;
  sugestao_diff: number;
  sem_candidato: number;
  itens: RecomendacaoItem[];
}

export interface FuncionarioTask {
  funcionario: string;
  cargo: string;
  turno: string;
  regime: string;
  total_tasks: number;
  tasks: RecomendacaoItem[];
}

export interface FuncionarioTaskResponse {
  total: number;
  itens: FuncionarioTask[];
}
