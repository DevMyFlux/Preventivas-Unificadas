import { useState } from 'react';
import type { FormEvent } from 'react';
import { useAuth } from '../../app/AuthContext';
import { mensagemDeErro } from '../../shared/api/http';
import Icon from '../../shared/ui/Icon';
import { Alert, Button } from '../../shared/ui/ui';

export default function LoginPage() {
  const { login, expired } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setErro('Informe usuário e senha.');
      return;
    }
    setErro(null);
    setEnviando(true);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setErro(mensagemDeErro(err, 'Não foi possível entrar.'));
      setPassword('');
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="login-wrap">
      <aside className="login-hero" aria-hidden="true">
        <div className="grid-bg" />
        <div className="brand" style={{ position: 'relative' }}>
          <div className="brand-mark"><Icon name="wrench" size={19} /></div>
          <div>
            <div className="brand-name">MyFlux Preventivas</div>
            <div className="brand-sub" style={{ color: '#cbd5e1' }}>Manutenção hospitalar</div>
          </div>
        </div>
        <div style={{ position: 'relative' }}>
          <h2>Cada ordem de serviço, no executante certo.</h2>
          <p>Acompanhe preventivas por dia, identifique o que está pendente ou em atraso e distribua o trabalho respeitando escalas, desligamentos e limites diários.</p>
        </div>
        <div style={{ position: 'relative', fontSize: 12, opacity: 0.6 }}>Acesso restrito à unidade autorizada.</div>
      </aside>

      <main className="login-pane" id="conteudo">
        <form className="login-card" onSubmit={enviar} noValidate>
          <div>
            <h1>Entrar</h1>
            <div className="page-sub">Use as credenciais fornecidas pelo administrador.</div>
          </div>

          {expired && !erro && <Alert tone="warning">Sua sessão expirou. Entre novamente para continuar.</Alert>}
          {erro && <Alert tone="danger">{erro}</Alert>}

          <div className="field">
            <label htmlFor="login-user">Usuário</label>
            <input
              id="login-user" className="input" autoComplete="username" autoCapitalize="none" spellCheck={false}
              value={username} onChange={(e) => setUsername(e.target.value)} aria-invalid={!!erro} autoFocus
            />
          </div>
          <div className="field">
            <label htmlFor="login-pass">Senha</label>
            <input
              id="login-pass" className="input" type="password" autoComplete="current-password"
              value={password} onChange={(e) => setPassword(e.target.value)} aria-invalid={!!erro}
            />
          </div>
          <Button variant="primary" type="submit" loading={enviando} icon="lock">Entrar</Button>
          <div className="muted" style={{ fontSize: 12 }}>
            Esqueceu a senha? Peça ao administrador para redefini-la. Tentativas repetidas inválidas bloqueiam a conta temporariamente.
          </div>
        </form>
      </main>
    </div>
  );
}
