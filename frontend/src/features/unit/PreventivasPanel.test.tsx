import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { UnitApiClient } from '../../shared/api/client';
import type { Preventiva, PreventivasQuery, PreventivasResponse, TotaisPreventivas } from '../../shared/api/types';
import { ToastProvider } from '../../shared/ui/Toast';
import PreventivasPanel, { } from './PreventivasPanel';
import { filtrarColaboradores } from './ColaboradoresPanel';
import { filtrarPlanos } from './PlanosPanel';

function item(extra: Partial<Preventiva>): Preventiva {
  return {
    id: Math.random().toString(36).slice(2), origem: 'OS', data_prev: '14/10/2026', data_iso: '2026-10-14', dia_par: 'Par',
    turno: '—', status: 'Pendente', atrasada: false, plano: 'PM - MENSAL - SPLIT', tipo: 'PREVENTIVA', oficina: 'CLIMATIZAÇÃO',
    equipamento: 'SPLIT 1', setor: 'BLOCO A', os_vinculada: '1001', os_id: 1, os_situacao: 'Aberta', responsavel_atual: 'CLIMA UM',
    responsavel_status: 'Atribuída', responsavel_cadastro: 'Clima Um', recomendado: null, recomendados: [], cargo: '', escala: '',
    score: -999, revisao: false, sem_candidato: false, motivo_sem_candidato: null, requer_intervencao: false, motivo_intervencao: null,
    regra: null, alertas: [], ...extra,
  };
}

const totais = (extra: Partial<TotaisPreventivas> = {}): TotaisPreventivas => ({
  total: 6, por_status: { Pendente: 2, 'Em andamento': 1, Concluída: 2, 'Aguardando geração': 1, 'Sem OS – verificar': 0, Parada: 0, Cancelada: 0 },
  por_dia: { '2026-10-13': 2, '2026-10-14': 4 }, atrasadas: 2, revisao: 1, sem_candidato: 1, requer_intervencao: 1, com_recomendacao: 1, ...extra,
});

function resposta(itens: Preventiva[], extra: Partial<PreventivasResponse> = {}): PreventivasResponse {
  return {
    total: itens.length, com_recomendacao: 0, em_atraso: 0, pagina: 1, por_pagina: 100, itens, totais: totais({ total: itens.length }),
    totais_periodo: totais(), periodo: { data_ini: '2026-10-13', data_fim: '2026-10-14', hoje: '2026-10-14' },
    gerado_em: '2026-10-14T15:00:00Z', pendencias_regras: [], ...extra,
  };
}

const fetchPreventivas = vi.fn();
const exportarPreventivas = vi.fn();
const client = { prefix: '/api/brasilandia', fetchPreventivas, exportarPreventivas } as unknown as UnitApiClient;

function montar(props: Partial<React.ComponentProps<typeof PreventivasPanel>> = {}) {
  return render(<ToastProvider><PreventivasPanel client={client} dataIni="2026-10-13" dataFim="2026-10-14" {...props} /></ToastProvider>);
}

const kpis = () => within(screen.getByLabelText('Resumo do período'));
const chips = () => within(screen.getByRole('group', { name: 'Filtrar por status' }));
const ultimaConsulta = (): PreventivasQuery => fetchPreventivas.mock.calls[fetchPreventivas.mock.calls.length - 1][0];

beforeEach(() => {
  fetchPreventivas.mockReset();
  exportarPreventivas.mockReset();
  fetchPreventivas.mockResolvedValue(resposta([
    item({ os_vinculada: '1001', status: 'Pendente', atrasada: true, data_prev: '13/10/2026', data_iso: '2026-10-13' }),
    item({ os_vinculada: '1002', status: 'Concluída', responsavel_atual: 'IRANILDO SILVA DOS SANTOS' }),
    item({ os_vinculada: '1003', status: 'Pendente', responsavel_atual: 'WILLIAN DE SOUZA LOBO', responsavel_status: 'Gestão', revisao: true,
      recomendado: 'Iranildo Silva dos Santos', recomendados: ['Iranildo Silva dos Santos'], cargo: 'Eletricista', escala: 'Diurno | Ímpar' }),
    item({ os_vinculada: '1004', status: 'Pendente', sem_candidato: true, requer_intervencao: true, responsavel_atual: 'ELÉTRICA - DIURNO', responsavel_status: 'Genérico',
      motivo_sem_candidato: 'Limite diário de ordens atingido por todos os profissionais compatíveis — requer intervenção.',
      motivo_intervencao: 'Limite diário de ordens atingido por todos os profissionais compatíveis — requer intervenção.' }),
  ]));
});

describe('PreventivasPanel', () => {
  it('pede ao servidor o período, com atrasadas incluídas, e mostra status, atraso e responsável', async () => {
    montar();
    await screen.findByText('1001');
    expect(ultimaConsulta()).toMatchObject({ dataIni: '2026-10-13', dataFim: '2026-10-14', incluirAtrasadas: true, page: 1, pageSize: 100 });
    const linha = screen.getByText('1001').closest('tr')!;
    expect(within(linha).getByText('Pendente')).toBeInTheDocument();
    expect(within(linha).getByText('Atrasada')).toBeInTheDocument();           // texto, não só cor
    expect(linha).toHaveClass('row-late');
    const doGestor = screen.getByText('1003').closest('tr')!;
    expect(within(doGestor).getByText('Gestão')).toBeInTheDocument();
    expect(within(doGestor).getByText('Iranildo Silva dos Santos')).toBeInTheDocument();
    const semCand = screen.getByText('1004').closest('tr')!;
    // só o aviso; o motivo aparece quando o usuário clica
    expect(within(semCand).getByText('Requer intervenção')).toBeInTheDocument();
    expect(within(semCand).queryByText(/Limite diário de ordens atingido/)).toBeNull();
    await userEvent.click(within(semCand).getByRole('button', { name: /Requer intervenção/ }));
    expect(within(semCand).getByText(/Limite diário de ordens atingido/)).toBeInTheDocument();
  });

  it('KPIs do período vêm do servidor e clicar em "Em atraso" filtra por atraso', async () => {
    montar();
    await screen.findByText('1001');
    // o número sobe com uma animação curta (contagem); espera o valor final
    await waitFor(() => expect(kpis().getByRole('button', { name: /Em atraso/ })).toHaveTextContent('2'), { timeout: 2000 });
    await userEvent.click(kpis().getByRole('button', { name: /Em atraso/ }));
    await waitFor(() => expect(ultimaConsulta().atrasada).toBe(true));
    expect(kpis().getByRole('button', { name: /Em atraso/ })).toHaveAttribute('aria-pressed', 'true');
  });

  it('seleção de dias específicos é enviada ao servidor (dias não contíguos)', async () => {
    montar({ dataIni: '2026-10-12', dataFim: '2026-10-16' });
    await screen.findByText('1001');
    await userEvent.click(screen.getByRole('button', { name: /^12\/10/ }));
    await userEvent.click(screen.getByRole('button', { name: /^16\/10/ }));
    await waitFor(() => expect(ultimaConsulta().dias).toEqual(['2026-10-12', '2026-10-16']));
    expect(ultimaConsulta().page).toBe(1);
  });

  it('chips de status combinam (Pendente + Em andamento) e "Limpar filtros" restaura', async () => {
    montar();
    await screen.findByText('1001');
    await userEvent.click(chips().getByRole('button', { name: /^Pendente/ }));
    await userEvent.click(chips().getByRole('button', { name: /^Em andamento/ }));
    await waitFor(() => expect(ultimaConsulta().status).toEqual(['Pendente', 'Em andamento']));
    await userEvent.click(screen.getByRole('button', { name: 'Limpar filtros' }));
    await waitFor(() => expect(ultimaConsulta().status).toEqual([]));
  });

  it('busca e responsável usam debounce (uma consulta com o texto final, não uma por tecla)', async () => {
    montar();
    await screen.findByText('1001');
    const antes = fetchPreventivas.mock.calls.length;
    await userEvent.type(screen.getByLabelText('Busca livre'), 'ronda');
    await waitFor(() => expect(ultimaConsulta().busca).toBe('ronda'));
    expect(fetchPreventivas.mock.calls.length - antes).toBeLessThanOrEqual(2);
  });

  it('desligar "incluir atrasadas" refaz a consulta com incluirAtrasadas=false', async () => {
    montar();
    await screen.findByText('1001');
    await userEvent.click(screen.getByLabelText(/Incluir ordens atrasadas/));
    await waitFor(() => expect(ultimaConsulta().incluirAtrasadas).toBe(false));
  });

  it('exportar usa os MESMOS filtros da listagem', async () => {
    exportarPreventivas.mockResolvedValue('hmb_preventivas.xlsx');
    montar();
    await screen.findByText('1001');
    await userEvent.click(chips().getByRole('button', { name: /^Concluída/ }));
    await waitFor(() => expect(ultimaConsulta().status).toEqual(['Concluída']));
    await userEvent.click(screen.getByRole('button', { name: /Exportar Excel/ }));
    await waitFor(() => expect(exportarPreventivas).toHaveBeenCalled());
    expect(exportarPreventivas.mock.calls[0][0]).toMatchObject({ status: ['Concluída'], dataIni: '2026-10-13', dataFim: '2026-10-14' });
    expect(await screen.findByText(/Arquivo gerado: hmb_preventivas.xlsx/)).toBeInTheDocument();
  });

  it('erro do servidor mostra mensagem e permite tentar de novo', async () => {
    fetchPreventivas.mockRejectedValueOnce(Object.assign(new Error('Neovero indisponível no momento. Tente novamente em instantes.'), { name: 'ApiError' }));
    montar();
    expect(await screen.findByRole('alert')).toHaveTextContent(/Neovero indisponível/);
    await userEvent.click(screen.getByRole('button', { name: 'Tentar de novo' }));
    expect(await screen.findByText('1001')).toBeInTheDocument();
  });

  it('sem resultados mostra estado vazio com ação de limpar filtros', async () => {
    fetchPreventivas.mockResolvedValue(resposta([], { total: 0, totais: totais({ total: 0 }) }));
    montar();
    expect(await screen.findByText('Nenhuma ocorrência encontrada')).toBeInTheDocument();
  });

  it('pendências de regras aparecem como aviso com atalho para resolver (não escolhe ninguém ao acaso)', async () => {
    const irParaRegras = vi.fn();
    fetchPreventivas.mockResolvedValue(resposta([item({})], {
      pendencias_regras: [{ regra: 'Rondas diárias', turno: 'Diurno', paridade: 'Par', alias: 'Michael', status: 'ambiguo', motivo: 'x', candidatos: [] }],
    }));
    montar({ onIrParaRegras: irParaRegras });
    expect(await screen.findByText(/1 nome\(s\) em regras de atribuição precisam de confirmação/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Resolver regras' }));
    expect(irParaRegras).toHaveBeenCalled();
  });

  it('exibe vários responsáveis recomendados juntos (regra com dois nomes)', async () => {
    fetchPreventivas.mockResolvedValue(resposta([item({
      recomendado: 'Gustavo Rafael', recomendados: ['Gustavo Rafael', 'Douglas Rodrigues'], cargo: 'Aux. Manutenção',
      alertas: ['Douglas Rodrigues consta na regra para dias Par, mas a escala dele(a) é Ímpar'],
    })]));
    montar();
    expect(await screen.findByText('Gustavo Rafael + Douglas Rodrigues')).toBeInTheDocument();
    expect(screen.getByText(/escala dele\(a\) é Ímpar/)).toBeInTheDocument();
  });
});

describe('filtros locais de planos e colaboradores', () => {
  const planos = [
    { id: 1, descricao: 'PM - MENSAL - SPLIT', tipo: '', periodicidade: '1 Meses', oficina: 'CLIMATIZAÇÃO', procedimento: '', ativo: true },
    { id: 2, descricao: 'PM - ANUAL - VÁCUO', tipo: '', periodicidade: '1 Anos', oficina: 'AR COMPRIMIDO E VÁCUO', procedimento: '', ativo: false },
  ];
  it('planos: busca livre e situação (ativos e inativos)', () => {
    expect(filtrarPlanos(planos, '', '')).toHaveLength(2);
    expect(filtrarPlanos(planos, 'vácuo', '').map((p) => p.id)).toEqual([2]);
    expect(filtrarPlanos(planos, '', 'sim').map((p) => p.id)).toEqual([1]);
    expect(filtrarPlanos(planos, '', 'nao').map((p) => p.id)).toEqual([2]);
  });

  const colab = (extra: object) => ({ funcionario: 'X', cargo: 'Eletricista', turno: 'Diurno', regime: 'Par', horario: '', status: 'Ativo' as const,
    habilidades: [], bloqueado: false, aviso: null, data_admissao: null, data_desligamento: null, fora_da_escala: false,
    executa_os: true, especialidade: 'Elétrica', limite_diario: 14, ...extra });
  it('colaboradores: status, bloqueio e função (executa OS × gestão)', () => {
    const lista = [colab({ funcionario: 'A' }), colab({ funcionario: 'B', status: 'Desligado' }), colab({ funcionario: 'C', bloqueado: true }),
      colab({ funcionario: 'D', cargo: 'Supervisor de Manutenção', executa_os: false })];
    expect(filtrarColaboradores(lista, '', 'Desligado', '', '').map((c) => c.funcionario)).toEqual(['B']);
    expect(filtrarColaboradores(lista, '', '', 'sim', '').map((c) => c.funcionario)).toEqual(['C']);
    expect(filtrarColaboradores(lista, '', '', '', 'nao').map((c) => c.funcionario)).toEqual(['D']);
    expect(filtrarColaboradores(lista, 'supervisor', '', '', '').map((c) => c.funcionario)).toEqual(['D']);
  });
});

describe('PreventivasPanel — filtros ativos e usabilidade', () => {
  it('mostra os filtros em vigor como chips removíveis e "Limpar" os remove todos', async () => {
    montar();
    await screen.findByText('1001');
    expect(screen.queryByRole('list', { name: 'Filtros ativos' })).toBeNull();
    await userEvent.click(chips().getByRole('button', { name: /Pendente/ }));
    await userEvent.selectOptions(screen.getByLabelText('Filtrar por turno'), 'Noturno');
    const lista = await screen.findByRole('list', { name: 'Filtros ativos' });
    expect(within(lista).getByText(/Status: Pendente/)).toBeInTheDocument();
    expect(within(lista).getByText(/Turno: Noturno/)).toBeInTheDocument();
    await userEvent.click(within(lista).getByRole('button', { name: /Remover filtro Turno: Noturno/ }));
    await waitFor(() => expect(ultimaConsulta().turno).toBeUndefined());
    expect(ultimaConsulta().status).toEqual(['Pendente']);
    await userEvent.click(screen.getAllByRole('button', { name: 'Limpar filtros' })[0]);
    await waitFor(() => expect(screen.queryByRole('list', { name: 'Filtros ativos' })).toBeNull());
  });

  it('filtros secundários ficam recolhidos em "Mais filtros" e abrem sob demanda', async () => {
    montar();
    await screen.findByText('1001');
    expect(screen.queryByLabelText('Filtrar por tipo de dia')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Mais filtros' }));
    await userEvent.selectOptions(screen.getByLabelText('Filtrar por tipo de dia'), 'Par');
    await waitFor(() => expect(ultimaConsulta().paridade).toBe('Par'));
    expect(screen.getByText('Dia Par')).toBeInTheDocument();    // e o filtro aplicado aparece como chip
  });

  it('mostra o desvio de cargo (executante com cargo fora do exigido pelo plano) sem alterar a OS', async () => {
    fetchPreventivas.mockResolvedValue(resposta([
      item({ os_vinculada: '2001', plano: 'PM SEMANAL - TESTE DE PARTIDA DOS GRUPOS GERADORES',
        cargo_fora_da_regra: 'Cargo fora da regra: o plano pede Eletricista' }),
      item({ os_vinculada: '2002', status: 'Parada', atrasada: true, os_situacao: 'Em Andamento' }),
    ]));
    montar();
    const linha = (await screen.findByText('2001')).closest('tr')!;
    expect(within(linha).getByText(/o plano pede Eletricista/)).toBeInTheDocument();
    expect(within(screen.getByText('2002').closest('tr')!).getByText('Parada')).toBeInTheDocument();
  });
});

describe('PreventivasPanel — limite diário é aviso, não bloqueio', () => {
  it('OS acima do limite continua escalada: mostra o recomendado + "Requer intervenção" e o motivo só ao clicar', async () => {
    fetchPreventivas.mockResolvedValue(resposta([
      item({ os_vinculada: '3001', status: 'Pendente', responsavel_atual: 'WILLIAN DE SOUZA LOBO', responsavel_status: 'Gestão', revisao: true,
        recomendado: 'Iranildo Silva dos Santos', recomendados: ['Iranildo Silva dos Santos'], cargo: 'Eletricista', escala: 'Diurno | Fixo',
        requer_intervencao: true, motivo_intervencao: 'Limite diário atingido: a OS foi escalada para Iranildo, que passa a ter 15 ordens no dia (limite 14).' }),
    ]));
    montar();
    const linha = (await screen.findByText('3001')).closest('tr')!;
    expect(within(linha).getByText('Iranildo Silva dos Santos')).toBeInTheDocument();          // continua escalada
    expect(within(linha).getByText('Requer intervenção')).toBeInTheDocument();
    expect(within(linha).queryByText(/passa a ter 15 ordens/)).toBeNull();
    await userEvent.click(within(linha).getByRole('button', { name: /Requer intervenção/ }));
    expect(within(linha).getByText(/passa a ter 15 ordens no dia \(limite 14\)/)).toBeInTheDocument();
  });

  it('o indicador "Requer intervenção" filtra pela nova regra e o chip do filtro aparece', async () => {
    montar();
    await screen.findByText('1001');
    await userEvent.click(within(screen.getByLabelText('Resumo do período')).getByRole('button', { name: /Requer intervenção/ }));
    await waitFor(() => expect(ultimaConsulta().requerIntervencao).toBe(true));
    expect(within(await screen.findByRole('list', { name: 'Filtros ativos' })).getByText('Requer intervenção')).toBeInTheDocument();
  });

  it('sem a tela de Regras (usuário comum) não mostra o aviso de nomes pendentes nem o botão Resolver', async () => {
    fetchPreventivas.mockResolvedValue(resposta([item({ os_vinculada: '4001' })], {
      pendencias_regras: [{ regra: 'Rondas', turno: 'Diurno', paridade: 'Par', alias: 'Michael', status: 'ambiguo', motivo: 'dois', candidatos: ['A', 'B'] }] }));
    montar();                                   // sem onIrParaRegras
    await screen.findByText('4001');
    expect(screen.queryByText(/precisam de confirmação/)).toBeNull();
    montar({ onIrParaRegras: () => {} });       // administrador
    expect((await screen.findAllByText(/precisam de confirmação/)).length).toBeGreaterThan(0);
  });
});

describe('PreventivasPanel — coluna Recomendado sem "—" mudo', () => {
  it('mostra o motivo de não haver recomendação (concluída, já atribuída, equipe do Neovero)', async () => {
    fetchPreventivas.mockResolvedValue(resposta([
      item({ os_vinculada: '5001', status: 'Concluída', sem_recomendacao_motivo: 'Concluída' }),
      item({ os_vinculada: '5002', sem_recomendacao_motivo: 'Já atribuída' }),
      item({ os_vinculada: '5003', responsavel_status: 'Equipe do Neovero', sem_recomendacao_motivo: 'Equipe do Neovero (automático)' }),
      item({ os_vinculada: '5004' }),                                           // sem motivo informado: continua "—"
    ]));
    montar();
    for (const [os, texto] of [['5001', 'Concluída'], ['5002', 'Já atribuída'], ['5003', 'Equipe do Neovero (automático)']]) {
      const celulas = within((await screen.findByText(os)).closest('tr')!).getAllByRole('cell');
      expect(celulas[celulas.length - 1]).toHaveTextContent(texto);
    }
    const ultima = within(screen.getByText('5004').closest('tr')!).getAllByRole('cell');
    expect(ultima[ultima.length - 1]).toHaveTextContent('—');
  });
});
