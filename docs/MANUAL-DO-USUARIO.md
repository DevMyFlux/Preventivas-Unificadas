# Manual do Usuário — MyFlux Preventivas

Guia rápido para quem usa o sistema no dia a dia. Em poucos passos você acompanha as manutenções preventivas da sua
unidade, vê o que está pendente ou atrasado e confere quem deve executar cada ordem de serviço (OS).

---

## 1. Entrar e sair

1. Abra o endereço do sistema e informe **e-mail** e **senha** fornecidos pelo administrador.
2. Clique em **Entrar**.

- **Errou a senha 5 vezes?** A conta fica bloqueada por 15 minutos. Se esqueceu, peça ao administrador para redefinir.
- **Primeiro acesso:** o sistema pode pedir para você criar uma nova senha (mínimo de **10 caracteres, com letras e números**).
- **Trocar a senha depois:** botão **Senha**, no rodapé do menu lateral.
- **Sair:** botão **Sair**, no rodapé do menu lateral.

> **Segurança:** se você ficar **25 minutos sem usar** o sistema, ele desconecta sozinho. Dois minutos antes aparece um aviso
> com a contagem — clique em **Continuar conectado** para ficar. Depois de desconectado, é só entrar de novo. Se isso acontecer
> no meio de uma alteração, ela **não é salva**; refaça após entrar.

---

## 2. Conhecendo a tela

- **Menu lateral (esquerda):**
  - Dia a dia: **Preventivas**, **Colaboradores**, **Revisão**.
  - Configuração: **Atribuição**, **Planos**, **Regras**.
  - Rodapé: **Sugestões e Suporte**, **Senha**, **Sair**.
  - Você vê **somente a sua unidade** (HETRIN ou HMB).
- **Barra do topo:** o **período** que vale para as telas de Preventivas, Colaboradores e Atribuição — escolha
  as datas *De / Até* e clique em **Aplicar**, ou use os atalhos **Hoje**, **7 dias** e **Mês**. O botão de sol/lua alterna entre
  tema claro e escuro.
- **Celular:** o menu abre pelo botão de três linhas no canto superior esquerdo.

---

## 3. Preventivas (tela principal)

Mostra, para o período escolhido, tudo o que foi ou será feito: as **OS reais** do Neovero e as **previsões** dos planos.

### Os números no topo (clique para filtrar)
**Total no período · Concluídas · Em andamento · Pendentes · Em atraso · Para revisar · Sem candidato.**

### O que significa cada status

| Status | Significado |
|---|---|
| **Concluída** | OS fechada |
| **Em andamento** | OS iniciada (no Neovero aparece como "OS em Pendência") |
| **Parada** | OS em andamento com o equipamento registrado como parado e ainda sem retorno |
| **Pendente** | OS aberta, ainda não iniciada |
| **Aguardando geração** | Data futura: o Neovero ainda vai gerar a OS |
| **Sem OS – verificar** | Data passada e nenhuma OS encontrada: vale conferir no Neovero (não é atraso) |
| **Cancelada** | OS cancelada |

**Atrasada** = OS ainda não concluída com data anterior a hoje (mostra a etiqueta vermelha *Atrasada*).

### Como filtrar
- **Dias do período:** escolha dias específicos, mesmo não seguidos.
- **Status:** clique nas etiquetas (pode marcar mais de uma) e em **Em atraso**.
- **Busca livre:** plano, equipamento, setor ou número da OS.
- **Responsável** e **Turno** (diurno/noturno).
- **Mais filtros:** tipo de dia (par/ímpar) e intervalo de datas.
- Os filtros em uso aparecem como **etiquetas com ×** — clique no × para tirar um, ou em **Limpar filtros** para tirar todos.
- **Incluir ordens atrasadas de dias anteriores ao período** (ligado por padrão) traz as OS ainda abertas mesmo fora das datas.

### Lendo a tabela
- **Responsável no Neovero:** quem está na OS hoje. A etiqueta diz se é um executante válido (**Atribuída**) ou se há problema:
  **Gestão** (OS em nome do gestor), **Genérico** (ex.: "ELÉTRICA - DIURNO"), **Desligado**, **Bloqueado** ou **Sem responsável**.
- **Recomendado:** quem o sistema sugere para executar, respeitando escala, desligamentos, cargo exigido pelo plano e o limite
  diário (14 OS para elétrica, 10 para climatização).
- **Requer intervenção:** ninguém está apto naquela data. O motivo aparece logo abaixo (ex.: limite diário atingido, regra aguardando
  confirmação, falta do cargo exigido). O sistema **nunca escolhe alguém fora da regra por conta própria**.
- Uma linha vermelha = atrasada; âmbar = precisa de revisão.

### Botões
- **Atualizar:** busca os dados mais recentes do Neovero.
- **Exportar Excel:** gera a planilha **com os mesmos filtros** que você está vendo.

---

## 4. Revisão

Reúne o que precisa de atenção — **o sistema só mostra, não altera nada sozinho**. Abas:

1. **Ordens a revisar:** OS abertas cujo responsável não é um executante válido (gestão, genérico, desligado, bloqueado ou vazio).
   Clique nos números do topo para filtrar por tipo de problema.
2. **Planos com responsável inválido:** planos cujo responsável padrão está errado — toda OS nova desse plano já nasce com o problema.
   "Não identificado" significa que não foi possível descobrir o nome daquele responsável.
3. **Cargo fora da regra:** OS atribuídas a alguém de cargo diferente do que o plano exige (somente HETRIN).
4. **Transferências:** quando uma OS mudou de responsável desde que o sistema passou a acompanhar. Clique no lápis para anotar o
   **motivo** da troca.

---

## 5. Colaboradores

Lista o quadro da unidade (nome, cargo, turno/escala, limite diário, situação e vínculo).

- **Buscar** por nome, cargo ou turno; filtrar por **status**, **bloqueio** e **função** (executa OS × gestão/administrativo).
- **Clique no nome** para abrir a ficha: OS em aberto, histórico do período, habilidades e vínculo.
- Na ficha você pode:
  - **Marcar como desligado / Reativar** e informar **data de admissão** e **de desligamento** (a pessoa deixa de receber OS a partir da data de desligamento; o histórico é mantido);
  - **Bloquear / Desbloquear** — bloqueado não recebe recomendações (informe o motivo, por exemplo aptidão pendente);
  - **Adicionar / remover habilidades**.
- Toda alteração pede confirmação quando é importante e fica registrada.

---

## 6. Atribuição

Fila para **conferir** quem assumirá as OS que estão em nome de gestão, de nomes genéricos ou de desligados.

1. Marque as OS da fila e clique em **Criar proposta(s)** — o sistema mostra o executante sugerido para cada uma.
2. Em **Propostas**, **Aprove** ou **Rejeite** cada item.
3. **Simular aprovadas** confere se cada atribuição seria aceita (a OS ainda existe, o responsável não mudou, há vaga no dia).
4. **Aplicar no Neovero** só funciona quando o administrador habilitar a escrita. Hoje o aviso no topo da tela informa o estado; enquanto
   estiver desabilitado, use a simulação e faça a troca no próprio Neovero.

---

## 7. Planos

Consulta dos planos de manutenção (descrição, periodicidade, oficina, procedimento, ativo/inativo).
Use a busca e o filtro de situação; **Exportar Excel** gera a lista filtrada.

## 8. Regras

Mostra as regras fixas da unidade (por exemplo, quem faz a ronda diária conforme turno e dia par/ímpar). Se alguma regra citar um nome
que o sistema não consegue identificar com certeza (apelido repetido), ela fica **Aguardando confirmação**: escolha a pessoa certa na
lista e clique em **Confirmar**. Até lá, essas OS aparecem como *Requer intervenção*, em vez de receberem alguém ao acaso.

---

## 9. Sugestões e Suporte

Menu lateral → **Sugestões e Suporte**.

1. Confira **Nome** e **E-mail de retorno**.
2. Escolha o **Tipo**: *Sugestão*, *Problema* ou *Melhoria*.
3. Escreva a **Mensagem** (mínimo de 10 caracteres; descreva onde estava, o que esperava e o que aconteceu). **Não inclua senhas.**
4. Clique em **Enviar** uma única vez. A mensagem fica registrada na plataforma e a administração vai ler.

Limite de 5 mensagens por hora; mensagens idênticas em sequência são recusadas.

---

## 10. Dúvidas frequentes

| Situação | O que fazer |
|---|---|
| "Desconectado por inatividade" | Entre novamente; refaça a última alteração se ela não foi salva |
| Os números parecem desatualizados | Clique em **Atualizar** |
| Uma OS está "Sem OS – verificar" | Confira no Neovero se a OS foi gerada; o sistema só avisa |
| Aparece "Requer intervenção" | Leia o motivo abaixo; normalmente é limite diário, falta de pessoal do cargo exigido ou regra pendente |
| OS em nome do gestor | É normal o Neovero criar assim; veja a sugestão em **Recomendado** ou use **Atribuição** |
| Não vejo uma opção que um colega tem | Algumas áreas são exclusivas da administração |
| Esqueci a senha / conta bloqueada | Peça ao administrador para redefinir |
| Algo não funciona | Use **Sugestões e Suporte** → tipo *Problema* |
