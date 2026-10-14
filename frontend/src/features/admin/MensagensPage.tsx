import { useState } from 'react';
import { adminApi } from '../../shared/api/adminClient';
import { mensagemDeErro } from '../../shared/api/http';
import type { MensagemSuporte, SituacaoMensagem } from '../../shared/api/types';
import { useAsync } from '../../shared/hooks/useAsync';
import { useToast } from '../../shared/ui/Toast';
import { Alert, Button, Chip, EmptyState, PageHead, Pagination, Segmented, TableSkeleton } from '../../shared/ui/ui';
import { formatDateTimeBR } from '../../shared/utils/dateUtils';

const TIPO: Record<string, string> = { sugestao: 'Sugestão', problema: 'Problema', melhoria: 'Melhoria' };
const SITUACAO: Record<SituacaoMensagem, { texto: string; tone: 'warning' | 'info' | 'success' }> = {
  nova: { texto: 'Nova', tone: 'warning' },
  lida: { texto: 'Lida', tone: 'info' },
  resolvida: { texto: 'Resolvida', tone: 'success' },
};

type Filtro = '' | SituacaoMensagem;

/** Caixa de mensagens do suporte: somente Dev (o backend recusa os demais com 403). */
export default function MensagensPage({ onChanged }: { onChanged?: (naoLidas: number) => void }) {
  const toast = useToast();
  const [situacao, setSituacao] = useState<Filtro>('');
  const [tipo, setTipo] = useState('');
  const [unit, setUnit] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [aberta, setAberta] = useState<number | null>(null);
  const [salvando, setSalvando] = useState<number | null>(null);

  const { data, loading, error, reload } = useAsync(
    () => adminApi.messages({ situacao: situacao || undefined, tipo: tipo || undefined, unit: unit || undefined, page, pageSize }),
    [situacao, tipo, unit, page, pageSize]);
  const itens = data?.itens ?? [];

  const marcar = async (m: MensagemSuporte, nova: SituacaoMensagem) => {
    setSalvando(m.id);
    try {
      await adminApi.setMessageStatus(m.id, nova);
      reload();
      adminApi.messagesCount().then((r) => onChanged?.(r.nao_lidas)).catch(() => {});
    } catch (e) {
      toast.error(mensagemDeErro(e));
    } finally {
      setSalvando(null);
    }
  };

  // abrir uma mensagem nova já a marca como lida (o Dev pode voltar para "nova" se quiser)
  const alternar = (m: MensagemSuporte) => {
    const abrindo = aberta !== m.id;
    setAberta(abrindo ? m.id : null);
    if (abrindo && m.situacao === 'nova') void marcar(m, 'lida');
  };

  const mudar = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1); };

  return (
    <div className="stack">
      <PageHead
        title="Caixa de mensagens"
        subtitle="Sugestões, problemas e melhorias enviados pelos usuários. Só administradores veem esta página."
        actions={<Button icon="refresh" onClick={reload} loading={loading}>Atualizar</Button>}
      />

      <section className="card row" aria-label="Filtros">
        <Segmented<Filtro> label="Situação" value={situacao} onChange={mudar(setSituacao)} options={[
          { key: '', label: data ? `Todas (${data.nao_lidas} novas)` : 'Todas' }, { key: 'nova', label: 'Novas' },
          { key: 'lida', label: 'Lidas' }, { key: 'resolvida', label: 'Resolvidas' }]} />
        <div className="field"><label htmlFor="m-tipo">Tipo</label>
          <select id="m-tipo" className="select" value={tipo} onChange={(e) => mudar(setTipo)(e.target.value)}>
            <option value="">Todos</option><option value="sugestao">Sugestão</option><option value="problema">Problema</option><option value="melhoria">Melhoria</option>
          </select></div>
        <div className="field"><label htmlFor="m-unit">Unidade</label>
          <select id="m-unit" className="select" value={unit} onChange={(e) => mudar(setUnit)(e.target.value)}>
            <option value="">Todas</option><option value="HETRIN">Hetrin</option><option value="HMB">HMB</option>
          </select></div>
      </section>

      {error && <Alert tone="danger" action={<Button size="sm" onClick={reload}>Tentar de novo</Button>}>{error}</Alert>}

      {loading && !data ? <TableSkeleton rows={5} cols={5} /> : data && itens.length === 0 ? (
        <EmptyState icon="inbox" title="Nenhuma mensagem">Quando alguém usar “Sugestões e Suporte”, a mensagem aparece aqui.</EmptyState>
      ) : data ? (
        <>
          <div className="stack" role="list" aria-label="Mensagens">
            {itens.map((m) => (
              <article key={m.id} role="listitem" className="card stack" style={{ gap: 8 }}>
                <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <button type="button" className="link-btn" style={{ textAlign: 'left', textDecoration: 'none', color: 'inherit' }}
                    aria-expanded={aberta === m.id} onClick={() => alternar(m)}>
                    <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                      <Chip tone={SITUACAO[m.situacao].tone}>{SITUACAO[m.situacao].texto}</Chip>
                      <Chip tone="neutral" dot={false}>{TIPO[m.tipo] ?? m.tipo}</Chip>
                      {m.unit && <Chip tone="primary" dot={false}>{m.unit}</Chip>}
                      <span className="strong">{m.nome}</span>
                      <span className="muted">· {m.username} · {formatDateTimeBR(m.ts)}</span>
                    </div>
                    {aberta !== m.id && <div className="cell-sub cell-clip" style={{ maxWidth: 640, marginTop: 4 }}>{m.mensagem}</div>}
                  </button>
                </div>
                {aberta === m.id && (
                  <>
                    <p style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', margin: 0 }}>{m.mensagem}</p>
                    <div className="muted" style={{ fontSize: 12.5 }}>
                      Retorno: <a href={`mailto:${m.email}`}>{m.email}</a>
                      {m.tratada_por && <> · {SITUACAO[m.situacao].texto.toLowerCase()} por {m.tratada_por} em {formatDateTimeBR(m.tratada_em)}</>}
                    </div>
                    <div className="row">
                      {m.situacao !== 'resolvida' && <Button size="sm" variant="primary" icon="check" loading={salvando === m.id} onClick={() => marcar(m, 'resolvida')}>Marcar como resolvida</Button>}
                      {m.situacao !== 'nova' && <Button size="sm" disabled={salvando === m.id} onClick={() => marcar(m, 'nova')}>Marcar como nova</Button>}
                    </div>
                  </>
                )}
              </article>
            ))}
          </div>
          <Pagination page={data.pagina} pageSize={data.por_pagina} total={data.total} onPage={setPage}
            onPageSize={(n) => { setPageSize(n); setPage(1); }} />
        </>
      ) : null}
    </div>
  );
}
