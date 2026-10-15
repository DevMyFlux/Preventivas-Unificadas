import { useEffect, useMemo, useRef, useState } from 'react';
import { mensagemDeErro } from '../../shared/api/http';
import type { UnitApiClient } from '../../shared/api/client';
import type { PreventivasQuery, Preventiva } from '../../shared/api/types';
import { useAsync, useDebounced } from '../../shared/hooks/useAsync';
import DayPicker from '../../shared/ui/DayPicker';
import { useToast } from '../../shared/ui/Toast';
import { Alert, Button, Chip, EmptyState, KpiCard, PageHead, Pagination, TableSkeleton } from '../../shared/ui/ui';
import { formatDateTimeBR } from '../../shared/utils/dateUtils';
import { STATUS_EXECUCAO, toneDoStatus } from '../../shared/utils/status';

interface Props {
  client: UnitApiClient;
  dataIni: string;
  dataFim: string;
  onCount?: (n: number) => void;
  /** só administradores têm a tela de Regras; sem isto o aviso de nomes pendentes e o botão "Resolver" não aparecem */
  onIrParaRegras?: () => void;
}

const TURNOS = [
  { v: '', l: 'Turno: todos' }, { v: 'Diurno', l: 'Diurno' }, { v: 'Noturno', l: 'Noturno' }, { v: '—', l: 'Não informado' },
];

export default function PreventivasPanel({ client, dataIni, dataFim, onCount, onIrParaRegras }: Props) {
  const toast = useToast();
  const [status, setStatus] = useState<string[]>([]);
  const [atrasada, setAtrasada] = useState(false);
  const [revisao, setRevisao] = useState(false);
  const [requerIntervencao, setRequerIntervencao] = useState(false);
  const [turno, setTurno] = useState('');
  const [paridade, setParidade] = useState('');
  const [dias, setDias] = useState<string[]>([]);
  const [fIni, setFIni] = useState('');
  const [fFim, setFFim] = useState('');
  const [busca, setBusca] = useState('');
  const [responsavel, setResponsavel] = useState('');
  const [incluirAtrasadas, setIncluirAtrasadas] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(100);
  const [exportando, setExportando] = useState(false);
  const [maisFiltros, setMaisFiltros] = useState(false);
  const forcar = useRef(false);

  const buscaD = useDebounced(busca);
  const respD = useDebounced(responsavel);

  // Ao mudar o período global, os filtros locais de dias deixam de fazer sentido.
  useEffect(() => { setDias([]); setFIni(''); setFFim(''); setPage(1); }, [dataIni, dataFim]);

  const query: PreventivasQuery = useMemo(() => ({
    dataIni, dataFim, incluirAtrasadas, dias, fIni: fIni || undefined, fFim: fFim || undefined, status, atrasada,
    turno: turno || undefined, paridade: paridade || undefined, responsavel: respD, busca: buscaD, revisao, requerIntervencao,
    page, pageSize,
  }), [dataIni, dataFim, incluirAtrasadas, dias, fIni, fFim, status, atrasada, turno, paridade, respD, buscaD, revisao, requerIntervencao, page, pageSize]);

  const { data, loading, error, reload } = useAsync(
    (signal) => {
      const refresh = forcar.current;
      forcar.current = false;
      return client.fetchPreventivas({ ...query, refresh }, signal);
    },
    [client, JSON.stringify(query)],
  );

  useEffect(() => { if (data) onCount?.(data.totais_periodo.total); }, [data, onCount]);

  // volta para a página 1 sempre que um filtro (não a página) muda
  const semPagina = JSON.stringify({ ...query, page: 0 });
  const anterior = useRef(semPagina);
  useEffect(() => { if (anterior.current !== semPagina) { anterior.current = semPagina; setPage(1); } }, [semPagina]);

  const tp = data?.totais_periodo;
  const tf = data?.totais;
  const filtrando = !!(status.length || atrasada || revisao || requerIntervencao || turno || paridade || dias.length || fIni || fFim || buscaD || respD);

  // Filtros em vigor, sempre visíveis e removíveis um a um (nada fica "escondido" aplicado)
  const ativos: { chave: string; texto: string; remover: () => void }[] = [
    ...status.map((s) => ({ chave: `st-${s}`, texto: `Status: ${s}`, remover: () => alternarStatus(s) })),
    ...(atrasada ? [{ chave: 'atrasada', texto: 'Em atraso', remover: () => setAtrasada(false) }] : []),
    ...(revisao ? [{ chave: 'revisao', texto: 'Para revisar', remover: () => setRevisao(false) }] : []),
    ...(requerIntervencao ? [{ chave: 'sem', texto: 'Requer intervenção', remover: () => setRequerIntervencao(false) }] : []),
    ...(turno ? [{ chave: 'turno', texto: `Turno: ${turno === '—' ? 'não informado' : turno}`, remover: () => setTurno('') }] : []),
    ...(paridade ? [{ chave: 'par', texto: `Dia ${paridade}`, remover: () => setParidade('') }] : []),
    ...(dias.length ? [{ chave: 'dias', texto: `${dias.length} dia(s) escolhido(s)`, remover: () => setDias([]) }] : []),
    ...(fIni ? [{ chave: 'fini', texto: `A partir de ${fIni.split('-').reverse().join('/')}`, remover: () => setFIni('') }] : []),
    ...(fFim ? [{ chave: 'ffim', texto: `Até ${fFim.split('-').reverse().join('/')}`, remover: () => setFFim('') }] : []),
    ...(buscaD ? [{ chave: 'busca', texto: `Busca: “${buscaD}”`, remover: () => setBusca('') }] : []),
    ...(respD ? [{ chave: 'resp', texto: `Responsável: “${respD}”`, remover: () => setResponsavel('') }] : []),
  ];
  const filtrosExtrasAtivos = !!(paridade || fIni || fFim);

  const limpar = () => {
    setStatus([]); setAtrasada(false); setRevisao(false); setRequerIntervencao(false); setTurno(''); setParidade('');
    setDias([]); setFIni(''); setFFim(''); setBusca(''); setResponsavel('');
  };

  const focarKpi = (k: 'todos' | 'status' | 'atrasada' | 'revisao' | 'sem', st?: string) => {
    limpar();
    if (k === 'status' && st) setStatus([st]);
    if (k === 'atrasada') setAtrasada(true);
    if (k === 'revisao') setRevisao(true);
    if (k === 'sem') setRequerIntervencao(true);
  };

  const alternarStatus = (s: string) =>
    setStatus((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));

  const exportar = async () => {
    setExportando(true);
    try {
      const nome = await client.exportarPreventivas(query);
      toast.success(`Arquivo gerado: ${nome}`);
    } catch (e) {
      toast.error(mensagemDeErro(e, 'Não foi possível exportar.'));
    } finally {
      setExportando(false);
    }
  };

  const atualizar = () => { forcar.current = true; reload(); };

  const kpiAtivo = (k: string) => {
    if (!filtrando) return k === 'todos';
    if (k === 'atrasada') return atrasada && !status.length && !revisao && !requerIntervencao;
    if (k === 'revisao') return revisao && !status.length && !atrasada && !requerIntervencao;
    if (k === 'sem') return requerIntervencao && !status.length && !atrasada && !revisao;
    return status.length === 1 && status[0] === k;
  };

  return (
    <div className="stack">
      <PageHead
        title="Preventivas"
        subtitle={data ? <>Dados de {formatDateTimeBR(data.gerado_em)} · hoje é {data.periodo.hoje.split('-').reverse().join('/')}</> : 'Ordens e previsões do período selecionado'}
        actions={
          <>
            <Button icon="refresh" onClick={atualizar} loading={loading}>Atualizar</Button>
            <Button variant="success" icon="download" onClick={exportar} loading={exportando} disabled={!data || data.total === 0}>
              Exportar Excel
            </Button>
          </>
        }
      />

      {data && onIrParaRegras && data.pendencias_regras.length > 0 && (
        <Alert
          tone="warning"
          action={onIrParaRegras && <Button size="sm" onClick={onIrParaRegras}>Resolver regras</Button>}
        >
          <b>{data.pendencias_regras.length} nome(s) em regras de atribuição precisam de confirmação.</b>{' '}
          Enquanto isso, as ordens dessas regras ficam <i>sem candidato</i> em vez de receberem um executante escolhido ao acaso.
        </Alert>
      )}

      <section className="kpis" aria-label="Resumo do período">
        <KpiCard label="Total no período" value={tp?.total ?? null} tone="primary" loading={loading && !tp}
          onClick={() => focarKpi('todos')} pressed={kpiAtivo('todos')} />
        <KpiCard label="Concluídas" value={tp?.por_status['Concluída'] ?? null} tone="success" loading={loading && !tp}
          onClick={() => focarKpi('status', 'Concluída')} pressed={kpiAtivo('Concluída')} />
        <KpiCard label="Em andamento" value={tp?.por_status['Em andamento'] ?? null} tone="info" loading={loading && !tp}
          onClick={() => focarKpi('status', 'Em andamento')} pressed={kpiAtivo('Em andamento')} />
        <KpiCard label="Pendentes" value={tp?.por_status['Pendente'] ?? null} tone="warning" loading={loading && !tp}
          onClick={() => focarKpi('status', 'Pendente')} pressed={kpiAtivo('Pendente')} />
        <KpiCard label="Em atraso" value={tp?.atrasadas ?? null} tone="danger" hint="Aberta/em andamento com data anterior a hoje"
          loading={loading && !tp} onClick={() => focarKpi('atrasada')} pressed={kpiAtivo('atrasada')} />
        <KpiCard label="Para revisar" value={tp?.revisao ?? null} tone="warning" hint="Responsável não é um executante válido"
          loading={loading && !tp} onClick={() => focarKpi('revisao')} pressed={kpiAtivo('revisao')} />
        <KpiCard label="Requer intervenção" value={tp?.requer_intervencao ?? tp?.sem_candidato ?? null} tone="purple" hint="Sem candidato ou acima do limite diário"
          loading={loading && !tp} onClick={() => focarKpi('sem')} pressed={kpiAtivo('sem')} />
      </section>

      <section className="filters" aria-label="Filtros">
        <DayPicker dataIni={dataIni} dataFim={dataFim} hoje={data?.periodo.hoje ?? ''} selecionados={dias}
          onChange={setDias} contagem={tp?.por_dia} />

        <div className="row" role="group" aria-label="Filtrar por status">
          <span className="label">Status</span>
          {STATUS_EXECUCAO.map((s) => (
            <button key={s.status} type="button" className="filter-chip" aria-pressed={status.includes(s.status)}
              title={s.hint} onClick={() => alternarStatus(s.status)}>
              {s.status}
              {tp && <span className="muted" style={{ fontVariantNumeric: 'tabular-nums' }}>{tp.por_status[s.status] ?? 0}</span>}
            </button>
          ))}
          <button type="button" className="filter-chip" aria-pressed={atrasada} onClick={() => setAtrasada((v) => !v)}
            title="Somente ordens abertas/em andamento com data anterior a hoje">
            Em atraso
          </button>
        </div>

        <div className="row">
          <div className="search-wrap" style={{ minWidth: 220, flex: '1 1 220px' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" /></svg>
            <input className="input" placeholder="Buscar plano, equipamento, setor, OS…" aria-label="Busca livre" value={busca}
              onChange={(e) => setBusca(e.target.value)} />
          </div>
          <input className="input" style={{ maxWidth: 210 }} placeholder="Responsável…" aria-label="Filtrar por responsável"
            value={responsavel} onChange={(e) => setResponsavel(e.target.value)} />
          <select className="select" style={{ maxWidth: 150 }} aria-label="Filtrar por turno" value={turno} onChange={(e) => setTurno(e.target.value)}>
            {TURNOS.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
          </select>
          <Button size="sm" variant="ghost" aria-expanded={maisFiltros || filtrosExtrasAtivos} onClick={() => setMaisFiltros((v) => !v)}
            disabled={filtrosExtrasAtivos}>
            {maisFiltros || filtrosExtrasAtivos ? 'Menos filtros' : 'Mais filtros'}
          </Button>
        </div>

        {(maisFiltros || filtrosExtrasAtivos) && (
          <div className="row" aria-label="Mais filtros">
            <select className="select" style={{ maxWidth: 140 }} aria-label="Filtrar por tipo de dia" value={paridade} onChange={(e) => setParidade(e.target.value)}>
              <option value="">Dia: todos</option><option value="Par">Par</option><option value="Ímpar">Ímpar</option>
            </select>
            <label className="row" style={{ gap: 6 }}>
              <span className="muted">De</span>
              <input type="date" className="input" style={{ width: 150 }} aria-label="Filtrar a partir de" min={dataIni} max={dataFim}
                value={fIni} onChange={(e) => setFIni(e.target.value)} />
            </label>
            <label className="row" style={{ gap: 6 }}>
              <span className="muted">Até</span>
              <input type="date" className="input" style={{ width: 150 }} aria-label="Filtrar até" min={dataIni} max={dataFim}
                value={fFim} onChange={(e) => setFFim(e.target.value)} />
            </label>
          </div>
        )}

        {ativos.length > 0 && (
          <div className="chips-ativos" role="list" aria-label="Filtros ativos">
            {ativos.map((a) => (
              <span key={a.chave} role="listitem" className="chip-removivel">
                {a.texto}
                <button type="button" aria-label={`Remover filtro ${a.texto}`} onClick={a.remover}>×</button>
              </span>
            ))}
          </div>
        )}

        <div className="row" style={{ justifyContent: 'space-between' }}>
          <label className="check">
            <span className="switch"><input type="checkbox" checked={incluirAtrasadas} onChange={(e) => setIncluirAtrasadas(e.target.checked)} /><span /></span>
            Incluir ordens atrasadas de dias anteriores ao período
          </label>
          <span className="row">
            {filtrando && tf && tp && <span className="muted">Mostrando {tf.total.toLocaleString('pt-BR')} de {tp.total.toLocaleString('pt-BR')}</span>}
            <Button size="sm" variant="ghost" icon="x" onClick={limpar} disabled={!filtrando}>Limpar filtros</Button>
          </span>
        </div>
      </section>

      {error && <Alert tone="danger" action={<Button size="sm" onClick={reload}>Tentar de novo</Button>}>{error}</Alert>}

      {loading && !data ? (
        <TableSkeleton rows={8} cols={7} />
      ) : data && data.itens.length === 0 ? (
        <EmptyState icon="calendar" title="Nenhuma ocorrência encontrada"
          action={filtrando ? <Button onClick={limpar}>Limpar filtros</Button> : undefined}>
          {filtrando ? 'Nenhum registro atende aos filtros atuais.' : 'Não há ordens nem previsões neste período.'}
        </EmptyState>
      ) : data ? (
        <>
          <div className="table-wrap" aria-busy={loading}>
            <table className="table">
              <caption className="sr-only">Preventivas do período, {data.total} ocorrências</caption>
              <thead>
                <tr>
                  <th scope="col">Data</th>
                  <th scope="col">Plano</th>
                  <th scope="col" className="hide-md">Equipamento / Setor</th>
                  <th scope="col">Status</th>
                  <th scope="col">OS</th>
                  <th scope="col">Recomendado</th>
                </tr>
              </thead>
              <tbody>
                {data.itens.map((it) => <Linha key={it.id} it={it} onIrParaRegras={onIrParaRegras} />)}
              </tbody>
            </table>
          </div>
          <Pagination page={data.pagina} pageSize={data.por_pagina} total={data.total} onPage={setPage}
            onPageSize={(n) => { setPageSize(n); setPage(1); }} />
        </>
      ) : null}
    </div>
  );
}

function Linha({ it, onIrParaRegras }: { it: Preventiva; onIrParaRegras?: () => void }) {
  const classe = it.atrasada ? 'row-late' : it.sem_candidato ? 'row-nocand' : it.revisao ? 'row-review' : '';
  const nomes = it.recomendados.length ? it.recomendados : it.recomendado ? [it.recomendado] : [];
  return (
    <tr className={classe}>
      <td>
        <div className="strong">{it.data_prev}</div>
        <div className="cell-sub">{it.dia_par}{it.turno !== '—' ? ` · ${it.turno}` : ''}</div>
      </td>
      <td>
        <div className="strong cell-clip" title={it.plano}>{it.plano || '—'}</div>
        <div className="cell-sub">{it.oficina || it.tipo}{it.origem === 'Plano' ? ' · projeção do plano' : ''}</div>
      </td>
      <td className="hide-md">
        <div className="cell-clip" title={it.equipamento}>{it.equipamento}</div>
        <div className="cell-sub cell-clip" title={it.setor}>{it.setor}</div>
      </td>
      <td>
        <div className="row" style={{ gap: 4, flexWrap: 'nowrap' }}>
          <Chip tone={toneDoStatus(it.status)}>{it.status}</Chip>
          {it.atrasada && <Chip tone="danger" dot={false}>Atrasada</Chip>}
        </div>
        {it.situacao_neovero && <div className="cell-sub" title="Situação como descrita no Neovero">{it.situacao_neovero}</div>}
        {it.observacao_os && <div className="cell-sub cell-clip" title={it.observacao_os}>“{it.observacao_os}”</div>}
      </td>
      <td className="mono">{it.os_vinculada !== '—' ? it.os_vinculada : <span className="muted">—</span>}</td>
      <td>
        {nomes.length > 0 ? (
          <>
            <div className="strong">{nomes.join(' + ')}</div>
            <div className="cell-sub">{it.cargo}{it.escala ? ` · ${it.escala}` : ''}</div>
            {it.alertas.map((a) => <div key={a} className="cell-sub" style={{ color: 'var(--warning-text)' }}>{a}</div>)}
            {it.requer_intervencao && <Intervencao motivo={it.motivo_intervencao ?? null} />}
          </>
        ) : it.sem_candidato || it.requer_intervencao ? (
          <>
            <Intervencao motivo={it.motivo_intervencao ?? it.motivo_sem_candidato} />
            {it.regra?.status === 'pendente' && onIrParaRegras && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={onIrParaRegras}>Resolver</button>
            )}
          </>
        ) : <span className="muted" title="Não é preciso recomendar executante nesta linha">{it.sem_recomendacao_motivo ?? '—'}</span>}
        {it.cargo_fora_da_regra && <div className="cell-sub" style={{ color: 'var(--warning-text)' }}>{it.cargo_fora_da_regra}</div>}
      </td>
    </tr>
  );
}

/** "Requer intervenção": só o aviso; o motivo aparece quando o usuário clica (a OS continua escalada). */
function Intervencao({ motivo }: { motivo: string | null }) {
  const [aberto, setAberto] = useState(false);
  return (
    <div>
      <button type="button" className="chip-btn" aria-expanded={aberto} onClick={() => setAberto((v) => !v)}
        title="Clique para ver o motivo">
        <Chip tone="purple">Requer intervenção</Chip>
      </button>
      {aberto && (
        <div className="cell-sub" role="note" style={{ maxWidth: 340, whiteSpace: 'normal' }}>
          {motivo ?? 'Motivo não informado.'}
        </div>
      )}
    </div>
  );
}
