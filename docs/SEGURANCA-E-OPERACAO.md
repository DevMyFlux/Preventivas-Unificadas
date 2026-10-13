# Segurança e operação — V2

## Modelo de acesso

- **Default-deny:** todo `/api/*` exige sessão, exceto `POST /api/auth/login` e `GET /api/health`
  (`core/auth/http.py::_guarda`). Rota nova nasce protegida; há teste que percorre **todas** as rotas sem login.
- **Perfis:** `dev` (administrador, único, todas as unidades) e `user` (vinculado a **uma** unidade). `/api/admin/*` exige
  `dev` na guarda **e** de novo em cada rota (`@dev_required`).
- **Unidade:** decidida pelo **prefixo da URL ↔ unidade gravada no cadastro** do usuário. Parâmetros, headers ou corpo
  vindos do cliente nunca escolhem a unidade (a empresa do Neovero vem da configuração do blueprint). Testes cobrem:
  rotas da outra unidade (leitura/escrita/exportação/regras/atribuições), `?unit=`, `X-Unit`, `empresa_id`, `//`, `..`,
  `%67randmassif`, caixa alta. Caches têm prefixo de unidade.
- **Mudar o vínculo ou desativar** um usuário encerra suas sessões na hora; **desativar não apaga histórico**.

## Credenciais e sessão

- Senhas: **scrypt** com salt (werkzeug). Mínimo 10 caracteres, com letras e números. Nunca em log/resposta.
- Sessão: token aleatório (256 bits) em cookie **HttpOnly + SameSite=Lax (+ Secure em produção)**; no banco só o
  **SHA-256** do token. **CSRF:** header `X-CSRF-Token` obrigatório em todo método que altera estado.
- Expiração: **30 min** de inatividade (`SESSION_IDLE_MINUTES`) e **12 h** absolutas (`SESSION_MAX_HOURS`).
- Login: resposta idêntica para usuário inexistente / senha errada / conta desativada (com custo de verificação
  equalizado); **bloqueio** após 5 falhas (15 min) e limite de **20 falhas/15 min por IP**. O IP do cliente só é lido de
  `X-Forwarded-For` quando há proxy confiável configurado (`TRUST_PROXY_HOPS`, 1 em produção).
- **Dev inicial:** `DEV_ADMIN_USERNAME`/`DEV_ADMIN_PASSWORD` (ambiente). Nada fixo no código. Sem Dev e sem variáveis, o log
  avisa e ninguém entra.
- Cabeçalhos: CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, HSTS (produção), `Cache-Control: no-store` na API.
  **CORS fechado** (antes `*`); só origens listadas em `CORS_ORIGINS`.
- Erros internos devolvem mensagem genérica (sem stack trace, sem texto de exceção). Exportações neutralizam injeção de
  fórmula (`=`, `+`, `-`, `@`).
- Dependências de produção: `pip-audit` e `npm audit --omit=dev` sem vulnerabilidades conhecidas.
  (`npm audit` completo ainda lista 6 achados **só de ferramentas de build/teste** — vite/vitest/esbuild — que exigem
  upgrade *major*; não vão para a imagem de produção.)

## Auditoria e relatórios de uso (somente Dev)

- Tabela `audit_log` **append-only** (não há rota de alteração/exclusão): usuário, unidade, data/hora (UTC), evento,
  módulo, ação (read/create/update/delete/export/login), recurso, resultado (`success`/`failure`/`denied`), HTTP, IP,
  user-agent e `details` **sanitizado** (chaves com `senha|token|secret|cookie|csrf|hash…` são mascaradas).
- Registra: login (sucesso/falha/bloqueio), logout, navegação entre módulos, **todas** as alterações, exportações,
  leituras dos módulos, acessos negados (com a unidade-alvo e a unidade do usuário) e erros. Leituras do próprio painel
  admin não poluem a trilha; alterações e exportações administrativas, sim.
- **Atividade × inatividade:** cada login abre uma **sessão** (`auth_sessions`) com `last_activity_at` (qualquer chamada
  autenticada + *heartbeat* a cada 60 s só se a aba está visível e houve interação nos últimos 5 min). Sem logout, a sessão é
  fechada como `idle_timeout` **na última atividade conhecida** (cobre fechar aba/queda de rede) ou `max_lifetime`.
  Relatórios dizem **“Sem registros no período”**, nunca “não utilizou”; trazem a data de início da coleta
  (`cobertura_desde`) para não confundir *sem cobertura* com *inatividade*.
- Painel (Administração → Histórico/Relatórios): filtros por usuário, unidade, módulo, resultado e período; indicadores
  (usuários ativos, logins, falhas, negados, sessões e tempo médio), atividade por dia, uso por módulo, falhas relevantes;
  exportação Excel/CSV.
- Retenção: não há expurgo automático (decisão a tomar; a tabela é indexada por data/usuário/unidade/evento).

## Banco de dados

| Tabela | Conteúdo |
|---|---|
| `users`, `auth_sessions`, `audit_log` | acesso e trilha |
| `colaborador_overlay` | status/vínculo/bloqueio/habilidades (antes JSON em disco — perdido a cada deploy) |
| `regra_resolucoes` | nomes confirmados nas regras nominais |
| `atribuicao_propostas` | fila de atribuição (antes/depois, aprovação, resultado) |
| `schema_migrations` | versões aplicadas |

Migrações em `core/migrations.py`: **aditivas e idempotentes**, com trava consultiva no PostgreSQL (vários workers
sobem juntos). Para evoluir: acrescentar `_mNNN_...` e registrar em `MIGRACOES`. **Cloud SQL:** ver README (motor,
credenciais GCP e usuário/senha/banco são necessários — o identificador da instância não autentica).

## Runbook rápido

| Situação | O que fazer |
|---|---|
| Ninguém consegue entrar (primeira subida) | Definir `DEV_ADMIN_USERNAME`/`DEV_ADMIN_PASSWORD` e reiniciar |
| Esqueci a senha do Dev | `DEV_ADMIN_RESET_PASSWORD=true` + nova `DEV_ADMIN_PASSWORD`, reiniciar, depois remover a flag |
| “Integração Neovero não configurada” (503) | Definir `NEOVERO_USERNAME`/`NEOVERO_PASSWORD` |
| “Neovero indisponível” (502) | Falha de rede/servidor no Neovero; nada é gravado em cache; tentar de novo |
| Dados de usuários somem a cada deploy | Banco não configurado (SQLite efêmero): definir `DATABASE_URL` ou `CLOUD_SQL_*` |
| Primeira carga lenta (~40 s para um mês) | Esperado: dezenas de consultas ao Neovero em paralelo; depois fica em cache (5–10 min) |
