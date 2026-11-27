import { useEffect, useState } from 'react';
import { mensagemDeErro } from '../../shared/api/http';
import type { UnitApiClient } from '../../shared/api/client';
import type { Habilidade } from '../../shared/api/types';
import { useAsync } from '../../shared/hooks/useAsync';
import Modal, { ConfirmDialog } from '../../shared/ui/Modal';
import { useToast } from '../../shared/ui/Toast';
import { Alert, Button, Chip, EmptyState, KpiCard, Spinner } from '../../shared/ui/ui';
import { calcBarWidths } from '../../shared/utils/barChart';
import { formatBR } from '../../shared/utils/dateUtils';

interface Props {
  client: UnitApiClient;
  nome: string;
  dataIni?: string;
  dataFim?: string;
  onClose: () => void;
  onChanged?: () => void;
}

export default function ColaboradorModal({ client, nome, dataIni, dataFim, onClose, onChanged }: Props) {
  const toast = useToast();
  const { data, loading, error, reload } = useAsync(() => client.fetchColaborador(nome, dataIni, dataFim), [client, nome, dataIni, dataFim]);
  const [catalogo, setCatalogo] = useState<Habilidade[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [novaHab, setNovaHab] = useState('');
  const [confirmarStatus, setConfirmarStatus] = useState(false);
  const [motivoBloqueio, setMotivoBloqueio] = useState<string | null>(null);
  const [admissao, setAdmissao] = useState('');
  const [desligamento, setDesligamento] = useState('');

  useEffect(() => { client.fetchHabilidades().then((r) => setCatalogo(r.itens)).catch(() => {}); }, [client]);
  useEffect(() => {
    if (data) { setAdmissao(data.data_admissao ?? ''); setDesligamento(data.data_desligamento ?? ''); }
  }, [data]);

  const executar = async (acao: () => Promise<unknown>, ok: string) => {
    setSalvando(true);
    try {
      await acao();
      toast.success(ok);
      onChanged?.();
      reload();
    } catch (e) {
      toast.error(mensagemDeErro(e));
    } finally {
      setSalvando(false);
    }
  };

  const disponiveis = catalogo.filter((h) => !(data?.habilidades ?? []).includes(h.id));
  const tipos = data ? calcBarWidths(data.tipos_servico) : [];
  const equips = data ? calcBarWidths(data.equipamentos) : [];
  const vinculoMudou = !!data && (admissao !== (data.data_admissao ?? '') || desligamento !== (data.data_desligamento ?? ''));

  return (
    <Modal wide title={nome} onClose={onClose}
      subtitle={data && <span>{data.cargo} · {data.turno}{data.regime && data.regime !== '—' ? ` · ${data.regime}` : ''}</span>}>
      {loading && !data && <Spinner label="Carregando colaborador…" />}
      {error && <Alert tone="danger" action={<Button size="sm" onClick={reload}>Tentar de novo</Button>}>{error}</Alert>}

      {data && (
        <>
          <div className="row">
            <Chip tone={data.status === 'Ativo' ? 'success' : 'danger'}>{data.status}</Chip>
            {data.bloqueado && <Chip tone="warning">Bloqueado</Chip>}
            {!data.executa_os && <Chip tone="neutral">Não executa OS (gestão/administrativo)</Chip>}
            {data.limite_diario && <Chip tone="primary" dot={false}>Limite {data.limite_diario} OS/dia · {data.especialidade}</Chip>}
            <span className="grow" />
            <Button size="sm" disabled={salvando} onClick={() => setConfirmarStatus(true)}>
              {data.status === 'Ativo' ? 'Marcar como desligado' : 'Reativar'}
            </Button>
            <Button size="sm" disabled={salvando}
              onClick={() => (data.bloqueado ? executar(() => client.atualizarBloqueioColaborador(nome, false), 'Colaborador desbloqueado.') : setMotivoBloqueio(''))}>
              {data.bloqueado ? 'Desbloquear' : 'Bloquear'}
            </Button>
          </div>

          {data.bloqueado && (
            <Alert tone="warning"><b>Indisponível para recomendação.</b> {data.aviso ?? 'Motivo não informado.'}</Alert>
          )}
          {data.data_desligamento && (
            <Alert tone="info">
              Desligamento em <b>{formatBR(data.data_desligamento)}</b>: não é elegível a novas ordens a partir dessa data.
              O histórico de OS já atribuídas é preservado e pode ser revisado na aba Revisão.
            </Alert>
          )}

          <section className="kpis">
            <KpiCard label="OS em aberto" value={data.total_abertas} tone="warning" />
            <KpiCard label="OS no histórico do período" value={data.total_historico} tone="primary" />
          </section>

          <div className="card stack">
            <div className="card-title">Vínculo</div>
            <div className="row" style={{ alignItems: 'flex-end' }}>
              <div className="field"><label htmlFor="v-adm">Data de admissão</label>
                <input id="v-adm" type="date" className="input" value={admissao} onChange={(e) => setAdmissao(e.target.value)} /></div>
              <div className="field"><label htmlFor="v-desl">Data de desligamento</label>
                <input id="v-desl" type="date" className="input" value={desligamento} onChange={(e) => setDesligamento(e.target.value)} /></div>
              <Button variant="primary" disabled={!vinculoMudou || salvando} loading={salvando}
                onClick={() => executar(() => client.atualizarVinculoColaborador(nome, {
                  data_admissao: admissao || null, data_desligamento: desligamento || null,
                }), 'Vínculo atualizado.')}>
                Salvar vínculo
              </Button>
            </div>
            <div className="muted" style={{ fontSize: 12 }}>
              A pessoa deixa de ser elegível a partir do próprio dia do desligamento. Apague a data para remover a restrição.
            </div>
          </div>

          <div className="card stack">
            <div className="card-title">Habilidades</div>
            <div className="row">
              {data.habilidades.length === 0 && <span className="muted">Nenhuma habilidade cadastrada.</span>}
              {data.habilidades.map((id) => {
                const h = catalogo.find((x) => x.id === id);
                return (
                  <span key={id} className="chip c-primary nodot">
                    {h ? h.nome : id}
                    <button type="button" aria-label={`Remover habilidade ${h ? h.nome : id}`} disabled={salvando}
                      onClick={() => executar(() => client.removerHabilidade(nome, id), 'Habilidade removida.')}
                      style={{ color: 'inherit', fontWeight: 800 }}>×</button>
                  </span>
                );
              })}
            </div>
            <div className="row">
              <select className="select" style={{ flex: 1, maxWidth: 420 }} aria-label="Habilidade para adicionar" value={novaHab}
                onChange={(e) => setNovaHab(e.target.value)} disabled={salvando || disponiveis.length === 0}>
                <option value="">{disponiveis.length === 0 ? 'Todas as habilidades já cadastradas' : 'Selecione uma habilidade…'}</option>
                {disponiveis.map((h) => <option key={h.id} value={h.id}>{h.nome} ({h.categoria})</option>)}
              </select>
              <Button variant="primary" disabled={!novaHab || salvando}
                onClick={() => executar(async () => { await client.adicionarHabilidade(nome, novaHab); setNovaHab(''); }, 'Habilidade adicionada.')}>
                Adicionar
              </Button>
            </div>
          </div>

          <div className="card">
            <div className="card-title" style={{ marginBottom: 8 }}>OS abertas / em andamento</div>
            {data.os_abertas.length === 0 ? <div className="muted">Nenhuma OS em aberto em nome deste colaborador.</div> : (
              <div className="table-wrap" style={{ maxHeight: 260 }}>
                <table className="table">
                  <thead><tr><th scope="col">Nº OS</th><th scope="col">Abertura</th><th scope="col">Tipo</th><th scope="col">Setor</th><th scope="col">Situação</th></tr></thead>
                  <tbody>
                    {data.os_abertas.map((o) => (
                      <tr key={o.numero}><td className="mono strong">{o.numero}</td><td>{o.abertura}</td><td>{o.tipo}</td>
                        <td><div className="cell-clip" title={o.setor}>{o.setor}</div></td><td><Chip tone="warning">{o.situacao}</Chip></td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="card stack">
            <div className="card-title">Histórico do período</div>
            {tipos.length === 0 && equips.length === 0 ? <EmptyState title="Sem histórico no período" /> : (
              <>
                {tipos.length > 0 && <div className="label">Tipos de serviço</div>}
                {tipos.map((t) => <Barra key={t.tipo} label={t.tipo} qtd={t.qtd} pct={t.pct} />)}
                {equips.length > 0 && <div className="label" style={{ marginTop: 6 }}>Equipamentos</div>}
                {equips.map((t) => <Barra key={t.ativo} label={t.ativo} qtd={t.qtd} pct={t.pct} />)}
              </>
            )}
          </div>
        </>
      )}

      {confirmarStatus && data && (
        <ConfirmDialog
          title={data.status === 'Ativo' ? 'Marcar como desligado?' : 'Reativar colaborador?'}
          danger={data.status === 'Ativo'}
          confirmLabel={data.status === 'Ativo' ? 'Marcar como desligado' : 'Reativar'}
          loading={salvando}
          message={data.status === 'Ativo'
            ? <>Este status exclui <b>o mês inteiro</b> das recomendações. Para desligar a partir de uma data específica (preservando os dias já trabalhados), use <b>Data de desligamento</b> em Vínculo. O histórico não é apagado.</>
            : <>{nome} voltará a poder ser recomendado.</>}
          onCancel={() => setConfirmarStatus(false)}
          onConfirm={async () => {
            await executar(() => client.atualizarStatusColaborador(nome, data.status === 'Ativo' ? 'Desligado' : 'Ativo'), 'Status atualizado.');
            setConfirmarStatus(false);
          }}
        />
      )}

      {motivoBloqueio !== null && (
        <Modal title="Bloquear colaborador" onClose={() => setMotivoBloqueio(null)}
          footer={<>
            <Button onClick={() => setMotivoBloqueio(null)}>Cancelar</Button>
            <Button variant="danger" loading={salvando}
              onClick={async () => {
                await executar(() => client.atualizarBloqueioColaborador(nome, true, motivoBloqueio.trim() || 'Bloqueado manualmente — motivo não informado.'), 'Colaborador bloqueado.');
                setMotivoBloqueio(null);
              }}>Bloquear</Button>
          </>}>
          <div className="field">
            <label htmlFor="motivo">Motivo (aparece para quem consultar este colaborador)</label>
            <textarea id="motivo" className="textarea" rows={3} maxLength={500} value={motivoBloqueio}
              onChange={(e) => setMotivoBloqueio(e.target.value)} data-autofocus />
          </div>
        </Modal>
      )}
    </Modal>
  );
}

function Barra({ label, qtd, pct }: { label: string; qtd: number; pct: number }) {
  return (
    <div className="barrow">
      <div className="cell-clip" title={label} style={{ maxWidth: 200 }}>{label}</div>
      <div className="bar-track" role="img" aria-label={`${label}: ${qtd}`}><div className="bar-fill" style={{ width: `${pct}%` }} /></div>
      <div className="strong num" style={{ textAlign: 'right' }}>{qtd}</div>
    </div>
  );
}
