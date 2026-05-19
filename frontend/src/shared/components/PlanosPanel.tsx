import { useState, useCallback, useEffect } from 'react';
import type { buildUnitClient } from '../api/client';
import type { Plano, PlanoResponse } from '../api/types';

type UnitApiClient = ReturnType<typeof buildUnitClient>;

interface PlanosPanelProps {
  apiClient: UnitApiClient;
  onCountChange?: (count: number) => void;
  autoLoad?: boolean;
}

function filterItems(items: Plano[], search: string): Plano[] {
  const term = search.trim().toLowerCase();
  if (!term) return items;
  return items.filter((item) => {
    const haystack = [item.descricao, item.tipo, item.periodicidade, item.oficina].join(' ').toLowerCase();
    return haystack.includes(term);
  });
}

export default function PlanosPanel({ apiClient, onCountChange, autoLoad }: PlanosPanelProps) {
  const [data, setData] = useState<PlanoResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiClient.fetchPlanos();
      setData(result);
      onCountChange?.(result.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar planos');
    } finally {
      setLoading(false);
    }
  }, [apiClient, onCountChange]);

  useEffect(() => {
    if (autoLoad) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered: Plano[] = data ? filterItems(data.itens, search) : [];

  return (
    <div>
      <div className="toolbar">
        <button className="btn-primary" onClick={load} disabled={loading}>
          {loading ? 'Carregando…' : 'Carregar Planos'}
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
          {loading && <span>Carregando planos…</span>}
          {error && <span role="alert" style={{ color: 'var(--color-danger)' }}>{error}</span>}
        </div>
      )}

      <div className="tbl-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Descrição</th>
              <th>Tipo</th>
              <th>Periodicidade</th>
              <th>Oficina</th>
              <th>Procedimento</th>
              <th>Ativo</th>
            </tr>
          </thead>
          <tbody>
            {!data ? (
              <tr><td colSpan={7} className="empty">Clique em "Carregar Planos" para carregar os dados.</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={7} className="empty">Nenhum registro encontrado.</td></tr>
            ) : (
              filtered.map((item) => (
                <tr key={item.id}>
                  <td>{item.id}</td>
                  <td>{item.descricao}</td>
                  <td>{item.tipo}</td>
                  <td>{item.periodicidade}</td>
                  <td>{item.oficina}</td>
                  <td>{item.procedimento}</td>
                  <td>
                    <span className={`badge ${item.ativo ? 'b-ok' : 'b-gray'}`}>
                      {item.ativo ? 'Sim' : 'Não'}
                    </span>
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
