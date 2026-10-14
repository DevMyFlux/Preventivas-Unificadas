# MyFlux Preventivas — V2

Aplicação de acompanhamento e distribuição de ordens de serviço (OS) de manutenção preventiva das
unidades **HETRIN** e **HMB**, integrada ao Neovero (somente leitura por padrão).

- **Backend:** Python 3.12 · Flask · SQLAlchemy · pandas (escalas em Excel) · gunicorn
- **Frontend:** React 18 · TypeScript · Vite (sem biblioteca de UI/ícones: CSS e SVG próprios)
- **Banco:** PostgreSQL/Cloud SQL em produção (usuários, sessões, auditoria, overlay de colaboradores,
  propostas de atribuição). SQLite apenas para desenvolvimento.
- **Deploy:** push no GitHub → Railway (Dockerfile). **Nunca** usar `vercel --prod`.

Documentação complementar: [`docs/REGRAS-DE-NEGOCIO-V2.md`](docs/REGRAS-DE-NEGOCIO-V2.md) (decisões e
premissas de cada regra) · [`docs/SEGURANCA-E-OPERACAO.md`](docs/SEGURANCA-E-OPERACAO.md) (modelo de segurança,
auditoria, banco, runbook).

## O que mudou na V2

| Área | Resumo |
|---|---|
| Acesso | Login obrigatório; perfil **Dev** (administrador) e usuários **vinculados a uma unidade**; isolamento imposto no backend |
| Auditoria | Trilha append-only (quem, unidade, quando, módulo, ação, resultado), sessões com inatividade explícita, relatórios e exportação (Dev) |
| Regras | Desligados não são elegíveis a partir da data; gestão nunca é executante; limites diários (Elétrica 14 / Climatização 10); rondas e oficina de ar comprimido/vácuo por turno × par/ímpar |
| Preventivas | Mistura OS reais + projeções dos planos; status (Concluída / Em andamento / Parada / Pendente / Aguardando geração / Sem OS – verificar), **atraso real**, filtros por dias não contíguos, período, status, turno, par/ímpar; paginação e exportação consistentes com a tela |
| Neovero | Credenciais só por ambiente; paginação paralela; falhas tratadas (502/503) sem dados parciais; fila de atribuição com aprovação (escrita **desligada** por padrão) |
| Código | Duas unidades × ~700 linhas de rotas duplicadas → um blueprint único (`core/unit_blueprint.py`); regras críticas em serviços (`core/regras/*`, `core/preventivas.py`) |
| Sessão | Logout automático após **25 min** sem atividade válida, decidido no servidor (aviso 2 min antes, todas as abas, auditado) |
| Suporte | “Sugestões e Suporte” grava na **caixa de mensagens** da plataforma (só Dev lê/trata); e-mail via SMTP é opcional (`SUPORTE_ENTREGA=email`) |
| Utilização (Dev) | Tempo de sessão × ativo × ocioso, ativos agora, sem utilização registrada (com critérios), ficha do usuário, desbloqueio |
| Cargos (HETRIN) | Cargo exigido por plano, alternativas explícitas, desvios sinalizados, histórico de transferências |
| Frontend | Interface nova (tema claro/escuro, navegação lateral, KPIs clicáveis, seletor de dias, estados de carregamento/erro/vazio, acessibilidade) |

## Executar localmente

```bash
# Backend (porta 5000)
cd backend
python -m venv .venv && .venv\Scripts\activate      # Windows
pip install -r requirements-dev.txt
copy .env.example .env                              # preencha NEOVERO_*, DEV_ADMIN_*
python app.py

# Frontend (porta 5173, proxy /api -> 5000)
cd frontend
npm ci
npm run dev
```

Na primeira subida o Dev é criado a partir de `DEV_ADMIN_USERNAME` / `DEV_ADMIN_PASSWORD`. Sem essas variáveis
(e sem Dev cadastrado) ninguém consegue entrar — o log avisa. Não há credencial administrativa no código-fonte.
Também é possível criar usuários comuns pela tela **Administração → Usuários**.

## Testes e verificações

```bash
cd backend  && python -m pytest -q          # 450+ testes (unitários, API com Neovero falso, segurança)
cd backend  && python -m ruff check .       # lint
cd backend  && python -m pip_audit -r requirements.txt --no-deps --disable-pip
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

Nenhum teste fala com o Neovero real nem usa credenciais reais.

## Configuração (variáveis de ambiente)

Lista completa e comentada em [`backend/.env.example`](backend/.env.example). Para o deploy no Railway são
**obrigatórias** antes de promover a V2:

| Variável | Para quê |
|---|---|
| `NEOVERO_USERNAME`, `NEOVERO_PASSWORD` | Conta de serviço do Neovero (antes estavam no código — **gire a senha**, ver abaixo) |
| `DEV_ADMIN_USERNAME`, `DEV_ADMIN_PASSWORD` | Cria o perfil Dev na primeira subida |
| `DATABASE_URL` **ou** `CLOUD_SQL_CONNECTION_NAME` + `DB_USER` + `DB_PASSWORD` + `DB_NAME` | Banco persistente. Sem isso a aplicação usa SQLite no disco do container (efêmero: usuários/logs se perdem a cada deploy) |
| `APP_ENV=production` | Já definido no Dockerfile (cookie `Secure`, HSTS, proxy confiável) |

### Banco de dados / Cloud SQL

`gestao-rh-escalas:southamerica-east1:rh-monitoramento-db` é o **identificador** da instância Cloud SQL — ele não
autentica ninguém. Para conectar são necessários: o **motor** (o código assume PostgreSQL via `pg8000`), nome do banco,
usuário e senha, e uma credencial GCP com papel *Cloud SQL Client* disponível ao processo
(`GOOGLE_APPLICATION_CREDENTIALS` com a chave da service account, ou rede/Proxy). Alternativa mais simples: IP
autorizado + `DATABASE_URL`. As tabelas são criadas por migrações aditivas (`core/migrations.py`) na subida.

## Segredo antigo no histórico do Git

Versões anteriores do repositório continham o usuário/senha do Neovero no código (`core/neovero_client.py`). Remover do
código **não** apaga o histórico: **troque a senha dessa conta no Neovero** e configure a nova só por variável de ambiente.

## Estrutura

```
backend/
  app_factory.py, app.py        fábrica Flask + entrada WSGI
  core/
    settings.py, db.py, models.py, migrations.py     configuração por ambiente, banco, migrações
    auth/                       sessões, login, guarda global (deny-by-default), rotas /api/auth e /api/admin
    audit.py, relatorios_uso.py trilha de auditoria e relatórios
    unit_blueprint.py           rotas de uma unidade (parametrizado) — HETRIN e HMB usam o mesmo
    preventivas.py              ocorrências: OS reais + projeções, status, atraso, filtros, totais
    regras/                     elegibilidade, limites diários, regras nominais, nomes, resoluções
    motor_base.py               recomendação (score + gates) compartilhada
    atribuicoes.py              fila/propostas/aplicação no Neovero (escrita desligada por padrão)
    overlay_store.py            overlay de colaboradores no banco (semente em data/<unidade>/*.json)
  units/{grand_massif,brasilandia}/   escala (Excel), motor da unidade, regras específicas
  data/                         escalas (xlsx) e sementes do overlay
  tests/
frontend/src/
  app/                          shell, rotas por hash, autenticação
  features/{auth,unit,admin}/   telas
  shared/{api,ui,hooks,utils}/  cliente HTTP, componentes, utilidades
```
