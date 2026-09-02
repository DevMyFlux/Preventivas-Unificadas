import { useState, useCallback, useEffect } from 'react';
import type { buildUnitClient } from '../api/client';
import type { Plano, PlanoResponse } from '../api/types';

type UnitApiClient = ReturnType<typeof buildUnitClient>;

interface PlanosPanelProps {
  apiClient: UnitApiClient;
  onCountChange?: (count: number) => void;
  autoLoad?: boolean;
}

export type FiltroAtivo = '' | 'sim' | 'nao';

function filterItems(items: Plano[], search: string, ativo: FiltroAtivo = ''): Plano[] {
  const term = search.trim().toLowerCase();
  return items.filter((item) => {
    if (ativo === 'sim' && !item.ativo) return false;
    if (ativo === 'nao' && item.ativo) return false;
    if (!term) return true;
    const haystack = [item.descricao, item.tipo, item.periodicidade, item.oficina].join(' ').toLowerCase();
    return haystack.includes(term);
  });
}

export default function PlanosPanel({ apiClient, onCountChange, autoLoad }: PlanosPanelProps) {
  const [data, setData] = useState<PlanoResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [ativoFiltro, setAtivoFiltro] = useState<FiltroAtivo>('');
  const [exporting, setExporting] = useState(false);

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

  const handleExport = async () => {
    if (!data) return;
    setExporting(true);
    try {
      const res = await apiClient.exportarPlanos(filtered);
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const disposition = res.headers.get('Content-Disposition') ?? '';
      const match = disposition.match(/filename="?([^"]+)"?/);
      a.download = match ? match[1] : 'planos.xlsx';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao exportar');
    } finally {
      setExporting(false);
    }
  };

  useEffect(() => {
    if (autoLoad) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered: Plano[] = data ? filterItems(data.itens, search, ativoFiltro) : [];

  return (
    <div>
      <div className="toolbar">
        <button className="btn-primary" onClick={load} disabled={loading}>
          {loading ? 'Carregando…' : 'Carregar Planos'}
        </button>
        <button className="btn-success" onClick={handleExport} disabled={!data || exporting}>
          {exporting ? 'Exportando…' : 'Exportar Excel'}
        </button>
        <select
          value={ativoFiltro}
          onChange={(e) => setAtivoFiltro(e.target.value as FiltroAtivo)}
          aria-label="Filtrar por ativo"
        >
          <option value="">Ativo: todos</option>
          <option value="sim">Sim</option>
          <option value="nao">Não</option>
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
