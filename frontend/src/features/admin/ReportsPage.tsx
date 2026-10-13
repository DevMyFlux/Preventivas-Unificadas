import { useState } from 'react';
import { adminApi } from '../../shared/api/adminClient';
import { mensagemDeErro } from '../../shared/api/http';
import type { AuditFilters, UsageSummary } from '../../shared/api/types';
import { useAsync } from '../../shared/hooks/useAsync';
import { useToast } from '../../shared/ui/Toast';
import { Alert, Button, Chip, EmptyState, KpiCard, PageHead, Segmented, TableSkeleton } from '../../shared/ui/ui';
import { addDays, formatBR, formatDateTimeBR, todayISO } from '../../shared/utils/dateUtils';
import { NOME_MODULO } from '../../shared/utils/status';

const ENCERRAMENTO: Record<string, { texto: string; tone: 'success' | 'warning' | 'info' | 'neutral' | 'danger' }> = {
  logout: { texto: 'Saiu (logout)', tone: 'success' },
  idle_timeout: { texto: 'Expirou por inatividade', tone: 'warning' },
  max_lifetime: { texto: 'Expirou (limite de tempo)', tone: 'warning' },
  revoked: { texto: 'Encerrada pelo admin', tone: 'neutral' },
  user_deactivated: { texto: 'Conta desativada', tone: 'danger' },
  password_changed: { texto: 'Senha alterada', tone: 'neutral' },
  em_andamento: { texto: 'Em andamento', tone: 'info' },
};

export function formatarMinutos(min: number): string {
  if (min < 1) return '< 1 min';
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return h > 0 ? `${h} h ${m} min` : `${m} min`;
}

export default function ReportsPage() {
  const toast = useToast();
  const [dataIni, setDataIni] = useState(addDays(todayISO(), -30));
  const [dataFim, setDataFim] = useState(todayISO());
  const [unit, setUnit] = useState('');
  const [aba, setAba] = useState<'usuarios' | 'sessoes' | 'falhas'>('usuarios');
  const [exportando, setExportando] = useState(false);

  const filtros: AuditFilters = { dataIni, dataFim, unit: unit || undefined };
  const resumo = useAsync(() => adminApi.summary(filtros), [JSON.stringify(filtros)]);
  const uso = useAsync(() => adminApi.usage(filtros), [JSON.stringify(filtros)]);
  const sessoes = useAsync(() => adminApi.sessions(filtros), [JSON.stringify(filtros)], aba === 'sessoes');

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

  const r = resumo.data;
  const t = r?.totais;
  const erro = resumo.error ?? uso.error;

  return (
    <div className="stack">
      <PageHead
        title="Relatórios de utilização"
        subtitle="Atividade por usuário, unidade e período — com a distinção entre inatividade e ausência de registros."
        actions={<>
          <Button icon="refresh" onClick={() => { resumo.reload(); uso.reload(); sessoes.reload(); }} loading={resumo.loading}>Atualizar</Button>
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
      </section>

      {erro && <Alert tone="danger" action={<Button size="sm" onClick={() => { resumo.reload(); uso.reload(); }}>Tentar de novo</Button>}>{erro}</Alert>}

      {r && (
        <Alert tone="info">
          <b>Como ler:</b> {r.nota} Uma sessão sem logout é considerada ociosa após {r.limite_inatividade_min} min sem atividade e encerrada na
          última atividade conhecida (cobre fechamento de aba e quedas de rede).
        </Alert>
      )}

      <section className="kpis" aria-label="Indicadores">
        <KpiCard label="Usuários com atividade" value={t?.usuarios_ativos ?? null} tone="primary" loading={resumo.loading && !r} />
        <KpiCard label="Logins" value={t?.logins ?? null} tone="success" loading={resumo.loading && !r} />
        <KpiCard label="Eventos registrados" value={t?.eventos ?? null} tone="info" loading={resumo.loading && !r} />
        <KpiCard label="Logins inválidos" value={t?.logins_falhos ?? null} tone="warning" loading={resumo.loading && !r} />
        <KpiCard label="Acessos negados" value={t?.acessos_negados ?? null} tone="danger" loading={resumo.loading && !r} />
        <KpiCard label="Falhas" value={t?.falhas ?? null} tone="danger" loading={resumo.loading && !r} />
        <KpiCard label="Sessões" value={t?.sessoes ?? null} tone="purple" hint={t ? `média ${formatarMinutos(t.tempo_medio_sessao_min)}` : undefined} loading={resumo.loading && !r} />
      </section>

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

      <Segmented label="Detalhamento" value={aba} onChange={setAba} options={[
        { key: 'usuarios', label: 'Por usuário' }, { key: 'sessoes', label: 'Sessões' }, { key: 'falhas', label: 'Falhas relevantes' }]} />

      {aba === 'usuarios' && (uso.loading && !uso.data ? <TableSkeleton rows={5} cols={7} /> : uso.data && (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Utilização por usuário</caption>
            <thead><tr><th scope="col">Usuário</th><th scope="col">Unidade</th><th scope="col">Situação no período</th><th scope="col" className="num">Sessões</th><th scope="col" className="num">Tempo em sessão</th><th scope="col" className="num">Eventos</th><th scope="col" className="num hide-md">Alterações</th><th scope="col" className="num hide-md">Exportações</th><th scope="col" className="hide-md">Último evento</th></tr></thead>
            <tbody>
              {uso.data.itens.map((u) => (
                <tr key={u.username}>
                  <td><div className="strong">{u.nome || u.username}</div><div className="cell-sub mono">{u.username}{!u.conta_ativa && ' · conta desativada'}</div></td>
                  <td>{u.unidade}</td>
                  <td><Chip tone={u.situacao.startsWith('Com') ? 'success' : 'neutral'} dot={false}>{u.situacao}</Chip></td>
                  <td className="num">{u.sessoes}</td><td className="num">{formatarMinutos(u.tempo_em_sessao_min)}</td>
                  <td className="num">{u.eventos}</td><td className="num hide-md">{u.escritas}</td><td className="num hide-md">{u.exportacoes}</td>
                  <td className="hide-md">{formatDateTimeBR(u.ultimo_evento)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {aba === 'sessoes' && (sessoes.loading && !sessoes.data ? <TableSkeleton rows={5} cols={6} /> : sessoes.data && (sessoes.data.itens.length === 0 ? <EmptyState title="Nenhuma sessão no período" /> : (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Sessões</caption>
            <thead><tr><th scope="col">Usuário</th><th scope="col">Início</th><th scope="col">Última atividade</th><th scope="col">Duração</th><th scope="col">Encerramento</th><th scope="col" className="hide-md">IP</th></tr></thead>
            <tbody>
              {sessoes.data.itens.map((s) => {
                const enc = ENCERRAMENTO[s.encerramento] ?? { texto: s.encerramento, tone: 'neutral' as const };
                return (
                  <tr key={s.id}>
                    <td className="strong">{s.username}{s.unit && <span className="cell-sub">{s.unit}</span>}</td>
                    <td>{formatDateTimeBR(s.inicio)}</td><td>{formatDateTimeBR(s.ultima_atividade)}</td>
                    <td>{formatarMinutos(s.duracao_min)}</td><td><Chip tone={enc.tone}>{enc.texto}</Chip></td>
                    <td className="hide-md mono">{s.ip ?? '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )))}

      {aba === 'falhas' && r && (r.falhas_relevantes.length === 0 ? (
        <EmptyState icon="checkCircle" title="Nenhuma falha relevante no período" />
      ) : (
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
      ))}
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
