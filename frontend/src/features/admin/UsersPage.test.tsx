import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ToastProvider } from '../../shared/ui/Toast';
import UsersPage from './UsersPage';

const mocks = vi.hoisted(() => ({ listUsers: vi.fn(), createUser: vi.fn(), updateUser: vi.fn(), setActive: vi.fn() }));
vi.mock('../../shared/api/adminClient', () => ({
  adminApi: { listUsers: mocks.listUsers, createUser: mocks.createUser, updateUser: mocks.updateUser, setActive: mocks.setActive,
    resetPassword: vi.fn(), userDetail: vi.fn(), unlockUser: vi.fn() },
}));
vi.mock('../../app/AuthContext', () => ({ useAuth: () => ({ user: { id: 1, username: 'dev@demo.local', is_dev: true } }) }));

const base = { role: 'user', is_dev: false, must_change_password: false, units: [], is_active: true, created_at: '2026-10-01T00:00:00Z', created_by: 'dev',
  last_login_at: null, deactivated_at: null, locked_until: null, sessoes_abertas: 0 };
const usuarios = [
  { ...base, id: 1, username: 'dev@demo.local', display_name: 'Admin Demo', role: 'dev', is_dev: true, unit: null, unit_name: null },
  { ...base, id: 2, username: 'outro.admin@demo.local', display_name: 'Outro Admin', role: 'dev', is_dev: true, unit: null, unit_name: null },
  { ...base, id: 3, username: 'ana@demo.local', display_name: 'Ana', unit: 'HMB', unit_name: 'HMB' },
];

beforeEach(() => {
  mocks.listUsers.mockReset().mockResolvedValue({ itens: usuarios, unidades: [{ codigo: 'HMB', nome: 'HMB' }, { codigo: 'HETRIN', nome: 'Hetrin' }] });
  mocks.createUser.mockReset().mockResolvedValue({});
  mocks.updateUser.mockReset().mockResolvedValue({});
});

const montar = () => render(<ToastProvider><UsersPage /></ToastProvider>);

describe('UsersPage — administradores', () => {
  it('lista administradores com o rótulo certo; a própria conta não tem Desativar nem outro administrador tem Senha', async () => {
    montar();
    await screen.findByText('Outro Admin');
    expect(screen.getAllByText('Administrador · todas as unidades')).toHaveLength(2);
    const propria = screen.getByText('Admin Demo').closest('tr')!;
    expect(within(propria).queryByRole('button', { name: 'Desativar' })).toBeNull();           // não desativa a si mesmo
    expect(within(propria).getByRole('button', { name: 'Senha' })).toBeInTheDocument();         // mas troca a própria senha
    const outro = screen.getByText('Outro Admin').closest('tr')!;
    expect(within(outro).getByRole('button', { name: 'Desativar' })).toBeInTheDocument();       // pode desativar outro administrador
    expect(within(outro).queryByRole('button', { name: 'Senha' })).toBeNull();                  // a senha dele é só dele
  });

  it('ao criar, o perfil Administrador esconde a unidade e envia role "dev" sem unidade', async () => {
    montar();
    await userEvent.click(await screen.findByRole('button', { name: /Novo usuário/ }));
    const form = await screen.findByRole('dialog');
    expect(within(form).getByLabelText('Unidade vinculada')).toBeInTheDocument();               // padrão: usuário comum
    await userEvent.selectOptions(within(form).getByLabelText('Perfil'), 'dev');
    expect(within(form).queryByLabelText('Unidade vinculada')).toBeNull();
    expect(within(form).getByText(/Só administradores podem criar outro administrador/)).toBeInTheDocument();
    await userEvent.type(within(form).getByLabelText('Usuário (login)'), 'novo.admin@demo.local');
    await userEvent.type(within(form).getByLabelText('Nome de exibição'), 'Novo Admin');
    await userEvent.type(within(form).getByLabelText('Senha inicial'), 'SenhaForte123');
    await userEvent.click(within(form).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(mocks.createUser).toHaveBeenCalledTimes(1));
    const corpo = mocks.createUser.mock.calls[0][0];
    expect(corpo).toMatchObject({ username: 'novo.admin@demo.local', role: 'dev', display_name: 'Novo Admin' });
    expect('unit' in corpo).toBe(false);
  });

  it('usuário comum continua sendo criado com unidade e perfil "user"', async () => {
    montar();
    await userEvent.click(await screen.findByRole('button', { name: /Novo usuário/ }));
    const form = await screen.findByRole('dialog');
    await userEvent.type(within(form).getByLabelText('Usuário (login)'), 'comum@demo.local');
    await userEvent.type(within(form).getByLabelText('Senha inicial'), 'SenhaForte123');
    await userEvent.selectOptions(within(form).getByLabelText('Unidade vinculada'), 'HETRIN');
    await userEvent.click(within(form).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(mocks.createUser).toHaveBeenCalledWith(expect.objectContaining({ role: 'user', unit: 'HETRIN' })));
  });

  it('editar um administrador não pede unidade e só envia o nome', async () => {
    montar();
    const outro = (await screen.findByText('Outro Admin')).closest('tr')!;
    await userEvent.click(within(outro).getByRole('button', { name: 'Editar' }));
    const form = await screen.findByRole('dialog');
    expect(within(form).queryByLabelText('Unidade vinculada')).toBeNull();
    await userEvent.click(within(form).getByRole('button', { name: 'Salvar' }));
    await waitFor(() => expect(mocks.updateUser).toHaveBeenCalledWith(2, { display_name: 'Outro Admin' }));
  });
});
