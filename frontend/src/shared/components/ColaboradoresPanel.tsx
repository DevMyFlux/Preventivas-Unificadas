import { useState, useCallback, useEffect } from 'react';
import type { buildUnitClient } from '../api/client';
import type { Colaborador, ColaboradorResponse } from '../api/types';
import ColaboradorModal from './ColaboradorModal';

type UnitApiClient = ReturnType<typeof buildUnitClient>;

interface ColaboradoresPanelProps {
  apiClient: UnitApiClient;
  onCountChange?: (count: number) => void;
  onSelectColaborador?: (nome: string) => void;
  autoLoad?: boolean;
}

export default function ColaboradoresPanel({
  apiClient,
  onCountChange,
  onSelectColaborador,
  autoLoad,
}: ColaboradoresPanelProps) {
  const [data, setData] = useState<ColaboradorResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [selectedNome, setSelectedNome] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiClient.fetchColaboradores();
      setData(result);
      onCountChange?.(result.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar colaboradores');
    } finally {
      setLoading(false);
    }
  }, [apiClient, onCountChange]);

  useEffect(() => {
    if (autoLoad) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRowClick = (item: Colaborador) => {
    if (onSelectColaborador) {
      onSelectColaborador(item.funcionario);
    } else {
      setSelectedNome(item.funcionario);
    }
  };

  const filtered: Colaborador[] = data
    ? data.itens.filter((c) => {
        const q = search.trim().toLowerCase();
        if (!q) return true;
        return (
          c.funcionario.toLowerCase().includes(q) ||
          c.cargo.toLowerCase().includes(q) ||
          c.turno.toLowerCase().includes(q) ||
          c.regime.toLowerCase().includes(q) ||
          c.horario.toLowerCase().includes(q)
        );
      })
    : [];

  return (
    <div>
      <div className="toolbar">
        <button className="btn-primary" onClick={load} disabled={loading}>
          {loading ? 'Carregando…' : 'Carregar'}
        </button>
        <input
          type="text"
          className="search"
          placeholder="Buscar colaborador…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Busca por colaborador"
        />
      </div>

      {(loading || error) && (
        <div className="status-bar">
          {loading && <span className="spinner" aria-hidden="true" />}
          {loading && <span>Carregando colaboradores…</span>}
          {error && <span role="alert" style={{ color: 'var(--color-danger)' }}>{error}</span>}
        </div>
      )}

      {!data && !loading && !error && (
        <div className="empty">Clique em "Carregar" para visualizar os colaboradores.</div>
      )}

      {data && !loading && (
        <>
          {filtered.length === 0 ? (
            <div className="empty">Nenhum colaborador encontrado.</div>
          ) : (
            <div className="tbl-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Nome</th>
                    <th>Cargo</th>
                    <th>Turno</th>
                    <th>Regime</th>
                    <th>Horário</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((item) => (
                    <tr
                      key={item.funcionario}
                      onClick={() => handleRowClick(item)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td style={{ fontWeight: 600, color: 'var(--color-primary)' }}>
                        {item.funcionario}
                      </td>
                      <td>{item.cargo || '—'}</td>
                      <td>{item.turno || '—'}</td>
                      <td>{item.regime || '—'}</td>
                      <td>{item.horario || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {!onSelectColaborador && (
        <ColaboradorModal
          apiClient={apiClient}
          nome={selectedNome}
          onClose={() => setSelectedNome(null)}
        />
      )}
    </div>
  );
}
