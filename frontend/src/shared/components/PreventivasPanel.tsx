import { useState, useCallback } from 'react';
import type { buildUnitClient } from '../api/client';
import type { Preventiva, PreventivaResponse } from '../api/types';
import { filterPreventivas, type FiltroStatusOS, type FiltroRecomendacao } from '../utils/preventivasFilter';

type UnitApiClient = ReturnType<typeof buildUnitClient>;

interface PreventivasPanelProps {
  apiClient: UnitApiClient;
  dataIni?: string;
  dataFim?: string;
  onCountChange?: (count: number) => void;
}

export default function PreventivasPanel({ apiClient, dataIni, dataFim, onCountChange }: PreventivasPanelProps) {
  const [data, setData] = useState<PreventivaResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const [responsavel, setResponsavel] = useState('');
  const [localDataIni, setLocalDataIni] = useState('');
  const [localDataFim, setLocalDataFim] = useState('');
  const [search, setSearch] = useState('');
  const [statusOS, setStatusOS] = useState<FiltroStatusOS>('');
  const [recomendacao, setRecomendacao] = useState<FiltroRecomendacao>('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiClient.fetchPreventivas(dataIni, dataFim);
      setData(result);
      onCountChange?.(result.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao carregar preventivas');
    } finally {
      setLoading(false);
    }
  }, [apiClient, dataIni, dataFim, onCountChange]);

  const clearFilters = () => {
    setResponsavel('');
    setLocalDataIni('');
    setLocalDataFim('');
    setSearch('');
    setStatusOS('');
    setRecomendacao('');
    setData(null);
  };

  const handleExport = async () => {
    if (!data) return;
    setExporting(true);
    try {
      const res = await apiClient.exportarPreventivas(filtered, localDataIni, localDataFim);
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const disposition = res.headers.get('Content-Disposition') ?? '';
      const match = disposition.match(/filename="?([^"]+)"?/);
      a.download = match ? match[1] : 'preventivas.xlsx';
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

  const filtered: Preventiva[] = data
    ? filterPreventivas(data.itens, responsavel, localDataIni, localDataFim, search, statusOS, recomendacao)
    : [];

  const previstas = filtered.filter((p) => !p.atrasada && !p.ja_com_os);
  const comRecomendacao = filtered.filter((p) => p.recomendado).length;
  const emAtraso = filtered.filter((p) => p.atrasada).length;

  return (
    <div>
      <div className="cards">
        <div className="card">
          <div className="num">{data ? previstas.length : '—'}</div>
          <div className="lbl">Previstas</div>
        </div>
        <div className="card green">
          <div className="num">{data ? comRecomendacao : '—'}</div>
          <div className="lbl">Com Recomendação</div>
        </div>
        <div className="card red">
          <div className="num">{data ? emAtraso : '—'}</div>
          <div className="lbl">Em Atraso</div>
        </div>
      </div>

      <div className="toolbar">
        <button className="btn-primary" onClick={load} disabled={loading}>
          {loading ? 'Carregando…' : 'Buscar Preventivas Previstas'}
        </button>
        <button className="btn-success" onClick={handleExport} disabled={!data || exporting}>
          {exporting ? 'Exportando…' : 'Exportar Excel'}
        </button>
        <input
          type="text"
          placeholder="Responsável…"
          value={responsavel}
          onChange={(e) => setResponsavel(e.target.value)}
          aria-label="Filtrar por responsável"
        />
        <label style={{ fontSize: '0.83rem', color: 'var(--color-text-secondary)' }}>
          De
          <input
            type="date"
            value={localDataIni}
            onChange={(e) => setLocalDataIni(e.target.value)}
            aria-label="Data inicial local"
            style={{ marginLeft: 6 }}
          />
        </label>
        <label style={{ fontSize: '0.83rem', color: 'var(--color-text-secondary)' }}>
          Até
          <input
            type="date"
            value={localDataFim}
            onChange={(e) => setLocalDataFim(e.target.value)}
            aria-label="Data final local"
            style={{ marginLeft: 6 }}
          />
        </label>
        <select
          value={statusOS}
          onChange={(e) => setStatusOS(e.target.value as FiltroStatusOS)}
          aria-label="Filtrar por status da OS"
        >
          <option value="">Status OS: todos</option>
          <option value="Aberta">Aberta</option>
          <option value="Em Andamento">Em Andamento</option>
          <option value="sem_os">Sem OS vinculada</option>
        </select>
        <select
          value={recomendacao}
          onChange={(e) => setRecomendacao(e.target.value as FiltroRecomendacao)}
          aria-label="Filtrar por recomendação"
        >
          <option value="">Recomendação: todas</option>
          <option value="com">Com recomendação</option>
          <option value="sem">Sem candidato</option>
        </select>
        <button className="btn-neutral" onClick={clearFilters}>Limpar filtros</button>
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
          {loading && <span>Carregando preventivas…</span>}
          {error && <span role="alert" style={{ color: 'var(--color-danger)' }}>{error}</span>}
        </div>
      )}

      {data && (
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th>Data Prevista</th>
                <th>Dia</th>
                <th>Plano</th>
                <th>Tipo</th>
                <th>Oficina</th>
                <th>Equipamento</th>
                <th>Setor</th>
                <th>OS Vinculada</th>
                <th>Status OS</th>
                <th>Recomendado</th>
                <th>Cargo</th>
                <th>Escala</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={12} className="empty">Nenhum registro encontrado.</td></tr>
              ) : (
                filtered.map((item, idx) => (
                  <tr
                    key={`${item.data_prev}-${item.plano}-${idx}`}
                    className={!item.recomendado ? 'row-danger' : ''}
                  >
                    <td>
                      {item.data_prev}
                      {item.atrasada && (
                        <span className="badge b-danger" style={{ marginLeft: 6 }}>Em atraso</span>
                      )}
                    </td>
                    <td>{item.dia_par}</td>
                    <td>{item.plano}</td>
                    <td>{item.tipo}</td>
                    <td>{item.oficina}</td>
                    <td>{item.equipamento}</td>
                    <td>{item.setor}</td>
                    <td>{item.os_vinculada}</td>
                    <td>{item.os_situacao}</td>
                    <td>{item.recomendado ?? '—'}</td>
                    <td>{item.cargo}</td>
                    <td>{item.escala}</td>
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
