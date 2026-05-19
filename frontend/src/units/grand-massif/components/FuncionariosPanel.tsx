import { useState, useCallback, useEffect } from 'react';
import { fetchTasksPorFuncionario } from '../api/client';
import type { FuncionarioTask, FuncionarioTaskResponse } from '../api/types';

interface FuncionariosPanelProps {
  dataIni?: string;
  dataFim?: string;
  onCountChange?: (count: number) => void;
  onSelectColaborador?: (nome: string) => void;
  autoLoad?: boolean;
}

function turnoBadgeClass(turno: string): string {
  const t = turno.toLowerCase();
  if (t.includes('manhã') || t.includes('manha') || t.includes('a')) return 'b-blue';
  if (t.includes('tarde') || t.includes('b')) return 'b-warn';
  if (t.includes('noite') || t.includes('c')) return 'b-purple';
  return 'b-gray';
}

function regimeBadgeClass(regime: string): string {
  const r = regime.toLowerCase();
  if (r.includes('12') || r.includes('folga')) return 'b-purple';
  if (r.includes('comercial') || r.includes('adm')) return 'b-blue';
  return 'b-gray';
}

export default function FuncionariosPanel({ dataIni, dataFim, onCountChange, onSelectColaborador, autoLoad }: FuncionariosPanelProps) {
  const [data, setData] = useState<FuncionarioTaskResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchTasksPorFuncionario(dataIni, dataFim);
      setData(result);
      onCountChange?.(result.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar tarefas por funcionário');
    } finally {
      setLoading(false);
    }
  }, [dataIni, dataFim, onCountChange]);

  useEffect(() => {
    if (autoLoad || data) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataIni, dataFim]);

  const filtered: FuncionarioTask[] = data
    ? data.itens
        .filter((f) => f.funcionario.toLowerCase().includes(search.trim().toLowerCase()))
        .sort((a, b) => b.total_tasks - a.total_tasks)
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
          placeholder="Buscar funcionário…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Busca por funcionário"
        />
      </div>

      {(loading || error) && (
        <div className="status-bar">
          {loading && <span className="spinner" aria-hidden="true" />}
          {loading && <span>Carregando tarefas por funcionário…</span>}
          {error && <span role="alert" style={{ color: 'var(--color-danger)' }}>{error}</span>}
        </div>
      )}

      {!data && !loading && !error && (
        <div className="empty">Clique em "Carregar" para visualizar as tarefas por funcionário.</div>
      )}

      {data && !loading && (
        <>
          {filtered.length === 0 ? (
            <div className="empty">Nenhum funcionário encontrado.</div>
          ) : (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px' }}>
              {filtered.map((func) => (
                <div
                  key={func.funcionario}
                  style={{
                    background: 'var(--color-surface)',
                    borderRadius: 'var(--radius-lg)',
                    boxShadow: 'var(--shadow-md)',
                    border: '1px solid var(--color-border)',
                    borderTop: '4px solid var(--color-primary)',
                    width: '320px',
                    flexShrink: 0,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      padding: '12px 16px',
                      borderBottom: '1px solid var(--color-border)',
                      background: 'var(--color-primary-hover)',
                      display: 'flex',
                      alignItems: 'flex-start',
                      justifyContent: 'space-between',
                      gap: 8,
                    }}
                  >
                    <div style={{ minWidth: 0 }}>
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={() => onSelectColaborador?.(func.funcionario)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') onSelectColaborador?.(func.funcionario);
                        }}
                        style={{
                          fontWeight: 700,
                          fontSize: '0.9rem',
                          color: 'var(--color-primary)',
                          cursor: onSelectColaborador ? 'pointer' : 'default',
                          textDecoration: onSelectColaborador ? 'underline' : 'none',
                          wordBreak: 'break-word',
                        }}
                      >
                        {func.funcionario}
                      </div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--color-text-muted)', marginTop: 2 }}>
                        {func.cargo || '—'}
                      </div>
                    </div>
                    <span className="badge b-blue" style={{ flexShrink: 0 }}>{func.total_tasks} OS</span>
                  </div>

                  <div style={{ padding: '10px 16px' }}>
                    <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
                      <span className={`badge ${turnoBadgeClass(func.turno)}`}>{func.turno || '—'}</span>
                      <span className={`badge ${regimeBadgeClass(func.regime)}`}>{func.regime || '—'}</span>
                    </div>
                    {func.tasks.length === 0 ? (
                      <div style={{ fontSize: '0.78rem', color: 'var(--color-text-muted)' }}>Sem tarefas no período.</div>
                    ) : (
                      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {func.tasks.map((task) => (
                          <li
                            key={task.numero}
                            style={{
                              fontSize: '0.78rem',
                              padding: '4px 8px',
                              background: '#f7f9ff',
                              borderRadius: 'var(--radius-sm)',
                              display: 'flex',
                              gap: 6,
                              alignItems: 'center',
                              flexWrap: 'wrap',
                            }}
                          >
                            <span style={{ fontWeight: 700, color: 'var(--color-primary)' }}>{task.numero}</span>
                            <span style={{ color: 'var(--color-text-secondary)' }}>{task.tipo}</span>
                            <span className="badge b-gray">{task.setor}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
