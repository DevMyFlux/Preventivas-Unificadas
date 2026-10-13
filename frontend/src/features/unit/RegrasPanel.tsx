import { useState } from 'react';
import { mensagemDeErro } from '../../shared/api/http';
import type { UnitApiClient } from '../../shared/api/client';
import type { RegraResponsavel } from '../../shared/api/types';
import { useAsync } from '../../shared/hooks/useAsync';
import { useToast } from '../../shared/ui/Toast';
import { Alert, Button, Chip, EmptyState, PageHead, Spinner } from '../../shared/ui/ui';

export default function RegrasPanel({ client, onChanged }: { client: UnitApiClient; onChanged?: () => void }) {
  const toast = useToast();
  const { data, loading, error, reload } = useAsync(() => client.fetchRegras(), [client]);
  const [escolhas, setEscolhas] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState<string | null>(null);

  const confirmar = async (alias: string) => {
    const funcionario = escolhas[alias];
    if (!funcionario) return;
    setSalvando(alias);
    try {
      await client.confirmarRegra(alias, funcionario);
      toast.success(`“${alias}” confirmado como ${funcionario}.`);
      reload();
      onChanged?.();
    } catch (e) {
      toast.error(mensagemDeErro(e));
    } finally {
      setSalvando(null);
    }
  };

  const remover = async (alias: string) => {
    setSalvando(alias);
    try {
      await client.removerConfirmacaoRegra(alias);
      toast.info(`Confirmação de “${alias}” removida.`);
      reload();
      onChanged?.();
    } catch (e) {
      toast.error(mensagemDeErro(e));
    } finally {
      setSalvando(null);
    }
  };

  return (
    <div className="stack">
      <PageHead
        title="Regras de atribuição"
        subtitle="Responsáveis fixos por turno e tipo de dia (par/ímpar do dia de execução). Os nomes são validados contra o quadro ativo da unidade."
        actions={<Button icon="refresh" onClick={reload} loading={loading}>Atualizar</Button>}
      />

      {error && <Alert tone="danger" action={<Button size="sm" onClick={reload}>Tentar de novo</Button>}>{error}</Alert>}
      {loading && !data && <Spinner label="Carregando regras…" />}

      {data && data.regras.length === 0 && (
        <EmptyState icon="sliders" title="Esta unidade não tem regras nominais">
          A distribuição usa apenas cargo, escala, turno, complexidade e limites diários.
        </EmptyState>
      )}

      {data?.regras.map((regra) => (
        <section key={regra.id} className="card stack" aria-labelledby={`r-${regra.id}`}>
          <div>
            <h3 className="card-title" id={`r-${regra.id}`}>{regra.titulo}</h3>
            <div className="page-sub">{regra.descricao}</div>
          </div>
          <div className="table-wrap" style={{ maxHeight: 'none' }}>
            <table className="table">
              <caption className="sr-only">{regra.titulo}</caption>
              <thead><tr><th scope="col">Turno</th><th scope="col">Dia</th><th scope="col">Responsável(is)</th><th scope="col">Situação</th></tr></thead>
              <tbody>
                {regra.linhas.map((l) => (
                  <tr key={`${l.turno}-${l.paridade}`}>
                    <td className="strong">{l.turno}</td>
                    <td>{l.paridade}</td>
                    <td>
                      <div className="stack" style={{ gap: 8 }}>
                        {l.responsaveis.map((r) => (
                          <ResponsavelCelula key={r.alias} r={r} quadro={data.quadro_ativo} escolha={escolhas[r.alias] ?? ''}
                            onEscolher={(v) => setEscolhas((c) => ({ ...c, [r.alias]: v }))}
                            salvando={salvando === r.alias} onConfirmar={() => confirmar(r.alias)} onRemover={() => remover(r.alias)} />
                        ))}
                        {l.alertas.map((a) => <div key={a} className="cell-sub" style={{ color: 'var(--warning-text)' }}>⚠ {a}</div>)}
                      </div>
                    </td>
                    <td>{l.status === 'ok' ? <Chip tone="success">Em vigor</Chip> : <Chip tone="warning">Aguardando confirmação</Chip>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            Combinações de turno e dia não listadas acima <b>não têm regra</b>: o comportamento anterior é mantido.
          </div>
        </section>
      ))}
    </div>
  );
}

function ResponsavelCelula({ r, quadro, escolha, onEscolher, salvando, onConfirmar, onRemover }: {
  r: RegraResponsavel; quadro: string[]; escolha: string; onEscolher: (v: string) => void;
  salvando: boolean; onConfirmar: () => void; onRemover: () => void;
}) {
  if (r.status === 'ok') {
    return (
      <div className="row">
        <span className="chip c-primary nodot">“{r.alias}”</span>→<b>{r.escolhido}</b>
        <span className="muted">{r.origem === 'confirmado' ? 'confirmado manualmente' : 'único no quadro'}</span>
        {r.origem === 'confirmado' && <Button size="sm" variant="ghost" onClick={onRemover} loading={salvando}>Remover confirmação</Button>}
      </div>
    );
  }
  const opcoes = r.candidatos.length ? [...r.candidatos, ...quadro.filter((q) => !r.candidatos.includes(q))] : quadro;
  return (
    <div className="stack" style={{ gap: 6 }}>
      <div className="row">
        <span className="chip c-warning nodot">“{r.alias}”</span>
        <span style={{ color: 'var(--warning-text)' }}>{r.motivo}</span>
      </div>
      <div className="row">
        <select className="select" style={{ maxWidth: 320 }} aria-label={`Quem é “${r.alias}”?`} value={escolha} onChange={(e) => onEscolher(e.target.value)}>
          <option value="">Selecione quem é “{r.alias}”…</option>
          {opcoes.map((n) => <option key={n} value={n}>{r.candidatos.includes(n) ? `★ ${n}` : n}</option>)}
        </select>
        <Button variant="primary" size="sm" disabled={!escolha} loading={salvando} onClick={onConfirmar}>Confirmar</Button>
      </div>
    </div>
  );
}
