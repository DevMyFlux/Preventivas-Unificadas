import { useEffect, useMemo, useState } from 'react';
import type { UnitApiClient } from '../../shared/api/client';
import type { Colaborador } from '../../shared/api/types';
import { useAsync } from '../../shared/hooks/useAsync';
import { Alert, Button, Chip, EmptyState, PageHead, TableSkeleton } from '../../shared/ui/ui';
import { formatBR } from '../../shared/utils/dateUtils';
import ColaboradorModal from './ColaboradorModal';

export function filtrarColaboradores(
  items: Colaborador[], busca: string, status: string, bloqueado: string, executa: string,
): Colaborador[] {
  const q = busca.trim().toLowerCase();
  return items.filter((c) => {
    if (status && c.status !== status) return false;
    if (bloqueado === 'sim' && !c.bloqueado) return false;
    if (bloqueado === 'nao' && c.bloqueado) return false;
    if (executa === 'sim' && !c.executa_os) return false;
    if (executa === 'nao' && c.executa_os) return false;
    if (!q) return true;
    return [c.funcionario, c.cargo, c.turno, c.regime, c.horario].join(' ').toLowerCase().includes(q);
  });
}

interface Props {
  client: UnitApiClient;
  dataIni: string;
  dataFim: string;
  onCount?: (n: number) => void;
}

export default function ColaboradoresPanel({ client, dataIni, dataFim, onCount }: Props) {
  const [busca, setBusca] = useState('');
  const [status, setStatus] = useState('');
  const [bloqueado, setBloqueado] = useState('');
  const [executa, setExecuta] = useState('');
  const [selecionado, setSelecionado] = useState<string | null>(null);
  const { data, loading, error, reload } = useAsync(() => client.fetchColaboradores(), [client]);

  useEffect(() => { if (data) onCount?.(data.total); }, [data, onCount]);
  const filtrados = useMemo(() => (data ? filtrarColaboradores(data.itens, busca, status, bloqueado, executa) : []),
    [data, busca, status, bloqueado, executa]);

  return (
    <div className="stack">
      <PageHead
        title="Colaboradores"
        subtitle="Quadro da unidade, vínculo (admissão/desligamento) e aptidão. Desligados permanecem no histórico."
        actions={<Button icon="refresh" onClick={reload} loading={loading}>Atualizar</Button>}
      />
      <div className="row">
        <div className="search-wrap" style={{ flex: '1 1 260px', maxWidth: 420 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" /></svg>
          <input className="input" placeholder="Buscar nome, cargo, turno…" aria-label="Busca por colaborador" value={busca} onChange={(e) => setBusca(e.target.value)} />
        </div>
        <select className="select" style={{ maxWidth: 160 }} aria-label="Filtrar por status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Status: todos</option><option value="Ativo">Ativo</option><option value="Desligado">Desligado</option>
        </select>
        <select className="select" style={{ maxWidth: 170 }} aria-label="Filtrar por bloqueio" value={bloqueado} onChange={(e) => setBloqueado(e.target.value)}>
          <option value="">Bloqueio: todos</option><option value="sim">Bloqueados</option><option value="nao">Não bloqueados</option>
        </select>
        <select className="select" style={{ maxWidth: 190 }} aria-label="Filtrar por função" value={executa} onChange={(e) => setExecuta(e.target.value)}>
          <option value="">Função: todas</option><option value="sim">Executam OS</option><option value="nao">Gestão / administrativo</option>
        </select>
        {data && <span className="muted">{filtrados.length} de {data.total}</span>}
      </div>

      {error && <Alert tone="danger" action={<Button size="sm" onClick={reload}>Tentar de novo</Button>}>{error}</Alert>}
      {loading && !data ? <TableSkeleton rows={8} cols={6} /> : data && filtrados.length === 0 ? (
        <EmptyState icon="users" title="Nenhum colaborador encontrado">Ajuste a busca ou os filtros.</EmptyState>
      ) : data ? (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Colaboradores da unidade</caption>
            <thead>
              <tr>
                <th scope="col">Nome</th><th scope="col">Cargo</th><th scope="col">Turno / escala</th>
                <th scope="col" className="hide-md">Limite diário</th><th scope="col">Situação</th><th scope="col" className="hide-md">Vínculo</th>
              </tr>
            </thead>
            <tbody>
              {filtrados.map((c) => (
                <tr key={c.funcionario} className="row-click" onClick={() => setSelecionado(c.funcionario)}
                  style={{ opacity: c.status === 'Desligado' ? 0.72 : 1 }}>
                  <td>
                    <button type="button" className="btn btn-ghost btn-sm strong" style={{ padding: 0, minHeight: 0 }}
                      onClick={(e) => { e.stopPropagation(); setSelecionado(c.funcionario); }}>
                      {c.funcionario}
                    </button>
                    {c.fora_da_escala && <div className="cell-sub">Fora da escala vigente (histórico)</div>}
                  </td>
                  <td>{c.cargo || '—'}{!c.executa_os && <div className="cell-sub">Não executa OS</div>}</td>
                  <td>{c.turno || '—'}{c.regime && c.regime !== '—' ? <div className="cell-sub">{c.regime}{c.horario ? ` · ${c.horario}` : ''}</div> : null}</td>
                  <td className="hide-md">{c.limite_diario ? `${c.limite_diario}/dia (${c.especialidade})` : <span className="muted">—</span>}</td>
                  <td>
                    <div className="row" style={{ gap: 4 }}>
                      <Chip tone={c.status === 'Ativo' ? 'success' : 'danger'}>{c.status}</Chip>
                      {c.bloqueado && <Chip tone="warning" title={c.aviso ?? undefined}>Bloqueado</Chip>}
                    </div>
                  </td>
                  <td className="hide-md">
                    {c.data_desligamento ? <>Desligado em <b>{formatBR(c.data_desligamento)}</b></> : c.data_admissao ? <>Admitido em {formatBR(c.data_admissao)}</> : <span className="muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {selecionado && (
        <ColaboradorModal client={client} nome={selecionado} dataIni={dataIni} dataFim={dataFim}
          onClose={() => setSelecionado(null)} onChanged={reload} />
      )}
    </div>
  );
}
