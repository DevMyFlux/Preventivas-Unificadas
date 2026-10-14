import { useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import type { UnitApiClient } from '../../shared/api/client';
import { useAsync } from '../../shared/hooks/useAsync';
import { mensagemDeErro } from '../../shared/api/http';
import type { Transferencia } from '../../shared/api/types';
import { useToast } from '../../shared/ui/Toast';
import { Alert, Button, Chip, EmptyState, KpiCard, PageHead, TableSkeleton, Tabs } from '../../shared/ui/ui';
import { formatBR, formatDateTimeBR } from '../../shared/utils/dateUtils';
import { HINT_RESPONSAVEL, toneDoResponsavel } from '../../shared/utils/status';

const ORDEM = ['Gestão', 'Desligado', 'Genérico', 'Bloqueado', 'Sem responsável'];

export default function RevisaoPanel({ client, onCount, podeAtribuir = false }: { client: UnitApiClient; onCount?: (n: number) => void; podeAtribuir?: boolean }) {
  const { data, loading, error, reload } = useAsync(() => client.fetchRevisao(), [client]);
  const [filtro, setFiltro] = useState('');
  const [aba, setAba] = useState<'ordens' | 'planos' | 'cargo' | 'transferencias'>('ordens');
  const transf = useAsync(() => client.fetchTransferencias(), [client], aba === 'transferencias');
  const nPlanos = data?.planos_responsavel_invalido?.length ?? null;
  const nCargo = data?.cargo_fora_da_regra?.length ?? null;
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
        {podeAtribuir ? <>Para preencher o executante, use <b>Atribuição</b> (conferência e aprovação).</> : <>A troca do responsável é feita pela administração.</>}
      </Alert>

      {error && <Alert tone="danger" action={<Button size="sm" onClick={reload}>Tentar de novo</Button>}>{error}</Alert>}

      <Tabs label="Seções da revisão" value={aba} onChange={setAba} tabs={[
        { key: 'ordens', label: 'Ordens a revisar', count: data?.total ?? null },
        { key: 'planos', label: 'Planos com responsável inválido', count: nPlanos },
        { key: 'cargo', label: 'Cargo fora da regra', count: nCargo },
        { key: 'transferencias', label: 'Transferências' },
      ]} />

      {aba === 'planos' && data && <PlanosInvalidos itens={data.planos_responsavel_invalido} />}
      {aba === 'cargo' && data && <CargoForaDaRegra itens={data.cargo_fora_da_regra} />}
      {aba === 'transferencias' && (
        <Transferencias carregando={transf.loading && !transf.data} erro={transf.error} itens={transf.data?.itens ?? []}
          nota={transf.data?.nota} onSalvar={async (id, motivo) => { await client.anotarMotivoTransferencia(id, motivo); transf.reload(); }}
          onRecarregar={transf.reload} />
      )}

      {aba === 'ordens' && (<>
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
      </>)}
    </div>
  );
}

function PlanosInvalidos({ itens }: { itens: NonNullable<import('../../shared/api/types').RevisaoResponse['planos_responsavel_invalido']> | null }) {
  if (itens === null) return <Alert tone="warning">Os planos não puderam ser consultados agora. Tente atualizar.</Alert>;
  if (itens.length === 0) return <EmptyState icon="checkCircle" title="Nenhum plano com responsável padrão inválido" />;
  return (
    <>
      <Alert tone="info">
        Cada OS nasce com o responsável padrão do plano. Estes planos têm como padrão alguém que não é executante válido
        (gestão, desligado, genérico ou sem identificação). Corrija o plano no Neovero para as próximas OS já nascerem corretas.
        “Não identificado” = nenhuma OS aberta permite descobrir o nome desse responsável — confira no cadastro do plano.
      </Alert>
      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">Planos com responsável padrão inválido</caption>
          <thead><tr><th scope="col">Plano</th><th scope="col">Responsável padrão</th><th scope="col">Situação</th><th scope="col" className="num">OS abertas</th></tr></thead>
          <tbody>
            {itens.map((p) => (
              <tr key={p.plano_id}>
                <td className="strong">{p.plano}</td>
                <td>{p.responsavel_nome ?? <span className="muted">{p.responsavel_id ? `id ${p.responsavel_id}` : '—'}</span>}</td>
                <td><Chip tone={toneDoResponsavel(p.status)}>{p.status}</Chip></td>
                <td className="num">{p.os_abertas}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function CargoForaDaRegra({ itens }: { itens: { os_numero: string; data_prev: string; plano: string; status: string; responsavel_atual: string | null; desvio: string }[] }) {
  if (itens.length === 0) {
    return <EmptyState icon="checkCircle" title="Nenhuma OS fora da regra de cargo">
      Esta unidade pode não ter regras de cargo por plano, ou todas as OS abertas estão com o cargo exigido.</EmptyState>;
  }
  return (
    <>
      <Alert tone="info">OS já atribuídas a um executante válido, mas de cargo diferente do que o plano exige. Só sinalização: nenhuma OS é reatribuída.</Alert>
      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">OS com cargo fora da regra</caption>
          <thead><tr><th scope="col">OS</th><th scope="col">Data</th><th scope="col">Plano</th><th scope="col">Status</th><th scope="col">Executante atual</th><th scope="col">Desvio</th></tr></thead>
          <tbody>
            {itens.map((i) => (
              <tr key={i.os_numero}>
                <td className="mono strong">{i.os_numero}</td><td>{i.data_prev}</td><td className="cell-clip" title={i.plano}>{i.plano}</td>
                <td>{i.status}</td><td>{i.responsavel_atual ?? '—'}</td><td style={{ color: 'var(--warning-text)' }}>{i.desvio}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Transferencias({ itens, carregando, erro, nota, onSalvar, onRecarregar }: {
  itens: Transferencia[]; carregando: boolean; erro: string | null; nota?: string;
  onSalvar: (id: number, motivo: string) => Promise<void>; onRecarregar: () => void;
}) {
  const toast = useToast();
  const [editando, setEditando] = useState<number | null>(null);
  const [motivo, setMotivo] = useState('');
  const [salvando, setSalvando] = useState(false);
  const salvar = async (e: FormEvent) => {
    e.preventDefault();
    if (editando === null) return;
    setSalvando(true);
    try {
      await onSalvar(editando, motivo);
      toast.success('Motivo registrado.');
      setEditando(null);
    } catch (err) {
      toast.error(mensagemDeErro(err));
    } finally {
      setSalvando(false);
    }
  };
  if (erro) return <Alert tone="danger" action={<Button size="sm" onClick={onRecarregar}>Tentar de novo</Button>}>{erro}</Alert>;
  if (carregando) return <TableSkeleton rows={5} cols={5} />;
  return (
    <>
      <Alert tone="info">
        Transferências de responsável <b>observadas</b> pelo sistema (o Neovero só informa o responsável atual).
        {nota ? ` ${nota}` : ' O motivo é anotado por uma pessoa.'}
      </Alert>
      {itens.length === 0 ? <EmptyState icon="activity" title="Nenhuma transferência observada ainda" /> : (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Transferências de responsável</caption>
            <thead><tr><th scope="col">Quando</th><th scope="col">OS</th><th scope="col">De</th><th scope="col">Para</th><th scope="col">Motivo</th></tr></thead>
            <tbody>
              {itens.map((t) => (
                <tr key={t.id}>
                  <td>{formatDateTimeBR(t.observado_em)}</td>
                  <td><div className="mono strong">{t.os_numero}</div><div className="cell-sub cell-clip" title={t.plano ?? ''}>{t.plano}</div></td>
                  <td>{t.de ?? <span className="muted">sem responsável</span>}</td>
                  <td>{t.para ?? <span className="muted">sem responsável</span>}</td>
                  <td>
                    {editando === t.id ? (
                      <form className="row" onSubmit={salvar}>
                        <input className="input" aria-label={`Motivo da transferência da OS ${t.os_numero}`} value={motivo} maxLength={300}
                          onChange={(e) => setMotivo(e.target.value)} data-autofocus />
                        <Button size="sm" variant="primary" type="submit" loading={salvando}>Salvar</Button>
                        <Button size="sm" type="button" onClick={() => setEditando(null)} disabled={salvando}>Cancelar</Button>
                      </form>
                    ) : (
                      <div className="row">
                        <span>{t.motivo ?? <span className="muted">não informado</span>}</span>
                        <Button size="sm" variant="ghost" icon="edit" aria-label={`Anotar motivo da OS ${t.os_numero}`}
                          onClick={() => { setEditando(t.id); setMotivo(t.motivo ?? ''); }} />
                      </div>
                    )}
                    {t.motivo && t.motivo_por && editando !== t.id && <div className="cell-sub">por {t.motivo_por}</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
