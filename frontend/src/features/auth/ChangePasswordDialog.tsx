import { useState } from 'react';
import type { FormEvent } from 'react';
import { useAuth } from '../../app/AuthContext';
import { authApi } from '../../shared/api/client';
import { mensagemDeErro } from '../../shared/api/http';
import Modal from '../../shared/ui/Modal';
import { Alert, Button } from '../../shared/ui/ui';

/** Troca da própria senha. `obrigatoria`: o administrador exigiu a troca — não dá para fechar sem trocar. */
export default function ChangePasswordDialog({ obrigatoria, onClose }: { obrigatoria?: boolean; onClose: () => void }) {
  const { reset } = useAuth();
  const [atual, setAtual] = useState('');
  const [nova, setNova] = useState('');
  const [confirma, setConfirma] = useState('');
  const [erro, setErro] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const [enviando, setEnviando] = useState(false);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (nova !== confirma) { setErro('A confirmação não confere com a nova senha.'); return; }
    setErro(null);
    setEnviando(true);
    try {
      await authApi.changePassword(atual, nova);
      setOk(true);   // o servidor encerra todas as sessões: é preciso entrar de novo
      window.setTimeout(reset, 1800);
    } catch (err) {
      setErro(mensagemDeErro(err));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Modal
      title={obrigatoria ? 'Defina uma nova senha' : 'Alterar senha'}
      onClose={() => { if (!obrigatoria && !ok) onClose(); }}
      subtitle={obrigatoria ? 'O administrador exigiu a troca da senha neste acesso.' : undefined}
      footer={ok ? null : (
        <>
          {!obrigatoria && <Button variant="secondary" onClick={onClose} disabled={enviando}>Cancelar</Button>}
          <Button variant="primary" type="submit" form="form-senha" loading={enviando}>Salvar nova senha</Button>
        </>
      )}
    >
      {ok ? (
        <Alert tone="success">Senha alterada. Por segurança, você será redirecionado para entrar novamente.</Alert>
      ) : (
        <form id="form-senha" onSubmit={enviar} className="stack">
          {erro && <Alert tone="danger">{erro}</Alert>}
          <div className="field">
            <label htmlFor="pw-atual">Senha atual</label>
            <input id="pw-atual" className="input" type="password" autoComplete="current-password" value={atual}
              onChange={(e) => setAtual(e.target.value)} data-autofocus />
          </div>
          <div className="field">
            <label htmlFor="pw-nova">Nova senha</label>
            <input id="pw-nova" className="input" type="password" autoComplete="new-password" value={nova}
              onChange={(e) => setNova(e.target.value)} />
            <span className="muted" style={{ fontSize: 12 }}>Mínimo de 10 caracteres, com letras e números.</span>
          </div>
          <div className="field">
            <label htmlFor="pw-conf">Confirmar nova senha</label>
            <input id="pw-conf" className="input" type="password" autoComplete="new-password" value={confirma}
              onChange={(e) => setConfirma(e.target.value)} />
          </div>
        </form>
      )}
    </Modal>
  );
}
