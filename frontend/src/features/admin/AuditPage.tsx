import { useState } from 'react';
import { adminApi } from '../../shared/api/adminClient';
import { mensagemDeErro } from '../../shared/api/http';
import type { AuditEvent, AuditFilters } from '../../shared/api/types';
import { useAsync, useDebounced } from '../../shared/hooks/useAsync';
import Modal from '../../shared/ui/Modal';
import { useToast } from '../../shared/ui/Toast';
import { Alert, Button, Chip, EmptyState, PageHead, Pagination, TableSkeleton } from '../../shared/ui/ui';
import { addDays, formatDateTimeBR, todayISO } from '../../shared/utils/dateUtils';
import { NOME_MODULO } from '../../shared/utils/status';

const MODULOS = ['auth', 'preventivas', 'planos', 'colaboradores', 'distribuicao', 'regras', 'exportacao', 'admin', 'sistema'];

export function toneDoResultado(r: AuditEvent['result']): 'success' | 'warning' | 'danger' {
  return r === 'success' ? 'success' : r === 'denied' ? 'warning' : 'danger';
}

export default function AuditPage() {
  const toast = useToast();
  const [dataIni, setDataIni] = useState(addDays(todayISO(), -7));
  const [dataFim, setDataFim] = useState(todayISO());
  const [username, setUsername] = useState('');
  const [unit, setUnit] = useState('');
  const [modulo, setModulo] = useState('');
  const [resultado, setResultado] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [detalhe, setDetalhe] = useState<AuditEvent | null>(null);
  const [exportando, setExportando] = useState(false);
  const userD = useDebounced(username);

  const filtros: AuditFilters = { dataIni, dataFim, username: userD, unit: unit || undefined, module: modulo || undefined, result: resultado || undefined, page, pageSize };
  const { data, loading, error, reload } = useAsync(() => adminApi.audit(filtros), [JSON.stringify(filtros)]);

  const mudar = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1); };

  const exportar = async (formato: 'xlsx' | 'csv') => {
    setExportando(true);
    try {
      toast.success(`Arquivo gerado: ${await adminApi.exportAudit(filtros, formato)}`);
    } catch (e) {
      toast.error(mensagemDeErro(e));
    } finally {
      setExportando(false);
    }
  };

  return (
    <div className="stack">
      <PageHead
        title="Histórico de utilização"
        subtitle="Trilha de auditoria append-only: quem fez o quê, onde, quando e com qual resultado. Senhas e tokens nunca são gravados."
        actions={<>
          <Button icon="refresh" onClick={reload} loading={loading}>Atualizar</Button>
          <Button icon="download" onClick={() => exportar('xlsx')} loading={exportando}>Excel</Button>
          <Button icon="download" onClick={() => exportar('csv')} disabled={exportando}>CSV</Button>
        </>}
      />

      <section className="card row" aria-label="Filtros">
        <div className="field"><label htmlFor="a-ini">De</label><input id="a-ini" type="date" className="input" value={dataIni} max={dataFim} onChange={(e) => mudar(setDataIni)(e.target.value)} /></div>
        <div className="field"><label htmlFor="a-fim">Até</label><input id="a-fim" type="date" className="input" value={dataFim} min={dataIni} onChange={(e) => mudar(setDataFim)(e.target.value)} /></div>
        <div className="field"><label htmlFor="a-user">Usuário</label><input id="a-user" className="input" placeholder="parte do login" value={username} onChange={(e) => mudar(setUsername)(e.target.value)} /></div>
        <div className="field"><label htmlFor="a-unit">Unidade</label>
          <select id="a-unit" className="select" value={unit} onChange={(e) => mudar(setUnit)(e.target.value)}>
            <option value="">Todas</option><option value="HETRIN">Hetrin</option><option value="HMB">HMB</option>
          </select></div>
        <div className="field"><label htmlFor="a-mod">Módulo</label>
          <select id="a-mod" className="select" value={modulo} onChange={(e) => mudar(setModulo)(e.target.value)}>
            <option value="">Todos</option>{MODULOS.map((m) => <option key={m} value={m}>{NOME_MODULO[m] ?? m}</option>)}
          </select></div>
        <div className="field"><label htmlFor="a-res">Resultado</label>
          <select id="a-res" className="select" value={resultado} onChange={(e) => mudar(setResultado)(e.target.value)}>
            <option value="">Todos</option><option value="success">Sucesso</option><option value="failure">Falha</option><option value="denied">Negado</option>
          </select></div>
      </section>

      {error && <Alert tone="danger" action={<Button size="sm" onClick={reload}>Tentar de novo</Button>}>{error}</Alert>}
      {loading && !data ? <TableSkeleton rows={8} cols={7} /> : data && data.itens.length === 0 ? (
        <EmptyState icon="activity" title="Nenhum evento no período">
          Ausência de eventos não significa que ninguém usou o sistema fora do período coletado — veja a nota em Relatórios.
        </EmptyState>
      ) : data ? (
        <>
          <div className="table-wrap" aria-busy={loading}>
            <table className="table">
              <caption className="sr-only">Eventos de auditoria</caption>
              <thead><tr><th scope="col">Data/hora</th><th scope="col">Usuário</th><th scope="col">Unidade</th><th scope="col">Módulo · ação</th><th scope="col" className="hide-md">Recurso</th><th scope="col">Resultado</th></tr></thead>
              <tbody>
                {data.itens.map((e) => (
                  <tr key={e.id} className="row-click" tabIndex={0} onClick={() => setDetalhe(e)}
                    onKeyDown={(ev) => { if (ev.key === 'Enter') setDetalhe(e); }}>
                    <td className="mono">{formatDateTimeBR(e.ts)}</td>
                    <td className="strong">{e.username ?? <span className="muted">anônimo</span>}</td>
                    <td>{e.unit ?? '—'}</td>
                    <td>{NOME_MODULO[e.module ?? ''] ?? e.module ?? '—'} · <span className="muted">{e.event}</span></td>
                    <td className="hide-md"><div className="cell-clip" title={e.resource ?? undefined}>{e.resource ?? '—'}</div></td>
                    <td><Chip tone={toneDoResultado(e.result)}>{e.result === 'success' ? 'Sucesso' : e.result === 'denied' ? 'Negado' : 'Falha'}{e.status_code ? ` · ${e.status_code}` : ''}</Chip></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={data.pagina} pageSize={data.por_pagina} total={data.total} onPage={setPage} onPageSize={(n) => { setPageSize(n); setPage(1); }} />
        </>
      ) : null}

      {detalhe && (
        <Modal title="Detalhe do evento" onClose={() => setDetalhe(null)}>
          <dl className="kv">
            {([
              ['Data/hora', formatDateTimeBR(detalhe.ts)], ['Usuário', detalhe.username ?? '—'], ['Unidade', detalhe.unit ?? '—'],
              ['Evento', detalhe.event], ['Módulo', detalhe.module ?? '—'], ['Ação', detalhe.action ?? '—'],
              ['Resultado', detalhe.result], ['HTTP', detalhe.status_code ? `${detalhe.method} ${detalhe.status_code}` : '—'],
              ['Recurso', detalhe.resource ?? '—'], ['Caminho', detalhe.path ?? '—'], ['IP', detalhe.ip ?? '—'], ['Sessão', detalhe.session_id ? `#${detalhe.session_id}` : '—'],
            ] as [string, string][]).map(([k, v]) => <div key={k}><dt>{k}</dt><dd className="cell-clip" style={{ maxWidth: 'none', overflowWrap: 'anywhere', whiteSpace: 'normal' }}>{v}</dd></div>)}
          </dl>
          {detalhe.user_agent && <div className="muted" style={{ fontSize: 12, overflowWrap: 'anywhere' }}>{detalhe.user_agent}</div>}
          <div>
            <div className="label">Detalhes (sanitizados)</div>
            <pre className="mono" style={{ whiteSpace: 'pre-wrap', background: 'var(--surface-2)', padding: 10, borderRadius: 8, overflowWrap: 'anywhere' }}>
              {detalhe.details ? JSON.stringify(detalhe.details, null, 2) : 'Sem detalhes adicionais.'}
            </pre>
          </div>
        </Modal>
      )}
    </div>
  );
}
