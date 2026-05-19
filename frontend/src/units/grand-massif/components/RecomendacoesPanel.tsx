import { useState, useCallback, useEffect } from 'react';
import { fetchRecomendacoes, exportarRecomendacoes } from '../api/client';
import type { RecomendacaoItem, RecomendacaoResponse } from '../api/types';
import { scoreClass, statusBadgeClass } from '../../../shared/utils/scoreColor';

interface RecomendacoesPanelProps {
  dataIni?: string;
  dataFim?: string;
  onCountChange?: (count: number) => void;
  autoLoad?: boolean;
}

function filterItems(items: RecomendacaoItem[], search: string): RecomendacaoItem[] {
  const term = search.trim().toLowerCase();
  if (!term) return items;
  return items.filter((item) => {
    const haystack = [item.numero, item.tipo, item.setor, item.recomendado ?? '', item.responsavel_atual ?? '']
      .join(' ')
      .toLowerCase();
    return haystack.includes(term);
  });
}

export default function RecomendacoesPanel({ dataIni, dataFim, onCountChange, autoLoad }: RecomendacoesPanelProps) {
  const [data, setData] = useState<RecomendacaoResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchRecomendacoes(dataIni, dataFim);
      setData(result);
      onCountChange?.(result.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao calcular recomendações');
    } finally {
      setLoading(false);
    }
  }, [dataIni, dataFim, onCountChange]);

  useEffect(() => {
    if (autoLoad || data) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataIni, dataFim]);

  const filtered: RecomendacaoItem[] = data ? filterItems(data.itens, search) : [];

  return (
    <div>
      {data && (
        <div className="cards">
          <div className="card"><div className="num">{data.total}</div><div className="lbl">Total OS</div></div>
          <div className="card green"><div className="num">{data.com_responsavel}</div><div className="lbl">Com Responsável</div></div>
          <div className="card red"><div className="num">{data.sem_responsavel}</div><div className="lbl">Sem Responsável</div></div>
          <div className="card orange"><div className="num">{data.sugestao_diff}</div><div className="lbl">Sugestão Diferente</div></div>
          <div className="card green"><div className="num">{data.bate_atual}</div><div className="lbl">Bate com Atual</div></div>
        </div>
      )}

      <div className="toolbar">
        <button className="btn-primary" onClick={load} disabled={loading}>
          {loading ? 'Calculando…' : 'Calcular Recomendações'}
        </button>
        <button className="btn-success" onClick={exportarRecomendacoes} disabled={!data} aria-label="Exportar Excel">
          Exportar Excel
        </button>
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
          {loading && <span>Calculando recomendações…</span>}
          {error && <span role="alert" style={{ color: 'var(--color-danger)' }}>{error}</span>}
        </div>
      )}

      <div className="tbl-wrap">
        <table>
          <thead>
            <tr>
              <th>Nº OS</th>
              <th>Data</th>
              <th>Turno</th>
              <th>Situação</th>
              <th>Tipo</th>
              <th>Setor</th>
              <th>Ativo</th>
              <th>Responsável Atual</th>
              <th>Recomendado</th>
              <th>Cargo</th>
              <th>Score</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {!data ? (
              <tr><td colSpan={12} className="empty">Clique em "Calcular Recomendações" para carregar os dados.</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={12} className="empty">Nenhum registro encontrado.</td></tr>
            ) : (
              filtered.map((item) => (
                <tr key={item.numero}>
                  <td>{item.numero}</td>
                  <td>{item.data_os}</td>
                  <td>{item.turno_os}</td>
                  <td>{item.situacao}</td>
                  <td>{item.tipo}</td>
                  <td>{item.setor}</td>
                  <td>{item.ativo || '—'}</td>
                  <td>{item.responsavel_atual ?? '—'}</td>
                  <td>{item.recomendado ?? 'SEM CANDIDATO'}</td>
                  <td>{item.cargo || '—'}</td>
                  <td>
                    {item.recomendado ? <span className={scoreClass(item.score)}>{item.score}</span> : '—'}
                  </td>
                  <td>
                    <span className={`badge ${statusBadgeClass(item.status)}`}>{item.status}</span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
