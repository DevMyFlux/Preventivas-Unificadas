import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from './AuthContext';
import { PAGINAS_ADMIN, useRota } from './route';
import type { PaginaAdmin, PaginaUnidade, Rota } from './route';
import AuditPage from '../features/admin/AuditPage';
import ReportsPage from '../features/admin/ReportsPage';
import UsersPage from '../features/admin/UsersPage';
import ChangePasswordDialog from '../features/auth/ChangePasswordDialog';
import AtribuicoesPanel from '../features/unit/AtribuicoesPanel';
import ColaboradoresPanel from '../features/unit/ColaboradoresPanel';
import PlanosPanel from '../features/unit/PlanosPanel';
import PreventivasPanel from '../features/unit/PreventivasPanel';
import RegrasPanel from '../features/unit/RegrasPanel';
import RevisaoPanel from '../features/unit/RevisaoPanel';
import { authApi, buildUnitClient } from '../shared/api/client';
import type { UnitApiClient } from '../shared/api/client';
import type { UnitInfo } from '../shared/api/types';
import Icon from '../shared/ui/Icon';
import type { IconName } from '../shared/ui/Icon';
import { Button } from '../shared/ui/ui';
import { addDays, firstOfMonth, lastOfMonth, todayISO, validateDateRange } from '../shared/utils/dateUtils';

const NAV_UNIDADE: { key: PaginaUnidade; label: string; icon: IconName }[] = [
  { key: 'preventivas', label: 'Preventivas', icon: 'calendar' },
  { key: 'revisao', label: 'Revisão', icon: 'alert' },
  { key: 'atribuicoes', label: 'Atribuição', icon: 'link' },
  { key: 'colaboradores', label: 'Colaboradores', icon: 'users' },
  { key: 'planos', label: 'Planos', icon: 'list' },
  { key: 'regras', label: 'Regras', icon: 'sliders' },
];

const NAV_ADMIN: { key: PaginaAdmin; label: string; icon: IconName }[] = [
  { key: 'usuarios', label: 'Usuários', icon: 'shield' },
  { key: 'auditoria', label: 'Histórico de uso', icon: 'activity' },
  { key: 'relatorios', label: 'Relatórios', icon: 'file' },
];

const TITULOS: Record<string, string> = {
  preventivas: 'Preventivas', revisao: 'Revisão de responsáveis', atribuicoes: 'Atribuição de executantes', colaboradores: 'Colaboradores',
  planos: 'Planos de manutenção', regras: 'Regras de atribuição', usuarios: 'Usuários e acessos', auditoria: 'Histórico de utilização',
  relatorios: 'Relatórios de utilização',
};

const COR_UNIDADE: Record<string, string> = { HETRIN: 'var(--unit-hetrin)', HMB: 'var(--unit-hmb)' };

function useTema(): [string, () => void] {
  const [tema, setTema] = useState<string>(() => {
    try {
      const salvo = localStorage.getItem('myflux-tema');
      if (salvo) return salvo;
    } catch { /* storage indisponível: usa a preferência do sistema */ }
    return 'light';   // padrão claro; a escolha do usuário fica salva
  });
  useEffect(() => {
    document.documentElement.dataset.theme = tema;
    try { localStorage.setItem('myflux-tema', tema); } catch { /* ignora */ }
  }, [tema]);
  return [tema, () => setTema((t) => (t === 'dark' ? 'light' : 'dark'))];
}

/** Heartbeat: só informa "em uso" se a aba está visível e houve interação nos últimos 5 minutos. */
function useHeartbeat() {
  const ultimaInteracao = useRef(Date.now());
  useEffect(() => {
    const marcar = () => { ultimaInteracao.current = Date.now(); };
    const eventos = ['mousedown', 'keydown', 'touchstart', 'scroll'] as const;
    eventos.forEach((e) => window.addEventListener(e, marcar, { passive: true }));
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible' && Date.now() - ultimaInteracao.current < 5 * 60_000) {
        authApi.ping().catch(() => { /* 401 já é tratado globalmente */ });
      }
    }, 60_000);
    return () => { eventos.forEach((e) => window.removeEventListener(e, marcar)); window.clearInterval(id); };
  }, []);
}

export default function Shell() {
  const { user, logout } = useAuth();
  const u = user!;
  const unidades = u.units;
  const padrao = unidades[0]?.codigo ?? 'HMB';
  const [rota, navegar] = useRota(padrao);
  const [tema, alternarTema] = useTema();
  const [menuAberto, setMenuAberto] = useState(false);
  const [senhaAberta, setSenhaAberta] = useState(false);
  const [contagens, setContagens] = useState<Record<string, number | undefined>>({});
  useHeartbeat();

  // período global
  const hoje = todayISO();
  const [inicio, setInicio] = useState(hoje);
  const [fim, setFim] = useState(hoje);
  const [periodo, setPeriodo] = useState({ dataIni: hoje, dataFim: hoje });
  const [erroPeriodo, setErroPeriodo] = useState<string | null>(null);

  const aplicar = (ini: string, f: string) => {
    const err = validateDateRange(ini, f);
    setErroPeriodo(err);
    if (!err && ini && f) setPeriodo({ dataIni: ini, dataFim: f });
  };
  const preset = (ini: string, f: string) => { setInicio(ini); setFim(f); aplicar(ini, f); };

  // A unidade da rota só vale se o usuário tem acesso a ela (o backend também recusa com 403)
  const unidadeAtual: UnitInfo | undefined = useMemo(
    () => (rota.tipo === 'unidade' ? unidades.find((x) => x.codigo === rota.unidade) : undefined) ?? unidades[0],
    [rota, unidades]);
  const client: UnitApiClient | null = useMemo(() => (unidadeAtual ? buildUnitClient(unidadeAtual.prefixo) : null), [unidadeAtual]);

  // Rota que o usuário não pode usar (admin sem ser Dev, unidade que não é a dele): volta para a dele.
  // É só conveniência de navegação — o backend recusa (403) de qualquer forma.
  const proibida = (rota.tipo === 'admin' && !u.is_dev) || (rota.tipo === 'unidade' && !unidades.some((x) => x.codigo === rota.unidade));
  useEffect(() => {
    if (proibida) navegar({ tipo: 'unidade', unidade: padrao, pagina: 'preventivas' });
  }, [proibida, navegar, padrao]);

  // registra a navegação entre módulos (alimenta o histórico de uso)
  useEffect(() => {
    const modulo = rota.tipo === 'admin' ? 'admin' : ({ atribuicoes: 'distribuicao', revisao: 'distribuicao' } as Record<string, string>)[rota.pagina] ?? rota.pagina;
    authApi.activity(modulo, rota.tipo === 'unidade' ? unidadeAtual?.codigo : undefined).catch(() => {});
  }, [rota, unidadeAtual?.codigo]);

  useEffect(() => { document.title = `${TITULOS[rota.pagina] ?? 'MyFlux'} · MyFlux Preventivas`; }, [rota]);
  useEffect(() => setMenuAberto(false), [rota]);

  const irPara = useCallback((r: Rota) => navegar(r), [navegar]);
  const setCount = (chave: string) => (n: number) => setContagens((c) => (c[chave] === n ? c : { ...c, [chave]: n }));
  const paginaUnidade = rota.tipo === 'unidade' ? rota.pagina : 'preventivas';
  const iniciais = (u.display_name || u.username).split(/\s+/).map((p) => p[0]).slice(0, 2).join('').toUpperCase();
  const mostraPeriodo = rota.tipo === 'unidade' && ['preventivas', 'colaboradores', 'atribuicoes'].includes(rota.pagina);

  return (
    <div className="app">
      <a href="#conteudo" className="skip-link" onClick={(e) => { e.preventDefault(); document.getElementById('conteudo')?.focus(); }}>Ir para o conteúdo</a>
      {menuAberto && <div className="scrim" onClick={() => setMenuAberto(false)} aria-hidden="true" />}

      <aside className={`sidebar${menuAberto ? ' open' : ''}`} aria-label="Navegação principal">
        <div className="side-brand">
          <span className="side-logo"><img src="/logo.png" alt="MyFlux" /></span>
          <div><div className="side-name">Preventivas</div><div className="side-sub">Manutenção hospitalar</div></div>
        </div>

        <div className="side-label">{unidades.length > 1 ? 'Unidade' : 'Sua unidade'}</div>
        <div className="unit-switch" role="group" aria-label="Unidade">
          {unidades.map((x) => (
            <button key={x.codigo} type="button" className="unit-btn" aria-pressed={unidadeAtual?.codigo === x.codigo && rota.tipo === 'unidade'}
              disabled={unidades.length === 1} onClick={() => irPara({ tipo: 'unidade', unidade: x.codigo, pagina: paginaUnidade })}>
              <span className="unit-dot" style={{ background: COR_UNIDADE[x.codigo] }} />{x.nome}
            </button>
          ))}
        </div>

        <nav className="nav" aria-label="Módulos da unidade">
          {NAV_UNIDADE.map((n) => (
            <button key={n.key} type="button" className="nav-item" aria-current={rota.tipo === 'unidade' && rota.pagina === n.key ? 'page' : undefined}
              onClick={() => irPara({ tipo: 'unidade', unidade: unidadeAtual?.codigo ?? padrao, pagina: n.key })}>
              <Icon name={n.icon} size={17} />{n.label}
              {contagens[`${unidadeAtual?.codigo}:${n.key}`] != null && <span className="count">{contagens[`${unidadeAtual?.codigo}:${n.key}`]}</span>}
            </button>
          ))}
        </nav>

        {u.is_dev && (
          <>
            <div className="side-label">Administração</div>
            <nav className="nav" aria-label="Administração">
              {NAV_ADMIN.map((n) => (
                <button key={n.key} type="button" className="nav-item" aria-current={rota.tipo === 'admin' && rota.pagina === n.key ? 'page' : undefined}
                  onClick={() => irPara({ tipo: 'admin', pagina: PAGINAS_ADMIN.find((p) => p === n.key)! })}>
                  <Icon name={n.icon} size={17} />{n.label}
                </button>
              ))}
            </nav>
          </>
        )}

        <div className="side-foot">
          <div className="user-card">
            <div className="avatar" aria-hidden="true">{iniciais}</div>
            <div style={{ minWidth: 0 }}>
              <div className="user-name cell-clip">{u.display_name || u.username}</div>
              <div className="user-meta">{u.is_dev ? 'Administrador (Dev)' : u.unit_name}</div>
            </div>
          </div>
          <div className="row" style={{ gap: 4, marginTop: 4 }}>
            <button type="button" className="nav-item" style={{ flex: 1 }} onClick={() => setSenhaAberta(true)}><Icon name="key" size={16} />Senha</button>
            <button type="button" className="nav-item" style={{ flex: 1 }} onClick={() => logout()}><Icon name="logout" size={16} />Sair</button>
          </div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <Button className="menu-btn" variant="ghost" icon="menu" aria-label="Abrir menu" onClick={() => setMenuAberto(true)} />
          <h1>{proibida ? '' : TITULOS[rota.pagina]}</h1>
          {rota.tipo === 'unidade' && unidadeAtual && <span className="muted">{unidadeAtual.nome}</span>}
          <span className="grow" />
          {mostraPeriodo && (
            <form className="row" onSubmit={(e) => { e.preventDefault(); aplicar(inicio, fim); }} aria-label="Período">
              <input type="date" className="input" style={{ width: 138 }} aria-label="Data inicial" value={inicio} onChange={(e) => setInicio(e.target.value)} />
              <span className="muted">a</span>
              <input type="date" className="input" style={{ width: 138 }} aria-label="Data final" value={fim} onChange={(e) => setFim(e.target.value)} />
              <Button variant="primary" size="sm" type="submit">Aplicar</Button>
              <Button type="button" size="sm" onClick={() => preset(hoje, hoje)}>Hoje</Button>
              <Button type="button" size="sm" onClick={() => preset(addDays(hoje, -6), hoje)}>7 dias</Button>
              <Button type="button" size="sm" onClick={() => preset(firstOfMonth(hoje), lastOfMonth(hoje))}>Mês</Button>
              {erroPeriodo && <span role="alert" style={{ color: 'var(--danger-text)', fontWeight: 600, fontSize: 12.5 }}>{erroPeriodo}</span>}
            </form>
          )}
          <Button variant="ghost" icon={tema === 'dark' ? 'sun' : 'moon'} aria-label={tema === 'dark' ? 'Usar tema claro' : 'Usar tema escuro'} onClick={alternarTema} />
        </header>

        <main className="page" id="conteudo" tabIndex={-1}>
          {proibida ? null : rota.tipo === 'admin' ? (
            !u.is_dev ? null :
            rota.pagina === 'usuarios' ? <UsersPage /> : rota.pagina === 'auditoria' ? <AuditPage /> : <ReportsPage />
          ) : client && unidadeAtual ? (
            <UnidadeConteudo key={unidadeAtual.codigo} codigo={unidadeAtual.codigo} client={client} pagina={rota.pagina}
              periodo={periodo} setCount={setCount} irPara={(p) => irPara({ tipo: 'unidade', unidade: unidadeAtual.codigo, pagina: p })} />
          ) : null}
        </main>
      </div>

      {(senhaAberta || u.must_change_password) && <ChangePasswordDialog obrigatoria={u.must_change_password} onClose={() => setSenhaAberta(false)} />}
    </div>
  );
}

function UnidadeConteudo({ codigo, client, pagina, periodo, setCount, irPara }: {
  codigo: string; client: UnitApiClient; pagina: PaginaUnidade; periodo: { dataIni: string; dataFim: string };
  setCount: (chave: string) => (n: number) => void; irPara: (p: PaginaUnidade) => void;
}) {
  const [versaoRegras, setVersaoRegras] = useState(0);
  const contar = (p: string) => setCount(`${codigo}:${p}`);
  // painéis ficam montados (display none) para preservar filtros e dados ao trocar de módulo
  const visivel = (p: PaginaUnidade) => ({ display: pagina === p ? 'block' : 'none' });
  return (
    <>
      <div style={visivel('preventivas')}>
        <PreventivasPanel key={versaoRegras} client={client} dataIni={periodo.dataIni} dataFim={periodo.dataFim}
          onCount={contar('preventivas')} onIrParaRegras={() => irPara('regras')} />
      </div>
      <div style={visivel('revisao')}><RevisaoPanel client={client} onCount={contar('revisao')} /></div>
      <div style={visivel('atribuicoes')}><AtribuicoesPanel client={client} dataIni={periodo.dataIni} dataFim={periodo.dataFim} /></div>
      <div style={visivel('colaboradores')}><ColaboradoresPanel client={client} dataIni={periodo.dataIni} dataFim={periodo.dataFim} onCount={contar('colaboradores')} /></div>
      <div style={visivel('planos')}><PlanosPanel client={client} onCount={contar('planos')} /></div>
      <div style={visivel('regras')}><RegrasPanel client={client} onChanged={() => setVersaoRegras((v) => v + 1)} /></div>
    </>
  );
}
