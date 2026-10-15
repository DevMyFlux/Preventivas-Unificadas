import { useState } from 'react';
import { adminApi } from '../../shared/api/adminClient';
import { mensagemDeErro } from '../../shared/api/http';
import type { EstadoAgora, SessionRow } from '../../shared/api/types';
import { useAsync } from '../../shared/hooks/useAsync';
import Modal from '../../shared/ui/Modal';
import { useToast } from '../../shared/ui/Toast';
import { Alert, Button, Chip, EmptyState, Skeleton } from '../../shared/ui/ui';
import { formatDateTimeBR } from '../../shared/utils/dateUtils';
import { NOME_MODULO } from '../../shared/utils/status';

export function formatarMinutos(min: number): string {
  if (min < 1) return '< 1 min';
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return h > 0 ? `${h} h ${m} min` : `${m} min`;
}

export const ESTADO_AGORA: Record<EstadoAgora, { texto: string; tone: 'success' | 'warning' | 'neutral' }> = {
  ativo: { texto: 'Ativo agora', tone: 'success' },
  ocioso: { texto: 'Conectado, ocioso', tone: 'warning' },
  offline: { texto: 'Sem sessão aberta', tone: 'neutral' },
};

export function tomDoEncerramento(s: SessionRow): 'success' | 'warning' | 'info' | 'neutral' | 'danger' {
  if (s.estado !== 'encerrada') return s.estado === 'ativo' ? 'success' : 'info';
  if (s.por_inatividade) return 'warning';
  if (s.encerramento === 'user_deactivated') return 'danger';
  return s.encerramento === 'logout' ? 'success' : 'neutral';
}

export function textoDaSessao(s: SessionRow): string {
  if (s.estado === 'ativo') return 'Ativa agora';
  if (s.estado === 'ocioso') return 'Aberta, ociosa';
  return s.motivo_texto;
}

/** Ficha do usuário (somente Dev): cadastro, utilização do período, sessões e últimos eventos. */
export default function UsuarioDetalhe({ userId, onClose, onChanged }: { userId: number; onClose: () => void; onChanged?: () => void }) {
  const toast = useToast();
  const { data, loading, error, reload } = useAsync(() => adminApi.userDetail(userId), [userId]);
  const [desbloqueando, setDesbloqueando] = useState(false);
  const u = data?.usuario;
  const uso = data?.utilizacao;

  const desbloquear = async () => {
    setDesbloqueando(true);
    try {
      await adminApi.unlockUser(userId);
      toast.success('Bloqueio temporário removido.');
      reload();
      onChanged?.();
    } catch (e) {
      toast.error(mensagemDeErro(e));
    } finally {
      setDesbloqueando(false);
    }
  };

  return (
    <Modal title={u ? (u.display_name || u.username) : 'Usuário'} subtitle={u?.username} wide onClose={onClose}
      footer={<Button onClick={onClose}>Fechar</Button>}>
      {error && <Alert tone="danger" action={<Button size="sm" onClick={reload}>Tentar de novo</Button>}>{error}</Alert>}
      {loading && !data && <div className="stack"><Skeleton height={18} /><Skeleton height={18} /><Skeleton height={80} /></div>}
      {u && (
        <div className="stack">
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
            {u.is_dev ? <Chip tone="primary">Administrador · todas as unidades</Chip> : <Chip tone="neutral">{u.unit_name ?? u.unit}</Chip>}
            <Chip tone={u.is_active ? 'success' : 'danger'}>{u.is_active ? 'Conta ativa' : 'Conta desativada'}</Chip>
            {uso && <Chip tone={ESTADO_AGORA[uso.estado_agora].tone}>{ESTADO_AGORA[uso.estado_agora].texto}</Chip>}
            {u.must_change_password && <Chip tone="info" dot={false}>Trocar senha</Chip>}
            {u.locked_until && <Chip tone="warning">Bloqueio temporário até {formatDateTimeBR(u.locked_until)}</Chip>}
          </div>
          {u.locked_until && (
            <div><Button size="sm" icon="lock" onClick={desbloquear} loading={desbloqueando}>Remover bloqueio temporário</Button></div>
          )}

          <dl className="kv">
            {([
              ['Criado em', formatDateTimeBR(u.created_at)], ['Criado por', u.created_by ?? '—'],
              ['Último login', formatDateTimeBR(u.last_login_at)], ['Sessões abertas', String(u.sessoes_abertas)],
              ['Desativado em', u.deactivated_at ? formatDateTimeBR(u.deactivated_at) : '—'],
            ] as [string, string][]).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
          </dl>

          {uso && (
            <section className="stack" aria-label="Utilização no período">
              <div className="card-title">Utilização (todo o histórico coletado)</div>
              <dl className="kv">
                {([
                  ['Acessos (sessões)', String(uso.acessos)], ['Tempo em sessão', formatarMinutos(uso.tempo_sessao_min)],
                  ['Tempo ativo (estimado)', formatarMinutos(uso.tempo_ativo_min)], ['Tempo ocioso', formatarMinutos(uso.tempo_ocioso_min)],
                  ['Encerradas por inatividade', String(uso.sessoes_por_inatividade)], ['Dias com registro', String(uso.dias_com_registro)],
                ] as [string, string][]).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
              </dl>
              {!uso.utilizou && <Alert tone="info">{uso.parecer}</Alert>}
            </section>
          )}

          <section className="stack" aria-label="Sessões recentes">
            <div className="card-title">Sessões recentes</div>
            {data.sessoes.length === 0 ? <EmptyState title="Nenhuma sessão no período" /> : (
              <div className="table-wrap">
                <table className="table">
                  <caption className="sr-only">Sessões do usuário</caption>
                  <thead><tr><th scope="col">Início</th><th scope="col">Fim</th><th scope="col" className="num">Duração</th><th scope="col" className="num">Ativo</th><th scope="col">Encerramento</th></tr></thead>
                  <tbody>
                    {data.sessoes.map((s) => (
                      <tr key={s.id}>
                        <td>{formatDateTimeBR(s.inicio)}</td><td>{s.fim ? formatDateTimeBR(s.fim) : '—'}</td>
                        <td className="num">{formatarMinutos(s.duracao_min)}</td><td className="num">{formatarMinutos(s.tempo_ativo_min)}</td>
                        <td><Chip tone={tomDoEncerramento(s)}>{textoDaSessao(s)}</Chip></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="stack" aria-label="Últimas atividades">
            <div className="card-title">Últimas atividades <span className="muted">({data.total_eventos} no período)</span></div>
            {data.eventos.length === 0 ? <EmptyState title="Sem atividades registradas no período" /> : (
              <div className="table-wrap">
                <table className="table">
                  <caption className="sr-only">Eventos do usuário</caption>
                  <thead><tr><th scope="col">Data/hora</th><th scope="col">Módulo</th><th scope="col">Evento</th><th scope="col">Resultado</th></tr></thead>
                  <tbody>
                    {data.eventos.map((e) => (
                      <tr key={e.id}>
                        <td className="mono">{formatDateTimeBR(e.ts)}</td><td>{NOME_MODULO[e.module ?? ''] ?? e.module ?? '—'}</td>
                        <td className="mono">{e.event}</td>
                        <td><Chip tone={e.result === 'success' ? 'success' : e.result === 'denied' ? 'warning' : 'danger'}>{e.result === 'success' ? 'Sucesso' : e.result === 'denied' ? 'Negado' : 'Falha'}</Chip></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </Modal>
  );
}
