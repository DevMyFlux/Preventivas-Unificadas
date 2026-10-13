import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { ApiError, setCsrfToken, setUnauthorizedHandler } from './shared/api/http';
import type { AuthState, AuthUser } from './shared/api/types';

const unidadeHMB = { codigo: 'HMB' as const, nome: 'HMB', prefixo: '/api/brasilandia' as const };
const unidadeHETRIN = { codigo: 'HETRIN' as const, nome: 'Hetrin', prefixo: '/api/grandmassif' as const };

function usuario(extra: Partial<AuthUser>): AuthUser {
  return {
    id: 1, username: 'ana', display_name: 'Ana', role: 'user', is_dev: false, unit: 'HMB', unit_name: 'HMB',
    must_change_password: false, units: [unidadeHMB], ...extra,
  };
}

const sessao = (u: AuthUser): AuthState => ({ user: u, csrf_token: 'csrf-1' });

const mocks = vi.hoisted(() => ({
  me: vi.fn(), login: vi.fn(), logout: vi.fn(), ping: vi.fn(), activity: vi.fn(), changePassword: vi.fn(),
  fetchPreventivas: vi.fn(), fetchPlanos: vi.fn(), fetchColaboradores: vi.fn(), fetchRevisao: vi.fn(),
  fetchRegras: vi.fn(), fetchAtribuicoes: vi.fn(), prefixos: [] as string[],
}));

vi.mock('./shared/api/client', () => ({
  authApi: { me: mocks.me, login: mocks.login, logout: mocks.logout, ping: mocks.ping, activity: mocks.activity, changePassword: mocks.changePassword },
  buildUnitClient: (prefix: string) => {
    mocks.prefixos.push(prefix);
    return {
      prefix, fetchPreventivas: mocks.fetchPreventivas, fetchPlanos: mocks.fetchPlanos, fetchColaboradores: mocks.fetchColaboradores,
      fetchRevisao: mocks.fetchRevisao, fetchRegras: mocks.fetchRegras, fetchAtribuicoes: mocks.fetchAtribuicoes,
      fetchColaborador: vi.fn(), fetchHabilidades: vi.fn(), exportarPreventivas: vi.fn(), exportarPlanos: vi.fn(),
    };
  },
  preventivasQuery: () => ({}),
}));

const totaisVazios = { total: 0, por_status: {}, por_dia: {}, atrasadas: 0, revisao: 0, sem_candidato: 0, com_recomendacao: 0 };

beforeEach(() => {
  Object.values(mocks).forEach((m) => { if (typeof m === 'function' && 'mockReset' in m) m.mockReset(); });
  mocks.prefixos.length = 0;
  setCsrfToken('');
  setUnauthorizedHandler(null);
  window.location.hash = '';
  mocks.ping.mockResolvedValue({ ok: true });
  mocks.activity.mockResolvedValue({ ok: true });
  mocks.fetchPreventivas.mockResolvedValue({
    total: 0, com_recomendacao: 0, em_atraso: 0, pagina: 1, por_pagina: 100, itens: [], totais: totaisVazios,
    totais_periodo: totaisVazios, periodo: { data_ini: '2026-10-13', data_fim: '2026-10-13', hoje: '2026-10-13' },
    gerado_em: '2026-10-13T12:00:00Z', pendencias_regras: [],
  });
  mocks.fetchPlanos.mockResolvedValue({ total: 0, itens: [] });
  mocks.fetchColaboradores.mockResolvedValue({ total: 0, itens: [] });
  mocks.fetchRevisao.mockResolvedValue({ total: 0, por_status: {}, por_responsavel: [], itens: [], nota: '' });
  mocks.fetchRegras.mockResolvedValue({ regras: [], quadro_ativo: [] });
  mocks.fetchAtribuicoes.mockResolvedValue({ fila: [], propostas: [], integracao: { escrita_habilitada: false, simulacao: true, aviso: '' } });
});

describe('porta de entrada (login)', () => {
  it('sem sessão mostra o login e nenhuma tela da aplicação', async () => {
    mocks.me.mockRejectedValue(new ApiError(401, 'Autenticação necessária.'));
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Entrar' })).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Navegação principal' })).toBeNull();
    expect(mocks.fetchPreventivas).not.toHaveBeenCalled();   // nenhum dado é pedido antes de autenticar
  });

  it('login inválido mostra o erro do servidor e limpa a senha', async () => {
    mocks.me.mockRejectedValue(new ApiError(401, 'x'));
    mocks.login.mockRejectedValue(new ApiError(401, 'Usuário ou senha inválidos.', 'credenciais_invalidas'));
    render(<App />);
    await userEvent.type(await screen.findByLabelText('Usuário'), 'ana');
    await userEvent.type(screen.getByLabelText('Senha'), 'errada123');
    await userEvent.click(screen.getByRole('button', { name: /Entrar/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Usuário ou senha inválidos.');
    expect(screen.getByLabelText('Senha')).toHaveValue('');
    expect(screen.queryByRole('navigation', { name: 'Navegação principal' })).toBeNull();
  });

  it('exige usuário e senha antes de chamar a API', async () => {
    mocks.me.mockRejectedValue(new ApiError(401, 'x'));
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: /Entrar/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/Informe usuário e senha/);
    expect(mocks.login).not.toHaveBeenCalled();
  });

  it('login válido entra na aplicação e guarda o token CSRF só em memória', async () => {
    mocks.me.mockRejectedValue(new ApiError(401, 'x'));
    mocks.login.mockResolvedValue(sessao(usuario({})));
    render(<App />);
    await userEvent.type(await screen.findByLabelText('Usuário'), '  ana ');
    await userEvent.type(screen.getByLabelText('Senha'), 'Senha12345');
    await userEvent.click(screen.getByRole('button', { name: /Entrar/ }));
    expect(await screen.findByRole('navigation', { name: 'Navegação principal' }, { timeout: 3000 }).catch(() => screen.findByLabelText('Navegação principal'))).toBeTruthy();
    expect(mocks.login).toHaveBeenCalledWith('ana', 'Senha12345');
    expect(JSON.stringify(localStorage)).not.toMatch(/csrf-1|Senha12345/);
    expect(JSON.stringify(sessionStorage)).not.toMatch(/csrf-1|Senha12345/);
  });
});

describe('controle de acesso na interface (a segurança real é do backend)', () => {
  it('usuário comum vê só a própria unidade e NÃO vê a área administrativa', async () => {
    mocks.me.mockResolvedValue(sessao(usuario({})));
    render(<App />);
    const lateral = await screen.findByLabelText('Navegação principal');
    expect(within(lateral).getByRole('button', { name: 'HMB' })).toBeDisabled();       // sem troca de unidade
    expect(within(lateral).queryByRole('button', { name: 'Hetrin' })).toBeNull();
    expect(within(lateral).queryByText('Administração')).toBeNull();
    expect(within(lateral).queryByRole('button', { name: /Usuários|Histórico de uso|Relatórios/ })).toBeNull();
    await waitFor(() => expect(mocks.prefixos.every((p) => p === '/api/brasilandia')).toBe(true));
    expect(mocks.prefixos).not.toContain('/api/grandmassif');
  });

  it('mesmo digitando a URL da outra unidade, o usuário comum continua na própria', async () => {
    window.location.hash = '#/u/HETRIN/preventivas';
    mocks.me.mockResolvedValue(sessao(usuario({})));
    render(<App />);
    await screen.findByLabelText('Navegação principal');
    await waitFor(() => expect(mocks.fetchPreventivas).toHaveBeenCalled());
    expect(mocks.prefixos).not.toContain('/api/grandmassif');
  });

  it('mesmo digitando #/admin/..., usuário comum não vê as telas administrativas', async () => {
    window.location.hash = '#/admin/usuarios';
    mocks.me.mockResolvedValue(sessao(usuario({})));
    render(<App />);
    await screen.findByLabelText('Navegação principal');
    expect(screen.queryByRole('heading', { name: 'Usuários e acessos' })).toBeNull();
    expect(screen.queryByText('Novo usuário')).toBeNull();
  });

  it('Dev vê as duas unidades e a administração', async () => {
    mocks.me.mockResolvedValue(sessao(usuario({ role: 'dev', is_dev: true, unit: null, unit_name: null, units: [unidadeHETRIN, unidadeHMB] })));
    render(<App />);
    const lateral = await screen.findByLabelText('Navegação principal');
    expect(within(lateral).getByRole('button', { name: 'Hetrin' })).toBeEnabled();
    expect(within(lateral).getByRole('button', { name: 'HMB' })).toBeEnabled();
    expect(within(lateral).getByText('Administração')).toBeInTheDocument();
    expect(within(lateral).getByRole('button', { name: /Histórico de uso/ })).toBeInTheDocument();
  });
});

describe('sessão', () => {
  it('quando a sessão expira (401) volta ao login com aviso claro', async () => {
    mocks.me.mockResolvedValue(sessao(usuario({})));
    render(<App />);
    await screen.findByLabelText('Navegação principal');
    // simula uma chamada que volta 401: o tratador global registrado pelo AuthProvider é acionado
    const { get } = await import('./shared/api/http');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"erro":"Autenticação necessária."}', { status: 401 })));
    await get('/api/qualquer').catch(() => {});
    expect(await screen.findByRole('heading', { name: 'Entrar' })).toBeInTheDocument();
    expect(screen.getByText(/Sua sessão expirou/)).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it('sair chama o logout no servidor e volta ao login', async () => {
    mocks.me.mockResolvedValue(sessao(usuario({})));
    mocks.logout.mockResolvedValue({ ok: true });
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: /Sair/ }));
    expect(mocks.logout).toHaveBeenCalled();
    expect(await screen.findByRole('heading', { name: 'Entrar' })).toBeInTheDocument();
  });

  it('troca de senha obrigatória abre o diálogo e não pode ser fechada', async () => {
    mocks.me.mockResolvedValue(sessao(usuario({ must_change_password: true })));
    render(<App />);
    const dialogo = await screen.findByRole('dialog', { name: 'Defina uma nova senha' });
    expect(within(dialogo).queryByRole('button', { name: 'Cancelar' })).toBeNull();
    await userEvent.keyboard('{Escape}');
    expect(screen.getByRole('dialog', { name: 'Defina uma nova senha' })).toBeInTheDocument();
  });
});
