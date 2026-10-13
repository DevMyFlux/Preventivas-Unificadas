import { useState } from 'react';
import { mensagemDeErro } from '../../shared/api/http';
import type { UnitApiClient } from '../../shared/api/client';
import type { Proposta } from '../../shared/api/types';
import { useAsync } from '../../shared/hooks/useAsync';
import { ConfirmDialog } from '../../shared/ui/Modal';
import { useToast } from '../../shared/ui/Toast';
import { Alert, Button, Chip, EmptyState, PageHead, TableSkeleton } from '../../shared/ui/ui';
import { formatBR, formatDateTimeBR } from '../../shared/utils/dateUtils';
import { HINT_RESPONSAVEL, toneDaProposta, toneDoResponsavel } from '../../shared/utils/status';

interface Props { client: UnitApiClient; dataIni: string; dataFim: string; onChanged?: () => void }

export default function AtribuicoesPanel({ client, dataIni, dataFim, onChanged }: Props) {
  const toast = useToast();
  const { data, loading, error, reload } = useAsync(() => client.fetchAtribuicoes(dataIni, dataFim), [client, dataIni, dataFim]);
  const [marcadas, setMarcadas] = useState<Set<number>>(new Set());
  const [ocupado, setOcupado] = useState(false);
  const [confirmarAplicar, setConfirmarAplicar] = useState<number[] | null>(null);

  const executar = async (fn: () => Promise<string>) => {
    setOcupado(true);
    try {
      toast.success(await fn());
      setMarcadas(new Set());
      reload();
      onChanged?.();
    } catch (e) {
      toast.error(mensagemDeErro(e));
    } finally {
      setOcupado(false);
    }
  };

  const alternar = (id: number) => setMarcadas((cur) => { const n = new Set(cur); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const automatizaveis = data?.fila.filter((f) => f.automatizavel) ?? [];
  const todasMarcadas = automatizaveis.length > 0 && automatizaveis.every((f) => marcadas.has(f.os_id));

  const criar = () => executar(async () => {
    const r = await client.criarPropostas(dataIni, dataFim, Array.from(marcadas));
    const criadas = r.resultado.filter((x) => x.criada).length;
    return `${criadas} proposta(s) criada(s); ${r.resultado.length - criadas} já existiam ou não eram automatizáveis.`;
  });
  const decidir = (ids: number[], acao: 'aprovar' | 'rejeitar') =>
    executar(async () => `${(await client.decidirPropostas(ids, acao)).atualizadas} proposta(s) ${acao === 'aprovar' ? 'aprovada(s)' : 'rejeitada(s)'}.`);
  const processar = (ids: number[], modo: 'simular' | 'aplicar') => executar(async () => {
    const r = await client.processarPropostas(ids, modo);
    const por = r.resultado.reduce<Record<string, number>>((a, x) => ({ ...a, [x.status]: (a[x.status] ?? 0) + 1 }), {});
    return Object.entries(por).map(([s, n]) => `${n} ${s}`).join(' · ') || 'Nada a processar.';
  });

  const aprovadas = (data?.propostas ?? []).filter((p) => p.status === 'aprovada');
  const integ = data?.integracao;

  return (
    <div className="stack">
      <PageHead
        title="Atribuição de executantes"
        subtitle="Fila de conferência: propostas do motor para as OS em nome de gestão, nomes genéricos ou desligados."
        actions={<Button icon="refresh" onClick={reload} loading={loading}>Atualizar</Button>}
      />

      {integ && (
        <Alert tone={integ.escrita_habilitada ? 'warning' : 'info'}>
          <b>{integ.escrita_habilitada ? (integ.simulacao ? 'Escrita habilitada em modo SIMULAÇÃO.' : 'Escrita no Neovero HABILITADA.') : 'Escrita no Neovero desabilitada.'}</b>{' '}
          {integ.aviso} Nenhuma ordem é alterada sem proposta <b>aprovada</b>, e a aplicação recusa se o responsável mudou desde a proposta
          ou se o limite diário seria excedido.
        </Alert>
      )}

      {error && <Alert tone="danger" action={<Button size="sm" onClick={reload}>Tentar de novo</Button>}>{error}</Alert>}

      <section className="card stack">
        <div className="card-head">
          <div className="card-title">Fila — {data ? data.fila.length : '…'} OS a preencher ({formatBR(dataIni)} a {formatBR(dataFim)} + atrasadas)</div>
          <Button variant="primary" icon="plus" disabled={marcadas.size === 0 || ocupado} onClick={criar} loading={ocupado}>
            Criar {marcadas.size || ''} proposta(s)
          </Button>
        </div>
        {loading && !data ? <TableSkeleton rows={5} cols={6} /> : data && data.fila.length === 0 ? (
          <EmptyState icon="checkCircle" title="Fila vazia">Nenhuma OS aberta precisa de executante neste período.</EmptyState>
        ) : data ? (
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Fila de atribuição</caption>
              <thead>
                <tr>
                  <th scope="col"><input type="checkbox" aria-label="Selecionar todas as automatizáveis" checked={todasMarcadas}
                    onChange={() => setMarcadas(todasMarcadas ? new Set() : new Set(automatizaveis.map((f) => f.os_id)))} /></th>
                  <th scope="col">OS</th><th scope="col">Data</th><th scope="col">Plano</th><th scope="col">Hoje no Neovero</th><th scope="col">Proposto</th>
                </tr>
              </thead>
              <tbody>
                {data.fila.slice(0, 400).map((f) => (
                  <tr key={f.os_id}>
                    <td><input type="checkbox" aria-label={`Selecionar OS ${f.os_numero}`} disabled={!f.automatizavel}
                      checked={marcadas.has(f.os_id)} onChange={() => alternar(f.os_id)} /></td>
                    <td className="mono strong">{f.os_numero}</td>
                    <td>{formatBR(f.data_iso)}</td>
                    <td><div className="cell-clip" title={f.plano}>{f.plano}</div></td>
                    <td>
                      {f.responsavel_atual ?? <span className="muted">—</span>}
                      <div><Chip tone={toneDoResponsavel(f.responsavel_status)} title={HINT_RESPONSAVEL[f.responsavel_status]}>{f.responsavel_status}</Chip></div>
                    </td>
                    <td>
                      {f.propostos.length ? <b>{f.propostos.join(' + ')}</b> : <Chip tone="purple">Requer intervenção</Chip>}
                      {f.motivo && <div className="cell-sub" style={{ whiteSpace: 'normal', maxWidth: 380 }}>{f.motivo}</div>}
                      {f.alertas.map((a) => <div key={a} className="cell-sub" style={{ color: 'var(--warning-text)' }}>⚠ {a}</div>)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <section className="card stack">
        <div className="card-head">
          <div className="card-title">Propostas ({data?.propostas.length ?? 0})</div>
          <div className="row">
            <Button size="sm" disabled={aprovadas.length === 0 || ocupado} onClick={() => processar(aprovadas.map((p) => p.id), 'simular')}>
              Simular aprovadas ({aprovadas.length})
            </Button>
            <Button size="sm" variant="danger" disabled={aprovadas.length === 0 || ocupado || !integ?.escrita_habilitada}
              title={integ?.escrita_habilitada ? undefined : 'Escrita desabilitada na configuração do servidor'}
              onClick={() => setConfirmarAplicar(aprovadas.map((p) => p.id))}>
              Aplicar no Neovero
            </Button>
          </div>
        </div>
        {data && data.propostas.length === 0 ? <div className="muted">Nenhuma proposta ainda. Marque itens da fila e crie propostas.</div> : data ? (
          <div className="table-wrap">
            <table className="table">
              <caption className="sr-only">Propostas de atribuição</caption>
              <thead><tr><th scope="col">OS</th><th scope="col">Data</th><th scope="col">De → Para</th><th scope="col">Status</th><th scope="col">Resultado</th><th scope="col">Ações</th></tr></thead>
              <tbody>
                {data.propostas.map((p) => <LinhaProposta key={p.id} p={p} ocupado={ocupado} onDecidir={decidir} />)}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      {confirmarAplicar && (
        <ConfirmDialog
          title="Aplicar no Neovero?" danger confirmLabel={integ?.simulacao ? 'Validar (simulação)' : 'Aplicar agora'} loading={ocupado}
          message={<>Serão processadas <b>{confirmarAplicar.length}</b> proposta(s) aprovada(s).{' '}
            {integ?.simulacao ? 'O servidor está em simulação: valida tudo, mas não envia alterações.' : 'Os responsáveis das OS serão ALTERADOS no Neovero.'}</>}
          onCancel={() => setConfirmarAplicar(null)}
          onConfirm={async () => { await processar(confirmarAplicar, 'aplicar'); setConfirmarAplicar(null); }}
        />
      )}
    </div>
  );
}

function LinhaProposta({ p, ocupado, onDecidir }: { p: Proposta; ocupado: boolean; onDecidir: (ids: number[], a: 'aprovar' | 'rejeitar') => void }) {
  return (
    <tr>
      <td className="mono strong">{p.os_numero}</td>
      <td>{formatBR(p.data_prevista)}</td>
      <td>{p.responsavel_original ?? '—'} → <b>{p.funcionario_proposto}</b></td>
      <td><Chip tone={toneDaProposta(p.status)}>{p.status}</Chip></td>
      <td><div className="cell-sub" style={{ whiteSpace: 'normal', maxWidth: 360 }}>{p.mensagem ?? `Criada por ${p.criado_por ?? '—'} em ${formatDateTimeBR(p.criado_em)}`}</div></td>
      <td>
        {p.status === 'proposta' && (
          <div className="row" style={{ gap: 4 }}>
            <Button size="sm" variant="primary" disabled={ocupado} onClick={() => onDecidir([p.id], 'aprovar')}>Aprovar</Button>
            <Button size="sm" disabled={ocupado} onClick={() => onDecidir([p.id], 'rejeitar')}>Rejeitar</Button>
          </div>
        )}
      </td>
    </tr>
  );
}
