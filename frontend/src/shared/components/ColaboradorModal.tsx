import { useEffect, useState } from 'react';
import type { buildUnitClient } from '../api/client';
import type { ColaboradorDetail } from '../api/types';
import { calcBarWidths } from '../utils/barChart';

type UnitApiClient = ReturnType<typeof buildUnitClient>;

interface ColaboradorModalProps {
  apiClient: UnitApiClient;
  nome: string | null;
  onClose: () => void;
}

const BAR_COLORS = [
  'var(--color-primary)',
  'var(--color-success)',
  'var(--color-warning)',
  'var(--color-purple)',
  'var(--color-danger)',
];

export default function ColaboradorModal({ apiClient, nome, onClose }: ColaboradorModalProps) {
  const [data, setData] = useState<ColaboradorDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!nome) return;
    setData(null);
    setError(null);
    setLoading(true);
    apiClient
      .fetchColaborador(nome)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : 'Erro ao carregar colaborador'))
      .finally(() => setLoading(false));
  }, [apiClient, nome]);

  if (!nome) return null;

  const tiposComPct = data ? calcBarWidths(data.tipos_servico) : [];
  const equipComPct = data ? calcBarWidths(data.equipamentos) : [];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Detalhes de ${nome}`}
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.55)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--color-surface)',
          borderRadius: 'var(--radius-xl)',
          boxShadow: '0 8px 32px rgba(0,0,0,0.25)',
          width: '100%',
          maxWidth: '720px',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            background: 'var(--color-primary)',
            color: '#fff',
            padding: '16px 20px',
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 12,
            flexShrink: 0,
          }}
        >
          <div>
            <div style={{ fontWeight: 800, fontSize: '1.05rem' }}>{nome}</div>
            {data && (
              <div style={{ fontSize: '0.82rem', opacity: 0.85, marginTop: 3 }}>
                {data.cargo} &nbsp;·&nbsp; {data.turno}
              </div>
            )}
          </div>
          <button
            aria-label="Fechar"
            onClick={onClose}
            style={{
              background: 'rgba(255,255,255,0.15)',
              color: '#fff',
              padding: '4px 10px',
              fontSize: '1rem',
              fontWeight: 700,
              borderRadius: 'var(--radius-sm)',
              flexShrink: 0,
            }}
          >
            ✕
          </button>
        </div>

        <div style={{ overflowY: 'auto', padding: '20px', flex: 1 }}>
          {loading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--color-text-muted)' }}>
              <span className="spinner" aria-hidden="true" />
              <span>Carregando…</span>
            </div>
          )}

          {error && (
            <div role="alert" style={{ color: 'var(--color-danger)', fontWeight: 600 }}>
              {error}
            </div>
          )}

          {data && !loading && (
            <>
              <div className="cards">
                <div className="card red">
                  <div className="num">{data.total_abertas}</div>
                  <div className="lbl">OS em aberto</div>
                </div>
                <div className="card">
                  <div className="num">{data.total_historico}</div>
                  <div className="lbl">OS no histórico</div>
                </div>
              </div>

              <SectionTitle>OS Abertas / Em Andamento</SectionTitle>
              {data.os_abertas.length === 0 ? (
                <div className="empty" style={{ padding: '20px 0' }}>Nenhuma OS em aberto.</div>
              ) : (
                <div className="tbl-wrap" style={{ marginBottom: 24 }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Nº OS</th>
                        <th>Abertura</th>
                        <th>Tipo</th>
                        <th>Setor</th>
                        <th>Situação</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.os_abertas.map((os) => (
                        <tr key={os.numero}>
                          <td style={{ fontWeight: 700, color: 'var(--color-primary)' }}>{os.numero}</td>
                          <td>{os.abertura}</td>
                          <td>{os.tipo}</td>
                          <td>{os.setor}</td>
                          <td><span className="badge b-warn">{os.situacao}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <SectionTitle>Tipos de Serviço (histórico)</SectionTitle>
              {tiposComPct.length === 0 ? (
                <div className="empty" style={{ padding: '20px 0' }}>Sem dados.</div>
              ) : (
                <div style={{ marginBottom: 24 }}>
                  {tiposComPct.map((item, idx) => (
                    <BarRow key={item.tipo} label={item.tipo} qtd={item.qtd} pct={item.pct} color={BAR_COLORS[idx % BAR_COLORS.length]} />
                  ))}
                </div>
              )}

              <SectionTitle>Equipamentos (histórico)</SectionTitle>
              {equipComPct.length === 0 ? (
                <div className="empty" style={{ padding: '20px 0' }}>Sem dados.</div>
              ) : (
                <div style={{ marginBottom: 8 }}>
                  {equipComPct.map((item, idx) => (
                    <BarRow key={item.ativo} label={item.ativo} qtd={item.qtd} pct={item.pct} color={BAR_COLORS[idx % BAR_COLORS.length]} />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontWeight: 700,
        fontSize: '0.88rem',
        color: 'var(--color-primary)',
        borderBottom: '2px solid var(--color-primary-light)',
        paddingBottom: 6,
        marginBottom: 12,
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
      }}
    >
      {children}
    </div>
  );
}

interface BarRowProps { label: string; qtd: number; pct: number; color: string; }

function BarRow({ label, qtd, pct, color }: BarRowProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, fontSize: '0.82rem' }}>
      <div
        style={{ width: 180, flexShrink: 0, color: 'var(--color-text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
        title={label}
      >
        {label}
      </div>
      <div style={{ flex: 1, background: '#eee', borderRadius: 4, height: 14, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.3s ease' }} />
      </div>
      <div style={{ width: 32, textAlign: 'right', fontWeight: 700, color: 'var(--color-text)' }}>{qtd}</div>
    </div>
  );
}
