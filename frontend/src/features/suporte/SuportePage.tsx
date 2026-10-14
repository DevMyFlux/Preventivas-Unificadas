import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { useAuth } from '../../app/AuthContext';
import { suporteApi } from '../../shared/api/client';
import { ApiError, mensagemDeErro } from '../../shared/api/http';
import type { TipoSuporte } from '../../shared/api/types';
import { useAsync } from '../../shared/hooks/useAsync';
import { Alert, Button, PageHead } from '../../shared/ui/ui';

const TIPOS: { key: TipoSuporte; label: string; hint: string }[] = [
  { key: 'sugestao', label: 'Sugestão', hint: 'Uma ideia para o sistema' },
  { key: 'problema', label: 'Problema', hint: 'Algo não funciona como deveria' },
  { key: 'melhoria', label: 'Melhoria', hint: 'Algo que já existe e pode ficar melhor' },
];

const MIN = 10;
const MAX = 5000;
const RE_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export interface ErrosSuporte { nome?: string; email?: string; mensagem?: string }

export function validarSuporte(v: { nome: string; email: string; mensagem: string }): ErrosSuporte {
  const e: ErrosSuporte = {};
  const nome = v.nome.trim();
  if (nome.length < 2) e.nome = 'Informe seu nome.';
  else if (nome.length > 120) e.nome = 'O nome pode ter no máximo 120 caracteres.';
  if (!RE_EMAIL.test(v.email.trim()) || v.email.trim().length > 254) e.email = 'Informe um e-mail de retorno válido.';
  const msg = v.mensagem.trim();
  if (msg.length < MIN) e.mensagem = `Descreva com pelo menos ${MIN} caracteres.`;
  else if (msg.length > MAX) e.mensagem = `A mensagem pode ter no máximo ${MAX} caracteres.`;
  return e;
}

export default function SuportePage() {
  const { user } = useAuth();
  const status = useAsync(() => suporteApi.status(), []);
  const [nome, setNome] = useState(user?.display_name ?? '');
  const [email, setEmail] = useState(user?.username.includes('@') ? user.username : '');
  const [tipo, setTipo] = useState<TipoSuporte>('sugestao');
  const [mensagem, setMensagem] = useState('');
  const [erros, setErros] = useState<ErrosSuporte>({});
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState<{ tom: 'success' | 'danger' | 'warning'; texto: string } | null>(null);
  const trava = useRef(false);   // impede segundo envio antes de o primeiro responder (duplo clique)

  const naoConfigurado = status.data?.configurado === false;   // só no modo e-mail sem SMTP; a caixa interna sempre está pronta
  const porCaixa = status.data?.entrega !== 'email';

  const enviar = async (ev: FormEvent) => {
    ev.preventDefault();
    if (trava.current) return;
    const e = validarSuporte({ nome, email, mensagem });
    setErros(e);
    setResultado(null);
    if (Object.keys(e).length > 0) return;
    trava.current = true;
    setEnviando(true);
    try {
      const r = await suporteApi.enviar({ nome: nome.trim(), email: email.trim(), tipo, mensagem: mensagem.trim() });
      setResultado({ tom: 'success', texto: r.mensagem });
      setMensagem('');
    } catch (err) {
      if (err instanceof ApiError && err.codigo === 'validacao' && err.campo) {
        setErros({ [err.campo]: err.message });
      } else if (err instanceof ApiError && err.codigo === 'suporte_nao_configurado') {
        setResultado({ tom: 'warning', texto: err.message });
        status.reload();
      } else {
        setResultado({ tom: 'danger', texto: mensagemDeErro(err, 'Não foi possível enviar agora.') });
      }
    } finally {
      trava.current = false;
      setEnviando(false);
    }
  };

  return (
    <div className="stack" style={{ maxWidth: 720 }}>
      <PageHead title="Sugestões e Suporte" subtitle={porCaixa ? 'Conte o que podemos melhorar ou o que não está funcionando. A mensagem fica registrada na plataforma e a administração vai ler.' : 'Conte o que podemos melhorar ou o que não está funcionando. A equipe responde no e-mail informado.'} />

      {naoConfigurado && (
        <Alert tone="warning">
          O envio de e-mail do suporte ainda não está configurado neste ambiente — sua mensagem <b>não poderá ser enviada</b> por aqui.
          Avise o administrador.
        </Alert>
      )}
      {resultado && <Alert tone={resultado.tom} role={resultado.tom === 'success' ? 'status' : 'alert'}>{resultado.texto}</Alert>}

      <form className="card stack" onSubmit={enviar} noValidate aria-label="Enviar mensagem ao suporte">
        <div className="grid-2">
          <div className="field">
            <label htmlFor="s-nome">Nome</label>
            <input id="s-nome" className="input" value={nome} maxLength={120} autoComplete="name" aria-invalid={!!erros.nome}
              aria-describedby={erros.nome ? 's-nome-erro' : undefined} onChange={(e) => setNome(e.target.value)} />
            {erros.nome && <span id="s-nome-erro" className="field-error" role="alert">{erros.nome}</span>}
          </div>
          <div className="field">
            <label htmlFor="s-email">E-mail de retorno</label>
            <input id="s-email" className="input" type="email" value={email} maxLength={254} autoComplete="email" aria-invalid={!!erros.email}
              aria-describedby={erros.email ? 's-email-erro' : undefined} onChange={(e) => setEmail(e.target.value)} />
            {erros.email && <span id="s-email-erro" className="field-error" role="alert">{erros.email}</span>}
          </div>
        </div>

        <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="label">Tipo</legend>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            {TIPOS.map((t) => (
              <label key={t.key} className="check" title={t.hint}>
                <input type="radio" name="tipo" value={t.key} checked={tipo === t.key} onChange={() => setTipo(t.key)} /> {t.label}
              </label>
            ))}
          </div>
        </fieldset>

        <div className="field">
          <label htmlFor="s-msg">Mensagem</label>
          <textarea id="s-msg" className="input" rows={7} value={mensagem} maxLength={MAX + 200} aria-invalid={!!erros.mensagem}
            aria-describedby="s-msg-ajuda" placeholder="Descreva com o máximo de detalhe: onde estava, o que esperava e o que aconteceu."
            onChange={(e) => setMensagem(e.target.value)} style={{ resize: 'vertical' }} />
          <div id="s-msg-ajuda" className="row" style={{ justifyContent: 'space-between' }}>
            {erros.mensagem ? <span className="field-error" role="alert">{erros.mensagem}</span> : <span className="muted" style={{ fontSize: 12 }}>Não inclua senhas.</span>}
            <span className="muted" style={{ fontSize: 12 }}>{mensagem.trim().length}/{MAX}</span>
          </div>
        </div>

        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <Button variant="primary" type="submit" icon="mail" loading={enviando} disabled={naoConfigurado}>Enviar</Button>
        </div>
      </form>
    </div>
  );
}
