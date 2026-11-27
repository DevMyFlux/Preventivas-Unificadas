import { useEffect, useMemo, useState } from 'react';
import { mensagemDeErro } from '../../shared/api/http';
import type { UnitApiClient } from '../../shared/api/client';
import type { Plano } from '../../shared/api/types';
import { useAsync } from '../../shared/hooks/useAsync';
import { useToast } from '../../shared/ui/Toast';
import { Alert, Button, Chip, EmptyState, PageHead, TableSkeleton } from '../../shared/ui/ui';

type FiltroAtivo = '' | 'sim' | 'nao';

export function filtrarPlanos(items: Plano[], busca: string, ativo: FiltroAtivo): Plano[] {
  const termo = busca.trim().toLowerCase();
  return items.filter((p) => {
    if (ativo === 'sim' && !p.ativo) return false;
    if (ativo === 'nao' && p.ativo) return false;
    if (!termo) return true;
    return [p.descricao, p.tipo, p.periodicidade, p.oficina, p.procedimento].join(' ').toLowerCase().includes(termo);
  });
}

export default function PlanosPanel({ client, onCount }: { client: UnitApiClient; onCount?: (n: number) => void }) {
  const toast = useToast();
  const [busca, setBusca] = useState('');
  const [ativo, setAtivo] = useState<FiltroAtivo>('');
  const [exportando, setExportando] = useState(false);
  const { data, loading, error, reload } = useAsync(() => client.fetchPlanos(), [client]);

  useEffect(() => { if (data) onCount?.(data.total); }, [data, onCount]);
  const filtrados = useMemo(() => (data ? filtrarPlanos(data.itens, busca, ativo) : []), [data, busca, ativo]);

  const exportar = async () => {
    setExportando(true);
    try {
      toast.success(`Arquivo gerado: ${await client.exportarPlanos(filtrados)}`);
    } catch (e) {
      toast.error(mensagemDeErro(e, 'Não foi possível exportar.'));
    } finally {
      setExportando(false);
    }
  };

  return (
    <div className="stack">
      <PageHead
        title="Planos de manutenção"
        subtitle="Cadastro de planos do Neovero (ativos e inativos)"
        actions={
          <>
            <Button icon="refresh" onClick={reload} loading={loading}>Atualizar</Button>
            <Button variant="success" icon="download" onClick={exportar} loading={exportando} disabled={filtrados.length === 0}>
              Exportar Excel
            </Button>
          </>
        }
      />
      <div className="row">
        <div className="search-wrap" style={{ flex: '1 1 260px', maxWidth: 420 }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="8" /><path d="m21 21-4.35-4.35" /></svg>
          <input className="input" placeholder="Buscar plano, tipo, oficina…" aria-label="Busca livre" value={busca} onChange={(e) => setBusca(e.target.value)} />
        </div>
        <select className="select" style={{ maxWidth: 170 }} aria-label="Filtrar por situação" value={ativo} onChange={(e) => setAtivo(e.target.value as FiltroAtivo)}>
          <option value="">Situação: todos</option><option value="sim">Ativos</option><option value="nao">Inativos</option>
        </select>
        {data && <span className="muted">{filtrados.length} de {data.total}</span>}
      </div>

      {error && <Alert tone="danger" action={<Button size="sm" onClick={reload}>Tentar de novo</Button>}>{error}</Alert>}
      {loading && !data ? <TableSkeleton rows={8} cols={6} /> : data && filtrados.length === 0 ? (
        <EmptyState title="Nenhum plano encontrado">Ajuste a busca ou os filtros.</EmptyState>
      ) : data ? (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Planos de manutenção</caption>
            <thead>
              <tr><th scope="col">ID</th><th scope="col">Descrição</th><th scope="col">Periodicidade</th><th scope="col" className="hide-md">Oficina</th><th scope="col" className="hide-md">Procedimento</th><th scope="col">Situação</th></tr>
            </thead>
            <tbody>
              {filtrados.map((p) => (
                <tr key={p.id}>
                  <td className="mono">{p.id}</td>
                  <td><div className="strong cell-clip" title={p.descricao}>{p.descricao}</div></td>
                  <td>{p.periodicidade || '—'}</td>
                  <td className="hide-md">{p.oficina || '—'}</td>
                  <td className="hide-md"><div className="cell-clip" title={p.procedimento}>{p.procedimento || '—'}</div></td>
                  <td><Chip tone={p.ativo ? 'success' : 'neutral'}>{p.ativo ? 'Ativo' : 'Inativo'}</Chip></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
