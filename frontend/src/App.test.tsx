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
  me: vi.fn(), login: vi.fn(), logout: vi.fn(), ping: vi.fn(), sessao: vi.fn(), activity: vi.fn(), changePassword: vi.fn(),
  suporteStatus: vi.fn(), suporteEnviar: vi.fn(),
  fetchPreventivas: vi.fn(), fetchPlanos: vi.fn(), fetchColaboradores: vi.fn(), fetchRevisao: vi.fn(),
  fetchRegras: vi.fn(), fetchAtribuicoes: vi.fn(), prefixos: [] as string[],
}));

vi.mock('./shared/api/client', () => ({
  authApi: { me: mocks.me, login: mocks.login, logout: mocks.logout, ping: mocks.ping, sessao: mocks.sessao, activity: mocks.activity, changePassword: mocks.changePassword },
  suporteApi: { status: mocks.suporteStatus, enviar: mocks.suporteEnviar },
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
  mocks.ping.mockResolvedValue({ ok: true, expira_em_s: 1500 });
  mocks.sessao.mockResolvedValue({ expira_em_s: 1500, ociosidade_max_s: 1500, aviso_antes_s: 120 });
  mocks.suporteStatus.mockResolvedValue({ configurado: true, entrega: 'caixa', tipos: {}, limites: { mensagem_max: 5000, mensagem_min: 10, nome_max: 120 } });
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

  it('usuário comum NÃO vê Regras nem Atribuição (só administradores), mas vê Planos', async () => {
    mocks.me.mockResolvedValue(sessao(usuario({})));
    render(<App />);
    const lateral = await screen.findByLabelText('Navegação principal');
    expect(within(lateral).queryByRole('button', { name: /^Regras/ })).toBeNull();
    expect(within(lateral).queryByRole('button', { name: /^Atribuição/ })).toBeNull();
    expect(within(lateral).getByRole('button', { name: /^Planos/ })).toBeInTheDocument();
    expect(within(lateral).queryByText('Configuração')).toBeNull();
  });

  it('link direto para #/u/HMB/regras ou atribuições volta para Preventivas e não pede os dados', async () => {
    window.location.hash = '#/u/HMB/regras';
    mocks.me.mockResolvedValue(sessao(usuario({})));
    render(<App />);
    await screen.findByLabelText('Navegação principal');
    await waitFor(() => expect(window.location.hash).toBe('#/u/HMB/preventivas'));
    expect(mocks.fetchRegras).not.toHaveBeenCalled();
    expect(mocks.fetchAtribuicoes).not.toHaveBeenCalled();
  });

  it('Dev vê as duas unidades e a administração', async () => {
    mocks.me.mockResolvedValue(sessao(usuario({ role: 'dev', is_dev: true, unit: null, unit_name: null, units: [unidadeHETRIN, unidadeHMB] })));
    render(<App />);
    const lateral = await screen.findByLabelText('Navegação principal');
    expect(within(lateral).getByRole('button', { name: 'Hetrin' })).toBeEnabled();
    expect(within(lateral).getByRole('button', { name: 'HMB' })).toBeEnabled();
    expect(within(lateral).getByText('Administração')).toBeInTheDocument();
    expect(within(lateral).getByRole('button', { name: /Utilização/ })).toBeInTheDocument();
    expect(within(lateral).getByRole('button', { name: /Mensagens/ })).toBeInTheDocument();
    expect(within(lateral).getByRole('button', { name: /^Regras/ })).toBeInTheDocument();
    expect(within(lateral).getByRole('button', { name: /^Atribuição/ })).toBeInTheDocument();
  });
});

describe('sessão', () => {
  async function derrubarSessao(corpo: object) {
    const { get } = await import('./shared/api/http');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(corpo), { status: 401 })));
    await get('/api/qualquer').catch(() => {});
  }

  it('quando a sessão cai por inatividade volta ao login explicando o motivo', async () => {
    mocks.me.mockResolvedValue(sessao(usuario({})));
    render(<App />);
    await screen.findByLabelText('Navegação principal');
    await derrubarSessao({ erro: 'Você foi desconectado por inatividade. Entre novamente para continuar.', codigo: 'nao_autenticado', motivo: 'inatividade', mutacao: false });
    expect(await screen.findByRole('heading', { name: 'Entrar' })).toBeInTheDocument();
    expect(screen.getByText(/desconectado por inatividade/)).toBeInTheDocument();
    expect(screen.queryByText(/não foi salva/)).toBeNull();
    vi.unstubAllGlobals();
  });

  it('se a queda pegou uma alteração em andamento, avisa que ela NÃO foi salva', async () => {
    mocks.me.mockResolvedValue(sessao(usuario({})));
    render(<App />);
    await screen.findByLabelText('Navegação principal');
    await derrubarSessao({ erro: 'Você foi desconectado por inatividade. Entre novamente para continuar.', codigo: 'nao_autenticado', motivo: 'inatividade', mutacao: true });
    expect(await screen.findByText(/não foi salva/)).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it('recarregar a página depois da queda não recupera a sessão: continua no login', async () => {
    mocks.me.mockRejectedValue(new ApiError(401, 'Você foi desconectado por inatividade.'));
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Entrar' })).toBeInTheDocument();
    expect(mocks.fetchPreventivas).not.toHaveBeenCalled();
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

describe('aviso de expiração (25 min de inatividade)', () => {
  it('perto de expirar mostra a contagem e "Continuar conectado" renova só com interação real', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      mocks.me.mockResolvedValue(sessao(usuario({})));
      mocks.sessao.mockResolvedValue({ expira_em_s: 90, ociosidade_max_s: 1500, aviso_antes_s: 120 });
      render(<App />);
      await screen.findByLabelText('Navegação principal');
      await vi.advanceTimersByTimeAsync(31_000);          // 1º ciclo: consulta o prazo (não renova)
      expect(mocks.sessao).toHaveBeenCalled();
      expect(mocks.ping).not.toHaveBeenCalled();           // consultar não é atividade
      const aviso = await screen.findByRole('alertdialog', { name: /prestes a expirar/ });
      expect(aviso).toHaveTextContent(/desconectado em/);
      mocks.ping.mockResolvedValue({ ok: true, expira_em_s: 1500 });
      await userEvent.click(within(aviso).getByRole('button', { name: 'Continuar conectado' }));
      expect(mocks.ping).toHaveBeenCalledWith(true);       // batimento com interação real
      await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull());
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('tela de login — logo institucional', () => {
  it('mostra a logo (desktop no painel lateral e mobile no cartão) sem alterar o formulário', async () => {
    mocks.me.mockRejectedValue(new ApiError(401, 'Autenticação necessária.'));
    const { container } = render(<App />);
    await screen.findByRole('heading', { name: 'Entrar' });
    const logos = container.querySelectorAll('.login-logo img[src="/logo.png"]');
    expect(logos.length).toBe(2);
    expect(screen.getByLabelText('Usuário')).toBeInTheDocument();
    expect(screen.getByLabelText('Senha')).toBeInTheDocument();
  });
});

describe('Sugestões e Suporte', () => {
  async function abrirSuporte() {
    mocks.me.mockResolvedValue(sessao(usuario({ username: 'ana@hospital.com' })));
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: /Sugestões e Suporte/ }));
    return screen.findByRole('form', { name: /Enviar mensagem ao suporte/ });
  }

  it('qualquer usuário autenticado vê a página com os quatro campos', async () => {
    const form = await abrirSuporte();
    expect(within(form).getByLabelText('Nome')).toBeInTheDocument();
    expect(within(form).getByLabelText('E-mail de retorno')).toHaveValue('ana@hospital.com');
    expect(within(form).getByRole('radio', { name: 'Sugestão' })).toBeChecked();
    expect(within(form).getByRole('radio', { name: 'Problema' })).toBeInTheDocument();
    expect(within(form).getByRole('radio', { name: 'Melhoria' })).toBeInTheDocument();
    expect(within(form).getByLabelText('Mensagem')).toBeInTheDocument();
  });

  it('valida no cliente antes de enviar', async () => {
    const form = await abrirSuporte();
    await userEvent.clear(within(form).getByLabelText('E-mail de retorno'));
    await userEvent.type(within(form).getByLabelText('E-mail de retorno'), 'sem-arroba');
    await userEvent.type(within(form).getByLabelText('Mensagem'), 'curta');
    await userEvent.click(within(form).getByRole('button', { name: /Enviar/ }));
    expect(await within(form).findByText('Informe um e-mail de retorno válido.')).toBeInTheDocument();
    expect(within(form).getByText(/pelo menos 10 caracteres/)).toBeInTheDocument();
    expect(mocks.suporteEnviar).not.toHaveBeenCalled();
  });

  it('envia uma vez só (botão trava durante o envio) e confirma ao usuário', async () => {
    let resolver: (v: unknown) => void = () => {};
    mocks.suporteEnviar.mockReturnValue(new Promise((r) => { resolver = r; }));
    const form = await abrirSuporte();
    await userEvent.type(within(form).getByLabelText('Nome'), 'Ana Souza');
    await userEvent.type(within(form).getByLabelText('Mensagem'), 'A tela de preventivas demora para carregar.');
    await userEvent.click(within(form).getByRole('radio', { name: 'Problema' }));
    const botao = within(form).getByRole('button', { name: /Enviar/ });
    await userEvent.dblClick(botao);
    expect(mocks.suporteEnviar).toHaveBeenCalledTimes(1);
    expect(mocks.suporteEnviar).toHaveBeenCalledWith(expect.objectContaining({ tipo: 'problema', email: 'ana@hospital.com' }));
    resolver({ ok: true, id: 1, mensagem: 'Mensagem enviada ao suporte.' });
    expect(await screen.findByText('Mensagem enviada ao suporte.')).toBeInTheDocument();
  });

  it('na caixa interna (padrão) não pede e-mail configurado e o botão fica habilitado', async () => {
    const form = await abrirSuporte();
    expect(screen.queryByText(/ainda não está configurado/)).toBeNull();
    expect(within(form).getByRole('button', { name: /Enviar/ })).toBeEnabled();
    expect(screen.getByText(/administração vai ler/)).toBeInTheDocument();
  });

  it('no modo e-mail sem SMTP, avisa e não finge que enviou', async () => {
    mocks.suporteStatus.mockResolvedValue({ configurado: false, entrega: 'email', tipos: {}, limites: { mensagem_max: 5000, mensagem_min: 10, nome_max: 120 } });
    const form = await abrirSuporte();
    expect(await screen.findByText(/ainda não está configurado/)).toBeInTheDocument();
    expect(within(form).getByRole('button', { name: /Enviar/ })).toBeDisabled();
  });
});
