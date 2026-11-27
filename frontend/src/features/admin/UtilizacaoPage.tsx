import { useState } from 'react';
import { adminApi } from '../../shared/api/adminClient';
import { mensagemDeErro } from '../../shared/api/http';
import type { AuditFilters, UsageSummary } from '../../shared/api/types';
import { useAsync, useDebounced } from '../../shared/hooks/useAsync';
import { useToast } from '../../shared/ui/Toast';
import { Alert, Button, Chip, EmptyState, KpiCard, PageHead, Segmented, TableSkeleton } from '../../shared/ui/ui';
import { addDays, formatBR, formatDateTimeBR, todayISO } from '../../shared/utils/dateUtils';
import { NOME_MODULO } from '../../shared/utils/status';
import AuditPage from './AuditPage';
import UsuarioDetalhe, { ESTADO_AGORA, formatarMinutos, textoDaSessao, tomDoEncerramento } from './UsuarioDetalhe';

type Aba = 'geral' | 'usuarios' | 'sessoes' | 'eventos';

export default function UtilizacaoPage() {
  const toast = useToast();
  const [dataIni, setDataIni] = useState(addDays(todayISO(), -30));
  const [dataFim, setDataFim] = useState(todayISO());
  const [unit, setUnit] = useState('');
  const [username, setUsername] = useState('');
  const [aba, setAba] = useState<Aba>('geral');
  const [exportando, setExportando] = useState(false);
  const [usuarioAberto, setUsuarioAberto] = useState<number | null>(null);
  const userD = useDebounced(username);

  const filtros: AuditFilters = { dataIni, dataFim, unit: unit || undefined, username: userD || undefined };
  const chave = JSON.stringify(filtros);
  const resumo = useAsync(() => adminApi.summary(filtros), [chave], aba === 'geral');
  const uso = useAsync(() => adminApi.usage(filtros), [chave], aba === 'geral' || aba === 'usuarios');
  const sessoes = useAsync(() => adminApi.sessions(filtros), [chave], aba === 'sessoes');

  const exportar = async (fmt: 'xlsx' | 'csv') => {
    setExportando(true);
    try {
      toast.success(`Arquivo gerado: ${await adminApi.exportUsage(filtros, fmt)}`);
    } catch (e) {
      toast.error(mensagemDeErro(e));
    } finally {
      setExportando(false);
    }
  };
  const atualizar = () => { resumo.reload(); uso.reload(); sessoes.reload(); };

  const r = resumo.data;
  const ind = uso.data?.indicadores;
  const erro = resumo.error ?? uso.error ?? sessoes.error;
  const filtrosAtivos = [unit && `Unidade ${unit}`, userD && `Usuário “${userD}”`].filter(Boolean) as string[];

  return (
    <div className="stack">
      <PageHead
        title="Utilização do sistema"
        subtitle="Quem usa, por quanto tempo e como as sessões terminam — separando tempo conectado de tempo realmente ativo."
        actions={<>
          <Button icon="refresh" onClick={atualizar} loading={resumo.loading || uso.loading}>Atualizar</Button>
          <Button icon="download" onClick={() => exportar('xlsx')} loading={exportando}>Excel</Button>
          <Button icon="download" onClick={() => exportar('csv')} disabled={exportando}>CSV</Button>
        </>}
      />

      <section className="card row" aria-label="Filtros">
        <div className="field"><label htmlFor="r-ini">De</label><input id="r-ini" type="date" className="input" value={dataIni} max={dataFim} onChange={(e) => setDataIni(e.target.value)} /></div>
        <div className="field"><label htmlFor="r-fim">Até</label><input id="r-fim" type="date" className="input" value={dataFim} min={dataIni} onChange={(e) => setDataFim(e.target.value)} /></div>
        <div className="field"><label htmlFor="r-unit">Unidade</label>
          <select id="r-unit" className="select" value={unit} onChange={(e) => setUnit(e.target.value)}>
            <option value="">Todas</option><option value="HETRIN">Hetrin</option><option value="HMB">HMB</option>
          </select></div>
        <div className="field"><label htmlFor="r-user">Usuário</label>
          <input id="r-user" className="input" placeholder="parte do login" value={username} onChange={(e) => setUsername(e.target.value)} /></div>
        {filtrosAtivos.length > 0 && (
          <div className="chips-ativos" aria-label="Filtros ativos">
            {filtrosAtivos.map((f) => <span className="chip c-primary nodot" key={f}>{f}</span>)}
            <button type="button" className="link-btn" onClick={() => { setUnit(''); setUsername(''); }}>Limpar filtros</button>
          </div>
        )}
      </section>

      <Segmented label="Seção" value={aba} onChange={setAba} options={[
        { key: 'geral', label: 'Visão geral' }, { key: 'usuarios', label: 'Por usuário' },
        { key: 'sessoes', label: 'Sessões' }, { key: 'eventos', label: 'Eventos' }]} />

      {erro && aba !== 'eventos' && <Alert tone="danger" action={<Button size="sm" onClick={atualizar}>Tentar de novo</Button>}>{erro}</Alert>}

      {aba === 'geral' && (
        <>
          <Alert tone="info">
            <b>Período analisado:</b> {formatBR(dataIni)} a {formatBR(dataFim)}
            {uso.data?.cobertura_desde && <> · a coleta de utilização começou em {formatDateTimeBR(uso.data.cobertura_desde)}</>}.{' '}
            Sessões sem atividade por {uso.data?.limite_inatividade_min ?? 25} min são encerradas pelo servidor.
            Quem não aparece no período tem apenas “sem utilização registrada” — isso <b>não prova</b> que não usa o sistema.
          </Alert>

          <section className="kpis" aria-label="Indicadores">
            <KpiCard label="Ativos agora" value={ind?.usuarios_ativos_agora ?? null} tone="success" loading={uso.loading && !ind}
              hint={ind ? `${ind.usuarios_ociosos_agora} conectado(s) e ocioso(s)` : undefined} />
            <KpiCard label="Acessos no período" value={ind?.acessos ?? null} tone="primary" loading={uso.loading && !ind} />
            <KpiCard label="Tempo em sessão" value={ind ? formatarMinutos(ind.tempo_sessao_min) : null} tone="info" loading={uso.loading && !ind} />
            <KpiCard label="Tempo ativo (estimado)" value={ind ? formatarMinutos(ind.tempo_ativo_min) : null} tone="success" loading={uso.loading && !ind} />
            <KpiCard label="Tempo ocioso" value={ind ? formatarMinutos(ind.tempo_ocioso_min) : null} tone="warning" loading={uso.loading && !ind} />
            <KpiCard label="Encerradas por inatividade" value={ind?.sessoes_por_inatividade ?? null} tone="purple" loading={uso.loading && !ind} />
            <KpiCard label="Sem utilização registrada" value={ind?.usuarios_sem_utilizacao_registrada ?? null} tone="info" loading={uso.loading && !ind}
              hint={ind ? `de ${ind.usuarios_cadastrados} cadastrados` : undefined} />
          </section>

          {uso.data && uso.data.ativos_agora.length > 0 && (
            <section className="card stack" aria-label="Conectados agora">
              <div className="card-title">Conectados agora</div>
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                {uso.data.ativos_agora.map((a) => (
                  <button key={a.id} type="button" className="chip-btn" onClick={() => setUsuarioAberto(a.user_id)}
                    title={`Última atividade: ${formatDateTimeBR(a.ultima_atividade)}`}>
                    <Chip tone={a.estado === 'ativo' ? 'success' : 'warning'}>{a.username}{a.unit ? ` · ${a.unit}` : ''} — {a.estado === 'ativo' ? 'ativo' : 'ocioso'}</Chip>
                  </button>
                ))}
              </div>
            </section>
          )}

          <div className="grid-2">
            <section className="card stack">
              <div className="card-title">Atividade por dia</div>
              {r && r.por_dia.length > 0 ? <GraficoDias dados={r.por_dia} /> : <EmptyState icon="activity" title="Sem eventos no período" />}
            </section>
            <section className="card stack">
              <div className="card-title">Uso por módulo</div>
              {r && r.por_modulo.length > 0 ? (
                <div className="stack" style={{ gap: 8 }}>
                  {r.por_modulo.map((m) => {
                    const max = r.por_modulo[0].eventos || 1;
                    return (
                      <div className="barrow" key={m.modulo}>
                        <div>{NOME_MODULO[m.modulo] ?? m.modulo}</div>
                        <div className="bar-track" role="img" aria-label={`${NOME_MODULO[m.modulo] ?? m.modulo}: ${m.eventos}`}><div className="bar-fill" style={{ width: `${(m.eventos / max) * 100}%` }} /></div>
                        <div className="strong num" style={{ textAlign: 'right' }}>{m.eventos}</div>
                      </div>
                    );
                  })}
                </div>
              ) : <EmptyState title="Sem uso registrado" />}
            </section>
          </div>

          {r && r.falhas_relevantes.length > 0 && (
            <section className="stack" aria-label="Falhas relevantes">
              <div className="card-title">Falhas relevantes</div>
              <div className="table-wrap">
                <table className="table">
                  <caption className="sr-only">Falhas relevantes</caption>
                  <thead><tr><th scope="col">Evento</th><th scope="col">Módulo</th><th scope="col">HTTP</th><th scope="col" className="num">Ocorrências</th></tr></thead>
                  <tbody>
                    {r.falhas_relevantes.map((f) => (
                      <tr key={`${f.evento}-${f.status}`}><td className="mono">{f.evento}</td><td>{NOME_MODULO[f.modulo ?? ''] ?? f.modulo ?? '—'}</td>
                        <td>{f.status ?? '—'}</td><td className="num strong">{f.ocorrencias}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {uso.data && (
            <details className="card">
              <summary className="strong">Como os números são calculados</summary>
              <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>{uso.data.criterios.map((c) => <li key={c}>{c}</li>)}</ul>
            </details>
          )}
        </>
      )}

      {aba === 'usuarios' && (uso.loading && !uso.data ? <TableSkeleton rows={5} cols={8} /> : uso.data && (uso.data.itens.length === 0 ? <EmptyState icon="users" title="Nenhum usuário nos filtros" /> : (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Utilização por usuário</caption>
            <thead><tr>
              <th scope="col">Usuário</th><th scope="col">Unidade</th><th scope="col">Agora</th><th scope="col" className="hide-md">Último acesso</th>
              <th scope="col" className="num">Acessos</th><th scope="col" className="num">Em sessão</th><th scope="col" className="num">Ativo</th>
              <th scope="col" className="num hide-md">Ocioso</th><th scope="col" className="num hide-md">Por inatividade</th><th scope="col">Situação</th>
            </tr></thead>
            <tbody>
              {uso.data.itens.map((u) => (
                <tr key={u.id} className="row-click" tabIndex={0} onClick={() => setUsuarioAberto(u.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter') setUsuarioAberto(u.id); }}>
                  <td><div className="strong">{u.nome || u.username}</div><div className="cell-sub mono">{u.username}{!u.conta_ativa && ' · conta desativada'}</div></td>
                  <td>{u.unidade}</td>
                  <td><Chip tone={ESTADO_AGORA[u.estado_agora].tone}>{ESTADO_AGORA[u.estado_agora].texto}</Chip></td>
                  <td className="hide-md">{formatDateTimeBR(u.ultimo_acesso)}</td>
                  <td className="num">{u.acessos}</td>
                  <td className="num">{formatarMinutos(u.tempo_sessao_min)}</td>
                  <td className="num">{formatarMinutos(u.tempo_ativo_min)}</td>
                  <td className="num hide-md">{formatarMinutos(u.tempo_ocioso_min)}</td>
                  <td className="num hide-md">{u.sessoes_por_inatividade}</td>
                  <td><Chip tone={u.utilizou ? 'success' : 'neutral'} dot={false} title={u.parecer}>{u.situacao}</Chip></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )))}

      {aba === 'sessoes' && (sessoes.loading && !sessoes.data ? <TableSkeleton rows={5} cols={7} /> : sessoes.data && (sessoes.data.itens.length === 0 ? <EmptyState title="Nenhuma sessão no período" /> : (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Sessões</caption>
            <thead><tr><th scope="col">Usuário</th><th scope="col">Início</th><th scope="col">Fim</th><th scope="col" className="num">Duração</th>
              <th scope="col" className="num">Ativo</th><th scope="col">Como terminou</th><th scope="col" className="hide-md">IP</th></tr></thead>
            <tbody>
              {sessoes.data.itens.map((s) => (
                <tr key={s.id}>
                  <td className="strong">{s.username}{s.unit && <span className="cell-sub">{s.unit}</span>}</td>
                  <td>{formatDateTimeBR(s.inicio)}</td>
                  <td>{s.fim ? formatDateTimeBR(s.fim) : <span className="muted">em andamento</span>}</td>
                  <td className="num">{formatarMinutos(s.duracao_min)}</td><td className="num">{formatarMinutos(s.tempo_ativo_min)}</td>
                  <td><Chip tone={tomDoEncerramento(s)}>{textoDaSessao(s)}</Chip></td>
                  <td className="hide-md mono">{s.ip ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )))}

      {aba === 'eventos' && <AuditPage embutido />}

      {usuarioAberto !== null && <UsuarioDetalhe userId={usuarioAberto} onClose={() => setUsuarioAberto(null)} />}
    </div>
  );
}

/** Gráfico de barras em SVG (sem biblioteca). Texto alternativo + tabela equivalente via aria-label. */
function GraficoDias({ dados }: { dados: UsageSummary['por_dia'] }) {
  const max = Math.max(...dados.map((d) => d.eventos), 1);
  const w = 560;
  const h = 150;
  const largura = Math.max(6, Math.min(34, (w - 20) / dados.length - 4));
  const passo = (w - 20) / dados.length;
  const resumoTxt = `Eventos por dia: ${dados.map((d) => `${formatBR(d.data)}: ${d.eventos}`).join('; ')}`;
  return (
    <svg viewBox={`0 0 ${w} ${h + 28}`} role="img" aria-label={resumoTxt} style={{ width: '100%', height: 'auto' }}>
      <title>Eventos por dia</title>
      <line x1="10" y1={h} x2={w - 10} y2={h} stroke="var(--border-strong)" />
      {dados.map((d, i) => {
        const bh = Math.max(2, (d.eventos / max) * (h - 14));
        const x = 10 + i * passo + (passo - largura) / 2;
        return (
          <g key={d.data}>
            <rect x={x} y={h - bh} width={largura} height={bh} rx="3" fill="var(--primary)" opacity="0.9">
              <title>{`${formatBR(d.data)}: ${d.eventos} eventos, ${d.logins} logins, ${d.usuarios_ativos} usuário(s)`}</title>
            </rect>
            {(dados.length <= 16 || i % Math.ceil(dados.length / 12) === 0) && (
              <text x={x + largura / 2} y={h + 16} textAnchor="middle" fontSize="10" fill="var(--text-3)">{d.data.slice(8)}/{d.data.slice(5, 7)}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
