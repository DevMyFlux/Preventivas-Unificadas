import { useState, useEffect, useCallback } from 'react';
import { fetchOS } from '../api/client';
import type { OSItem, OSResponse } from '../api/types';
import { filterOS } from '../utils/osFilter';

interface OSPanelProps {
  dataIni?: string;
  dataFim?: string;
  onCountChange?: (count: number) => void;
  onDataLoad?: (data: OSResponse) => void;
  autoLoad?: boolean;
}

function statusBadgeClass(sitLabel: string): string {
  switch (sitLabel) {
    case 'Fechada':      return 'b-ok';
    case 'Em Andamento': return 'b-warn';
    case 'Aberta':       return 'b-blue';
    default:             return 'b-gray';
  }
}

function rowClass(item: OSItem): string {
  if (!item.responsavel) return 'row-danger';
  if (item.sit_label === 'Fechada') return 'row-ok';
  return '';
}

export default function OSPanel({ dataIni, dataFim, onCountChange, onDataLoad, autoLoad }: OSPanelProps) {
  const [data, setData] = useState<OSResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [situacao, setSituacao] = useState('Todas');
  const [responsavel, setResponsavel] = useState('Todos');
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchOS(dataIni, dataFim);
      setData(result);
      onCountChange?.(result.total);
      onDataLoad?.(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar OS');
    } finally {
      setLoading(false);
    }
  }, [dataIni, dataFim, onCountChange, onDataLoad]);

  useEffect(() => {
    if (autoLoad || data) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataIni, dataFim]);

  const filtered: OSItem[] = data ? filterOS(data.itens, situacao, responsavel, search) : [];

  return (
    <div>
      {data && (
        <div className="cards">
          <div className="card"><div className="num">{data.total}</div><div className="lbl">Total</div></div>
          <div className="card green"><div className="num">{data.com_responsavel}</div><div className="lbl">Com Responsável</div></div>
          <div className="card red"><div className="num">{data.sem_responsavel}</div><div className="lbl">Sem Responsável</div></div>
          <div className="card orange"><div className="num">{data.em_andamento}</div><div className="lbl">Em Andamento</div></div>
          <div className="card purple"><div className="num">{data.fechadas}</div><div className="lbl">Fechadas</div></div>
        </div>
      )}

      <div className="toolbar">
        <button className="btn-primary" onClick={load} disabled={loading}>
          {loading ? 'Carregando…' : 'Carregar OS'}
        </button>
        <select value={situacao} onChange={(e) => setSituacao(e.target.value)} aria-label="Filtrar por situação">
          <option>Todas</option>
          <option>Aberta</option>
          <option>Em Andamento</option>
          <option>Fechada</option>
        </select>
        <select value={responsavel} onChange={(e) => setResponsavel(e.target.value)} aria-label="Filtrar por responsável">
          <option>Todos</option>
          <option>Com Responsável</option>
          <option>Sem Responsável</option>
        </select>
        <input
          type="text"
          className="search"
          placeholder="Buscar…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Busca livre"
        />
      </div>

      {(loading || error) && (
        <div className="status-bar">
          {loading && <span className="spinner" aria-hidden="true" />}
          {loading && <span>Carregando dados…</span>}
          {error && <span role="alert" style={{ color: 'var(--color-danger)' }}>{error}</span>}
        </div>
      )}

      {data && (
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th>Nº OS</th>
                <th>Abertura</th>
                <th>Tipo</th>
                <th>Setor</th>
                <th>Prioridade</th>
                <th>Status</th>
                <th>Responsável</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={7} className="empty">Nenhum registro encontrado.</td></tr>
              ) : (
                filtered.map((item) => (
                  <tr key={item.numero} className={rowClass(item)}>
                    <td>{item.numero}</td>
                    <td>{item.abertura}</td>
                    <td>{item.tipo}</td>
                    <td>{item.setor}</td>
                    <td>{item.prioridade}</td>
                    <td><span className={`badge ${statusBadgeClass(item.sit_label)}`}>{item.sit_label}</span></td>
                    <td>{item.responsavel ?? '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
