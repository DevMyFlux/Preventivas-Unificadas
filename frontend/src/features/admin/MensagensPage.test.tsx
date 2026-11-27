import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../shared/ui/Toast';
import MensagensPage from './MensagensPage';

const mocks = vi.hoisted(() => ({ messages: vi.fn(), count: vi.fn(), set: vi.fn() }));
vi.mock('../../shared/api/adminClient', () => ({
  adminApi: { messages: mocks.messages, messagesCount: mocks.count, setMessageStatus: mocks.set },
}));

const msg = (extra: object) => ({
  id: 1, ts: '2026-10-14T15:00:00Z', username: 'ana.hmb', unit: 'HMB', nome: 'Ana Souza', email: 'ana@hospital.com', tipo: 'problema',
  mensagem: 'A tela de preventivas demora para carregar.', entrega: 'recebida', situacao: 'nova', tratada_em: null, tratada_por: null, ...extra,
});
const pagina = (itens: object[], nao_lidas = 1) => ({ total: itens.length, pagina: 1, por_pagina: 25, itens, nao_lidas });

beforeEach(() => {
  mocks.messages.mockReset().mockResolvedValue(pagina([msg({}), msg({ id: 2, nome: 'Beto', unit: 'HETRIN', tipo: 'sugestao', situacao: 'resolvida', mensagem: 'Sugestão sobre relatórios.' })]));
  mocks.count.mockReset().mockResolvedValue({ nao_lidas: 0 });
  mocks.set.mockReset().mockResolvedValue({});
});

const montar = (onChanged = vi.fn()) => render(<ToastProvider><MensagensPage onChanged={onChanged} /></ToastProvider>);

describe('MensagensPage (caixa do admin)', () => {
  it('lista as mensagens com situação, tipo, unidade e remetente', async () => {
    montar();
    const lista = await screen.findByRole('list', { name: 'Mensagens' });
    const itens = within(lista).getAllByRole('listitem');
    expect(itens).toHaveLength(2);
    expect(within(itens[0]).getByText('Nova')).toBeInTheDocument();
    expect(within(itens[0]).getByText('Problema')).toBeInTheDocument();
    expect(within(itens[0]).getByText('HMB')).toBeInTheDocument();
    expect(within(itens[0]).getByText(/ana\.hmb/)).toBeInTheDocument();
    expect(within(itens[1]).getByText('Resolvida')).toBeInTheDocument();
  });

  it('abrir uma mensagem nova mostra o texto completo, o e-mail de retorno e a marca como lida', async () => {
    const onChanged = vi.fn();
    mocks.count.mockResolvedValue({ nao_lidas: 0 });
    montar(onChanged);
    const primeiro = (await screen.findAllByRole('listitem'))[0];
    await userEvent.click(within(primeiro).getByRole('button', { expanded: false }));
    expect(await within(primeiro).findByRole('link', { name: 'ana@hospital.com' })).toHaveAttribute('href', 'mailto:ana@hospital.com');
    await waitFor(() => expect(mocks.set).toHaveBeenCalledWith(1, 'lida'));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(0));
  });

  it('permite marcar como resolvida e filtrar por situação', async () => {
    mocks.messages.mockResolvedValue(pagina([msg({ situacao: 'lida', tratada_por: 'dev', tratada_em: '2026-10-14T16:00:00Z' })], 0));
    montar();
    const item = (await screen.findAllByRole('listitem'))[0];
    await userEvent.click(within(item).getByRole('button', { expanded: false }));
    await userEvent.click(await within(item).findByRole('button', { name: 'Marcar como resolvida' }));
    await waitFor(() => expect(mocks.set).toHaveBeenCalledWith(1, 'resolvida'));
    await userEvent.click(screen.getByRole('button', { name: 'Novas' }));
    await waitFor(() => expect(mocks.messages).toHaveBeenLastCalledWith(expect.objectContaining({ situacao: 'nova', page: 1 })));
  });

  it('caixa vazia explica de onde vêm as mensagens', async () => {
    mocks.messages.mockResolvedValue(pagina([], 0));
    montar();
    expect(await screen.findByText('Nenhuma mensagem')).toBeInTheDocument();
  });
});
