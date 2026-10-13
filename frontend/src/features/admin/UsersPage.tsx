import { useState } from 'react';
import type { FormEvent } from 'react';
import { adminApi } from '../../shared/api/adminClient';
import { mensagemDeErro } from '../../shared/api/http';
import type { AdminUser } from '../../shared/api/types';
import { useAsync } from '../../shared/hooks/useAsync';
import Modal, { ConfirmDialog } from '../../shared/ui/Modal';
import { useToast } from '../../shared/ui/Toast';
import { Alert, Button, Chip, EmptyState, PageHead, TableSkeleton } from '../../shared/ui/ui';
import { formatDateTimeBR } from '../../shared/utils/dateUtils';

export default function UsersPage() {
  const toast = useToast();
  const { data, loading, error, reload } = useAsync(() => adminApi.listUsers(), []);
  const [criando, setCriando] = useState(false);
  const [editando, setEditando] = useState<AdminUser | null>(null);
  const [senhaDe, setSenhaDe] = useState<AdminUser | null>(null);
  const [alternando, setAlternando] = useState<AdminUser | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const alternarAtivo = async () => {
    if (!alternando) return;
    setOcupado(true);
    try {
      await adminApi.setActive(alternando.id, !alternando.is_active);
      toast.success(alternando.is_active ? 'Usuário desativado. As sessões abertas foram encerradas.' : 'Usuário reativado.');
      setAlternando(null);
      reload();
    } catch (e) {
      toast.error(mensagemDeErro(e));
    } finally {
      setOcupado(false);
    }
  };

  return (
    <div className="stack">
      <PageHead
        title="Usuários e acessos"
        subtitle="Cada usuário comum enxerga e altera somente a unidade a que está vinculado. Desativar não apaga o histórico."
        actions={<Button variant="primary" icon="plus" onClick={() => setCriando(true)}>Novo usuário</Button>}
      />
      {error && <Alert tone="danger" action={<Button size="sm" onClick={reload}>Tentar de novo</Button>}>{error}</Alert>}
      {loading && !data ? <TableSkeleton rows={5} cols={6} /> : data && data.itens.length === 0 ? <EmptyState icon="users" title="Nenhum usuário" /> : data ? (
        <div className="table-wrap">
          <table className="table">
            <caption className="sr-only">Usuários cadastrados</caption>
            <thead><tr><th scope="col">Usuário</th><th scope="col">Perfil / unidade</th><th scope="col">Situação</th><th scope="col" className="hide-md">Último acesso</th><th scope="col" className="hide-md">Sessões abertas</th><th scope="col">Ações</th></tr></thead>
            <tbody>
              {data.itens.map((u) => (
                <tr key={u.id} style={{ opacity: u.is_active ? 1 : 0.7 }}>
                  <td><div className="strong">{u.display_name || u.username}</div><div className="cell-sub mono">{u.username}</div></td>
                  <td>{u.is_dev ? <Chip tone="primary">Dev · todas as unidades</Chip> : <Chip tone="neutral">{u.unit_name ?? u.unit}</Chip>}</td>
                  <td>
                    <div className="row" style={{ gap: 4 }}>
                      <Chip tone={u.is_active ? 'success' : 'danger'}>{u.is_active ? 'Ativo' : 'Desativado'}</Chip>
                      {u.locked_until && <Chip tone="warning" title="Bloqueado por tentativas inválidas">Bloqueio temporário</Chip>}
                      {u.must_change_password && <Chip tone="info" dot={false}>Trocar senha</Chip>}
                    </div>
                  </td>
                  <td className="hide-md">{formatDateTimeBR(u.last_login_at)}</td>
                  <td className="hide-md num">{u.sessoes_abertas}</td>
                  <td>
                    <div className="row" style={{ gap: 4 }}>
                      {!u.is_dev && <Button size="sm" icon="edit" onClick={() => setEditando(u)}>Editar</Button>}
                      <Button size="sm" icon="key" onClick={() => setSenhaDe(u)}>Senha</Button>
                      {!u.is_dev && (
                        <Button size="sm" variant={u.is_active ? 'danger' : 'primary'} onClick={() => setAlternando(u)}>
                          {u.is_active ? 'Desativar' : 'Reativar'}
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {criando && data && <FormUsuario unidades={data.unidades} onClose={() => setCriando(false)} onSaved={() => { setCriando(false); reload(); }} />}
      {editando && data && <FormUsuario unidades={data.unidades} usuario={editando} onClose={() => setEditando(null)} onSaved={() => { setEditando(null); reload(); }} />}
      {senhaDe && <FormSenha usuario={senhaDe} onClose={() => setSenhaDe(null)} />}
      {alternando && (
        <ConfirmDialog
          title={alternando.is_active ? `Desativar ${alternando.username}?` : `Reativar ${alternando.username}?`}
          danger={alternando.is_active} loading={ocupado}
          confirmLabel={alternando.is_active ? 'Desativar' : 'Reativar'}
          message={alternando.is_active
            ? 'A pessoa perde o acesso imediatamente (as sessões abertas são encerradas). O histórico de atividades é mantido.'
            : 'A pessoa poderá entrar novamente com a senha atual.'}
          onCancel={() => setAlternando(null)} onConfirm={alternarAtivo}
        />
      )}
    </div>
  );
}

function FormUsuario({ unidades, usuario, onClose, onSaved }: {
  unidades: { codigo: string; nome: string }[]; usuario?: AdminUser; onClose: () => void; onSaved: () => void;
}) {
  const toast = useToast();
  const [username, setUsername] = useState(usuario?.username ?? '');
  const [nome, setNome] = useState(usuario?.display_name ?? '');
  const [unit, setUnit] = useState<string>(usuario?.unit ?? unidades[0]?.codigo ?? '');
  const [senha, setSenha] = useState('');
  const [trocar, setTrocar] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      if (usuario) {
        await adminApi.updateUser(usuario.id, { display_name: nome, unit });
        toast.success(unit !== usuario.unit ? 'Usuário atualizado. As sessões abertas foram encerradas para aplicar o novo vínculo.' : 'Usuário atualizado.');
      } else {
        await adminApi.createUser({ username, password: senha, display_name: nome, unit, must_change_password: trocar });
        toast.success('Usuário criado.');
      }
      onSaved();
    } catch (err) {
      setErro(mensagemDeErro(err));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Modal title={usuario ? `Editar ${usuario.username}` : 'Novo usuário'} onClose={onClose}
      footer={<><Button onClick={onClose} disabled={enviando}>Cancelar</Button><Button variant="primary" type="submit" form="form-usuario" loading={enviando}>Salvar</Button></>}>
      <form id="form-usuario" className="stack" onSubmit={enviar}>
        {erro && <Alert tone="danger">{erro}</Alert>}
        {!usuario && (
          <div className="field">
            <label htmlFor="u-user">Usuário (login)</label>
            <input id="u-user" className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off"
              autoCapitalize="none" spellCheck={false} data-autofocus />
            <span className="muted" style={{ fontSize: 12 }}>Minúsculas, números, ponto, hífen ou sublinhado (3–64 caracteres).</span>
          </div>
        )}
        <div className="field">
          <label htmlFor="u-nome">Nome de exibição</label>
          <input id="u-nome" className="input" value={nome} onChange={(e) => setNome(e.target.value)} autoComplete="off" />
        </div>
        <div className="field">
          <label htmlFor="u-unit">Unidade vinculada</label>
          <select id="u-unit" className="select" value={unit} onChange={(e) => setUnit(e.target.value)}>
            {unidades.map((u) => <option key={u.codigo} value={u.codigo}>{u.nome}</option>)}
          </select>
          {usuario && unit !== usuario.unit && <span style={{ fontSize: 12, color: 'var(--warning-text)' }}>Mudar a unidade encerra as sessões abertas desta pessoa.</span>}
        </div>
        {!usuario && (
          <>
            <div className="field">
              <label htmlFor="u-senha">Senha inicial</label>
              <input id="u-senha" className="input" type="password" autoComplete="new-password" value={senha} onChange={(e) => setSenha(e.target.value)} />
              <span className="muted" style={{ fontSize: 12 }}>Mínimo de 10 caracteres, com letras e números. Nunca é exibida de novo.</span>
            </div>
            <label className="check"><input type="checkbox" checked={trocar} onChange={(e) => setTrocar(e.target.checked)} /> Exigir troca de senha no primeiro acesso</label>
          </>
        )}
      </form>
    </Modal>
  );
}

function FormSenha({ usuario, onClose }: { usuario: AdminUser; onClose: () => void }) {
  const toast = useToast();
  const [senha, setSenha] = useState('');
  const [trocar, setTrocar] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setErro(null);
    setEnviando(true);
    try {
      await adminApi.resetPassword(usuario.id, senha, trocar);
      toast.success('Senha redefinida. As sessões abertas dessa pessoa foram encerradas.');
      onClose();
    } catch (err) {
      setErro(mensagemDeErro(err));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Modal title={`Redefinir senha — ${usuario.username}`} onClose={onClose}
      footer={<><Button onClick={onClose} disabled={enviando}>Cancelar</Button><Button variant="primary" type="submit" form="form-reset" loading={enviando}>Redefinir</Button></>}>
      <form id="form-reset" className="stack" onSubmit={enviar}>
        {erro && <Alert tone="danger">{erro}</Alert>}
        <div className="field">
          <label htmlFor="r-senha">Nova senha</label>
          <input id="r-senha" className="input" type="password" autoComplete="new-password" value={senha} onChange={(e) => setSenha(e.target.value)} data-autofocus />
        </div>
        <label className="check"><input type="checkbox" checked={trocar} onChange={(e) => setTrocar(e.target.checked)} /> Exigir troca de senha no próximo acesso</label>
      </form>
    </Modal>
  );
}
