import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { UnitApiClient } from '../../shared/api/client';
import { ToastProvider } from '../../shared/ui/Toast';
import RevisaoPanel from './RevisaoPanel';

const fetchRevisao = vi.fn();
const fetchTransferencias = vi.fn();
const anotarMotivoTransferencia = vi.fn();
const client = { prefix: '/api/grandmassif', fetchRevisao, fetchTransferencias, anotarMotivoTransferencia } as unknown as UnitApiClient;

const revisao = {
  total: 1, por_status: { Gestão: 1 }, por_responsavel: [{ status: 'Gestão', responsavel: 'WILLIAN DE SOUZA LOBO', ordens: 1 }],
  itens: [{ os_numero: '2001', data_prev: '14/10/2026', plano: 'PM - X', oficina: 'ELÉTRICA', situacao: 'Aberta', status: 'Pendente', atrasada: false,
    responsavel_atual: 'WILLIAN DE SOUZA LOBO', responsavel_status: 'Gestão', responsavel_cadastro: 'William de Souza Lobo', data_desligamento: null }],
  cargo_fora_da_regra: [{ os_numero: '3001', data_prev: '14/10/2026', plano: 'PM SEMANAL - TESTE DE PARTIDA DOS GRUPOS GERADORES',
    status: 'Pendente', responsavel_atual: 'AUX ELETRICO A', desvio: 'Cargo fora da regra: o plano pede Eletricista' }],
  planos_responsavel_invalido: [
    { plano_id: 7, plano: 'PM - LIMPEZA FANCOILS BL1 - DIA 01', responsavel_id: 12, responsavel_nome: 'CARLOS AURELIO DE CARVALHO', status: 'Desligado', os_abertas: 3 },
    { plano_id: 8, plano: 'PM - OUTRO', responsavel_id: 99, responsavel_nome: null, status: 'Não identificado', os_abertas: 0 },
  ],
  nota: 'Somente leitura',
};

beforeEach(() => {
  fetchRevisao.mockReset().mockResolvedValue(revisao);
  fetchTransferencias.mockReset().mockResolvedValue({
    total: 1, nota: 'Mudanças anteriores ao monitoramento não são conhecidas.',
    itens: [{ id: 5, os_numero: '202614226', os_id: 1, plano: 'PM - X', de: 'MAIKON JONATHAS', para: 'WILLIAN MIRANDA', tipo: 'transferencia',
      observado_em: '2026-10-14T15:00:00Z', motivo: null, motivo_por: null }],
  });
  anotarMotivoTransferencia.mockReset().mockResolvedValue({});
});

const montar = () => render(<ToastProvider><RevisaoPanel client={client} /></ToastProvider>);

describe('RevisaoPanel', () => {
  it('abas mostram contagens e separam ordens, planos inválidos e cargo fora da regra', async () => {
    montar();
    await screen.findByText('2001');
    const abas = screen.getByRole('tablist', { name: 'Seções da revisão' });
    expect(within(abas).getByRole('tab', { name: /Planos com responsável inválido/ })).toHaveTextContent('2');
    expect(within(abas).getByRole('tab', { name: /Cargo fora da regra/ })).toHaveTextContent('1');

    await userEvent.click(within(abas).getByRole('tab', { name: /Planos com responsável inválido/ }));
    const linhaPlano = (await screen.findByText('PM - LIMPEZA FANCOILS BL1 - DIA 01')).closest('tr')!;
    expect(within(linhaPlano).getByText('Desligado')).toBeInTheDocument();
    expect(within(linhaPlano).getByText('CARLOS AURELIO DE CARVALHO')).toBeInTheDocument();
    expect(screen.getByText('Não identificado')).toBeInTheDocument();       // sem OS para resolver o nome: não presume nada

    await userEvent.click(within(abas).getByRole('tab', { name: /Cargo fora da regra/ }));
    expect(await screen.findByText(/o plano pede Eletricista/)).toBeInTheDocument();
    expect(screen.getByText(/nenhuma OS é reatribuída/)).toBeInTheDocument();
  });

  it('transferências mostram de → para e permitem anotar o motivo', async () => {
    montar();
    await screen.findByText('2001');
    await userEvent.click(screen.getByRole('tab', { name: 'Transferências' }));
    const linha = (await screen.findByText('202614226')).closest('tr')!;
    expect(within(linha).getByText('MAIKON JONATHAS')).toBeInTheDocument();
    expect(within(linha).getByText('WILLIAN MIRANDA')).toBeInTheDocument();
    expect(within(linha).getByText('não informado')).toBeInTheDocument();
    await userEvent.click(within(linha).getByRole('button', { name: /Anotar motivo da OS 202614226/ }));
    await userEvent.type(screen.getByLabelText(/Motivo da transferência da OS 202614226/), 'Troca de turno');
    await userEvent.click(screen.getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(anotarMotivoTransferencia).toHaveBeenCalledWith(5, 'Troca de turno'));
  });
});
