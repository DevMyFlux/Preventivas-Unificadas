import { useEffect, useState } from 'react';
import type { UnitApiClient } from '../../shared/api/client';
import { useAsync } from '../../shared/hooks/useAsync';
import { Alert, Button, Chip, EmptyState, KpiCard, PageHead, TableSkeleton } from '../../shared/ui/ui';
import { formatBR } from '../../shared/utils/dateUtils';
import { HINT_RESPONSAVEL, toneDoResponsavel } from '../../shared/utils/status';

const ORDEM = ['Gestão', 'Desligado', 'Genérico', 'Bloqueado', 'Sem responsável'];

export default function RevisaoPanel({ client, onCount }: { client: UnitApiClient; onCount?: (n: number) => void }) {
  const { data, loading, error, reload } = useAsync(() => client.fetchRevisao(), [client]);
  const [filtro, setFiltro] = useState('');
  useEffect(() => { if (data) onCount?.(data.total); }, [data, onCount]);

  const itens = data ? data.itens.filter((i) => !filtro || i.responsavel_status === filtro) : [];

  return (
    <div className="stack">
      <PageHead
        title="Revisão de responsáveis"
        subtitle="OS abertas ou em andamento cujo responsável no Neovero não é um executante válido. Somente leitura: nada é reatribuído automaticamente."
        actions={<Button icon="refresh" onClick={reload} loading={loading}>Atualizar</Button>}
      />

      <Alert tone="info">
        O Neovero cria cada OS com o <b>responsável padrão do plano</b> — hoje o gestor da unidade. Aqui aparecem as ordens em nome de
        gestão, de nomes genéricos (ex.: “ELÉTRICA - DIURNO”), de colaboradores desligados, bloqueados ou sem responsável.
        Para preencher o executante, use <b>Atribuição</b> (conferência e aprovação).
      </Alert>

      {error && <Alert tone="danger" action={<Button size="sm" onClick={reload}>Tentar de novo</Button>}>{error}</Alert>}

      <section className="kpis" aria-label="Resumo da revisão">
        <KpiCard label="Total para revisar" value={data?.total ?? null} tone="primary" loading={loading && !data}
          onClick={() => setFiltro('')} pressed={filtro === ''} />
        {ORDEM.map((s) => (
          <KpiCard key={s} label={s} value={data?.por_status[s] ?? (data ? 0 : null)} loading={loading && !data}
            tone={s === 'Desligado' || s === 'Bloqueado' ? 'danger' : s === 'Sem responsável' ? 'purple' : 'warning'}
            hint={HINT_RESPONSAVEL[s]} onClick={() => setFiltro(filtro === s ? '' : s)} pressed={filtro === s} />
        ))}
      </section>

      {loading && !data ? <TableSkeleton rows={8} cols={6} /> : data && itens.length === 0 ? (
        <EmptyState icon="checkCircle" title="Nada para revisar">Todas as ordens abertas têm um executante válido.</EmptyState>
      ) : data ? (
        <>
          {!filtro && data.por_responsavel.length > 0 && (
            <div className="card">
              <div className="card-title" style={{ marginBottom: 8 }}>Ordens por responsável no Neovero</div>
              <div className="row">
                {data.por_responsavel.slice(0, 12).map((r) => (
                  <Chip key={`${r.status}-${r.responsavel}`} tone={toneDoResponsavel(r.status)} title={HINT_RESPONSAVEL[r.status]}>
                    {r.responsavel} · {r.ordens}
                  </Chip>
                ))}
              </div>
            </div>
          )}
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Ordens com responsável a revisar</caption>
              <thead>
                <tr><th scope="col">OS</th><th scope="col">Data</th><th scope="col">Plano</th><th scope="col">Responsável no Neovero</th><th scope="col">Situação do responsável</th><th scope="col">OS</th></tr>
              </thead>
              <tbody>
                {itens.slice(0, 500).map((i) => (
                  <tr key={i.os_numero} className={i.atrasada ? 'row-late' : ''}>
                    <td className="mono strong">{i.os_numero}</td>
                    <td>{i.data_prev}{i.atrasada && <> <Chip tone="danger" dot={false}>Atrasada</Chip></>}</td>
                    <td><div className="cell-clip strong" title={i.plano}>{i.plano}</div><div className="cell-sub">{i.oficina}</div></td>
                    <td>{i.responsavel_atual ?? <span className="muted">—</span>}</td>
                    <td>
                      <Chip tone={toneDoResponsavel(i.responsavel_status)} title={HINT_RESPONSAVEL[i.responsavel_status]}>{i.responsavel_status}</Chip>
                      {i.data_desligamento && <div className="cell-sub">Desligado em {formatBR(i.data_desligamento)}</div>}
                    </td>
                    <td>{i.situacao}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {itens.length > 500 && <div className="muted">Mostrando as primeiras 500 de {itens.length}. Use o filtro por situação para refinar.</div>}
          <div className="muted" style={{ fontSize: 12 }}>{data.nota}</div>
        </>
      ) : null}
    </div>
  );
}
