# Hand-off para o Kiro, parte 2: preencher a daily melhor e integração com o GitLab

Complementa `docs/HANDOFF-KIRO.md` (leia a seção 1, "Regras inegociáveis", e a seção 2, "Contexto", de lá:
valem aqui). Este documento cobre duas fases novas, **na ordem**, uma branch por fase:
**Fase 5** (`feature/daily-melhor`) e **Fase 6** (`feature/gitlab`).

O site já está **publicado** (PythonAnywhere, plano gratuito) e em uso pelo time. Toda mudança de schema
precisa ser **aditiva e idempotente**: no próximo "Reload" do servidor o `init_db()` roda sobre o banco real.

## 1. Regras (resumo; as completas estão no hand-off 1)

1. **`data/strikes.db` é o banco real: nunca tocar.** Teste sempre com `STRIKES_DB` apontando para uma cópia.
   Use `python scripts/criar_banco_demo.py <caminho>` para criar um banco de mentira (7 da equipe, 3 convidados,
   histórico, atas, PIN `1234` da Arthur). O arquivo `data/*.db` está no `.gitignore`; não o adicione.
2. **Não faça commit.** O dono comita depois da revisão (e nunca use `git add -A` sem excluir o banco).
3. Segredos (token do GitLab, `ACCESS_CODE`, `ADMIN_CODE`, `SECRET_KEY`, tokens de sincronização) **nunca** no
   repositório, em logs, em mensagens de erro nem em testes (use valores falsos óbvios nos testes).
4. UI em português com acentos; sem emojis em código/arquivos; sem bibliotecas novas (stdlib apenas, inclusive
   para falar com o GitLab: `urllib`); CRLF nos arquivos; `python -m unittest discover tests` verde (hoje: 385).
5. Sem punição, sem ranking: **nada aqui premia quantidade de cards** nem de commits. Escolher um card do GitLab
   **não rende semente**; só a fala preenchida rende (regra de `docs/BALANCEAMENTO.md`, seção 4.1, Jeito 7).
6. Confira o visual de verdade (suba o app com o banco de demonstração e abra em 375 px), não só o código.

**Armadilhas já encontradas neste projeto (economize tempo):**
- `init_db()` só roda em `python app.py` e no `wsgi.py`; ao subir um servidor de teste importando `app`, chame
  `app.init_db()` antes.
- Templates ficam em cache sem o modo debug: reinicie o servidor de teste ao editá-los.
- No Windows, **feche toda conexão sqlite** nos testes (um `sqlite3.connect` esquecido trava o `os.remove` do
  próximo `setUp`).
- Nos testes, o `test_client` é "localhost" e portanto **administrador**. Para simular um visitante use
  `environ_overrides={"REMOTE_ADDR": "192.168.0.23"}` e `base_url="http://192.168.0.10:5000"` (ver `tests/test_papeis.py`).
  Cookies de sessão são por host: use `session_transaction(base_url=...)` com o mesmo host.
- Heredocs com Python e aspas quebram no shell: escreva scripts em arquivo.

## 2. Como o jogo e as permissões funcionam hoje (o que você vai reaproveitar)

- **Sementes** (derivadas do histórico, `game.calcular_sementes`): +1 por evento com presença (daily, dev,
  encerramento); **+1 por ata (Daily e Day Closing) em que a pessoa tem fala preenchida** (`feito` ou `planejado`
  não vazio, sem avaliar conteúdo); +1 ao relator por ata que redigiu; mais os bônus de semana, dia cheio, marcos,
  floresceu e boas-vindas. Detalhes em `docs/BALANCEAMENTO.md`.
- **Ata**: tabelas `atas(data, tipo, relator_id, bloqueios, bloqueios_resolvidos, quadro_atualizado)` e
  `ata_falas(data, tipo, member_id, feito, planejado)`. `daily` ↔ evento `daily`; `fechamento` ↔ `encerramento`.
  Na Daily: `feito` = Done, `planejado` = Doing. Formatação/exportação em `ata_fmt.py` (módulo puro, em inglês
  por padrão). Cards `#123` no texto viram etiqueta; `config.gitlab_base_url` (vazio por padrão) vira link.
- **Quem altera o quê** (README, "Quem pode alterar o quê"): o **administrador** (quem está no computador do
  sistema, o Scrum de hoje, ou quem entrou com `ADMIN_CODE`) edita o que é de todos. O **relator de uma ata**
  edita aquela ata (`_pode_editar_ata`). Cada pessoa edita **a própria** fala por `POST /api/ata/minha-fala`
  (exige `/eu` + PIN) e usa a própria loja.
- **QR de presença**: `/qr/<evento>` (admin) mostra a data e o QR; quem escaneia cai em
  `/presenca/<evento>/<código>` (`templates/presenca.html`), que oferece "Marcar presença" ou "Marcar e preencher a
  Daily (+1 semente)".
- **Página pessoal** `/eu` (PIN): planta, sementes, loja e "Minha fala de hoje" (Daily e Day Closing), com
  salvamento automático.

## 3. O que o dono pediu (problemas a resolver)

1. Quem **marca presença primeiro não consegue preencher a daily depois**: na tela de presença, o sucesso esconde
   as ações.
2. Ao abrir a **ata**, a pessoa (ex.: Heloisa) **não consegue editar a própria fala** (a tela fica toda desabilitada
   para quem não é relator/admin). Se escreveu algo errado, não corrige.
3. **Não está claro quanto rende cada coisa**: marcar presença = +1 semente (pelo evento); preencher a daily = +1
   semente extra (bônus da ata). O total correto de "presença + fala" é +2 e isso precisa aparecer.
4. **Integração com o GitLab** da faculdade: ler o quadro (Kanban) e oferecer, na hora de preencher a daily, os
   cards **que estão em "Doing" no nome da pessoa** e os que estão em **"Waiting review"**, escolhendo com um
   toque. Sempre deve ser possível digitar um card **livre** (exceções). Mais uma aba/bloco de **Review** na daily.

## 4. Fase 5: preencher a daily sem atrito (`feature/daily-melhor`)

**5.1 Presença e fala em sequência, sem esconder nada.** Em `/presenca/<evento>/<código>`:
- Depois de **"Marcar presença"**, a tela **não some**: mostra "Presença registrada" e **mantém visível** o
  botão/formulário "Preencher a Daily" (e a fala existente, se houver) para a pessoa preencher agora ou **voltar
  depois** (o mesmo QR ou o link de Meu jardim). O mesmo vale para o Day Closing no encerramento. No Dev (sem ata),
  só presença.
- "Marcar e preencher" continua como atalho. Salvar a fala sempre faz também a presença (idempotente).
- Aceite: teste de rota de que, após `POST` só de presença, um novo `POST` com `fala` grava a fala; e de que a página
  renderiza o formulário no estado "já presente".

**5.2 Cada pessoa edita a própria linha na ata.** Em `/ata/<data>/<tipo>`, quem está logado com PIN (`/eu`) e **não**
é relator/admin vê **só a própria linha editável** (as demais continuam desabilitadas, só leitura). O salvamento usa
`/api/ata/minha-fala` (já valida que é a própria pessoa). Mantém o auto-salvar (pausa de 1,2 s + blur) e o polling
de 4 s sem sobrescrever o campo em edição. Quem não está logado vê o aviso atual com "Entrar com o PIN".
- Aceite: testes de que o logado não-relator consegue `minha-fala` na própria linha e **não** edita a linha de outro
  (`/api/ata/salvar` continua 403); página renderiza só os campos dele habilitados.

**5.3 Deixar claro quanto rende (sem prometer o que não existe).** Um bloco "Quanto rende" lido das constantes de
`game.py` (**nunca** números fixos no HTML): na tela de presença e em "Minha fala":
- "Marcar presença: +{SEED_POR_EVENTO[evento]} semente"
- "Preencher a {Daily|Day Closing}: +{SEED_ATA} semente de bônus (uma vez por ata, mesmo editando depois)"
- "Os dois juntos: +{soma} hoje".
Depois de salvar, mostrar o resultado real: "Você ganhou +1 pela presença e +1 pela fala" (ou só o que ainda não
tinha). Editar a fala **não rende de novo**; apagar todo o texto remove o bônus (é derivado). Dizer isso em uma
linha discreta.
- Aceite: teste que a página contém os valores das constantes (alterar a constante no teste e ver a página mudar);
  teste de que editar não duplica (`calcular_sementes` por ata continua 1).

**5.4 Pequenos acabamentos relacionados (se sobrar tempo):** botão "Minha fala de hoje" no topo do `/eu` com
destaque quando ainda está vazia; na ata, indicar quem já preencheu a própria fala (um pontinho) sem expor
"quem falta" de forma punitiva.

## 5. Fase 6: GitLab (`feature/gitlab`)

**Objetivo:** na daily, sugerir os cards da pessoa que estão em **Doing** (para o campo "Doing/planejado") e em
**Waiting review** (para um campo/aba **Review**), com seleção por toque; sempre aceitando digitação livre.

### 6.0 Decisão de arquitetura (importante)

O GitLab é o **da faculdade** (endereço próprio, não é o gitlab.com). O plano gratuito do PythonAnywhere só acessa
uma lista permitida de sites na saída, então o **servidor provavelmente não consegue falar com esse GitLab**. Por
isso a integração é feita por **empurrar o retrato do quadro**:

- Um **script no computador do dono** (`scripts/sync_gitlab.py`, stdlib pura) lê o GitLab com o **token pessoal do
  dono** e **envia um retrato (snapshot)** do quadro para o site publicado (`POST /api/gitlab/snapshot`).
- O **token do GitLab fica só no computador do dono** (variável de ambiente `GITLAB_TOKEN`); **nunca vai para o
  servidor**. O servidor guarda só os cards (número, título, link, responsável, coluna).
- O dono roda o script quando quiser (ou agenda no Agendador de Tarefas do Windows a cada ~10 min).
- (Opcional, se couber) modo "direto": se existir `GITLAB_TOKEN`/`GITLAB_URL`/`GITLAB_PROJECT` **no servidor** (ex.:
  rodando local ou numa hospedagem sem restrição), um endpoint admin "Sincronizar agora" busca direto. A base
  (função que monta o retrato a partir das respostas da API) deve ser a **mesma** nos dois modos.

### 6.1 Banco, configuração e mapeamento de usuários

- Coluna `members.gitlab_user TEXT` (nome de usuário no GitLab), migração aditiva. Na tela **Membros** (só admin)
  um campo "Usuário no GitLab" por pessoa, salvo por `POST /api/membros/<id>` (já protegido por admin).
- Tabela `gitlab_cards(iid INTEGER NOT NULL, coluna TEXT NOT NULL CHECK (coluna IN ('doing','review')),
  usuario TEXT NOT NULL, titulo TEXT NOT NULL, url TEXT NOT NULL DEFAULT '', labels TEXT NOT NULL DEFAULT '',
  atualizado_em TEXT NOT NULL DEFAULT (datetime('now')), PRIMARY KEY (iid, coluna, usuario))`.
- `config`: `gitlab_ultima_sync` (data/hora do último retrato) e `gitlab_base_url` (a URL do **projeto**, usada para
  os links dos cards; já existe, hoje vazia: o snapshot pode preenchê-la se vier vazia).
- Nomes das colunas do quadro são **configuráveis** (o time pode chamá-las de outro jeito):
  `GITLAB_LABEL_DOING` (padrão `Doing`) e `GITLAB_LABEL_REVIEW` (padrão `Waiting review`), comparação sem
  diferenciar maiúsculas/minúsculas, no **script**. Um card em "Doing" tem a label de Doing e `state=opened`.

### 6.2 O script (`scripts/sync_gitlab.py`)

Variáveis de ambiente (lidas só do ambiente, nunca de arquivo do repositório):
`GITLAB_URL` (ex.: `https://git.exemplo.edu.br`), `GITLAB_PROJECT` (ID numérico **ou** caminho `grupo/projeto`),
`GITLAB_TOKEN` (token pessoal com escopo `read_api`), `SITE_URL` (ex.: `https://usuario.pythonanywhere.com`),
`SITE_SYNC_TOKEN` (segredo compartilhado com o servidor), mais as labels acima (opcionais).
Comportamento:
1. `GET {GITLAB_URL}/api/v4/projects/{id}/issues?state=opened&labels={label}&per_page=100&page=N` (header
   `PRIVATE-TOKEN`), paginando, **uma vez por coluna**. Para cada issue, pega `iid`, `title`, `web_url`,
   `labels` e **todos os `assignees[].username`** (um card pode ter mais de um responsável: gera uma linha por
   responsável). Issues sem responsável são ignoradas (ou guardadas com `usuario=''` e não oferecidas).
2. Monta o JSON `{"gerado_em": "...", "projeto_url": "...", "cards": [{"iid":.., "coluna":"doing"|"review",
   "usuario":"..", "titulo":"..", "url":"..", "labels":[..]}]}` e faz `POST {SITE_URL}/api/gitlab/snapshot` com
   `Authorization: Bearer {SITE_SYNC_TOKEN}`.
3. Opções: `--simular` (não envia; imprime o resumo), `--listar-usuarios` (imprime os usernames que aparecem nos
   cards, para o dono preencher o mapeamento na tela Membros), `--arquivo caminho.json` (envia um JSON pronto, útil
   para teste). Mensagens de erro claras (token inválido, projeto não encontrado, sem rede) **sem imprimir o token**.
4. Timeout de rede e tratamento de erros; saída com código diferente de zero em falha (para o agendador).
- Não usar bibliotecas externas. Funções de montagem do retrato **puras e testáveis** (entrada: listas de issues no
  formato da API; saída: lista de cards), em um módulo próprio (`gitlab_sync.py`) importado pelo script e pelo app.

### 6.3 Endpoints

- `POST /api/gitlab/snapshot` (autenticado **só** por `Authorization: Bearer <SYNC_TOKEN>`, comparado com
  `hmac.compare_digest` ao valor da variável de ambiente `SYNC_TOKEN` do **servidor**; sem `SYNC_TOKEN`
  configurado, responde 404/403). **Não** exige cookie nem o cabeçalho `X-Requested-With` (quem chama é um script):
  ajustar `guarda_de_acesso` para liberar esta rota **apenas** quando o Bearer estiver correto, e **nunca** liberar
  outras. Limite de tentativas por IP para token errado. Em uma transação: substitui todo o conteúdo de
  `gitlab_cards`, atualiza `gitlab_ultima_sync` e, se `gitlab_base_url` estiver vazia, preenche com `projeto_url`.
  Valida o formato (colunas permitidas, tamanhos máximos de texto, limite de ~2000 cards). Responde
  `{"ok": true, "cards": N}`.
- `GET /api/gitlab/cards?member_id=ID` (qualquer pessoa vê; só leitura): devolve
  `{"doing": [...], "review": [...], "ultima_sync": "...", "configurado": bool}` para o `gitlab_user` do membro.
  Sem usuário mapeado ou sem retrato: listas vazias e uma dica ("peça ao admin para preencher seu usuário do GitLab"
  ou "ainda não sincronizado").

### 6.4 Interface

- **Ata e "Minha fala"**: abaixo do campo "Doing/Planejado" (Daily) mostrar "Seus cards em Doing (GitLab)" como
  **chips tocáveis** (`#123 título curto`). Tocar **acrescenta** `#123 título` ao campo (nunca sobrescreve; tocar
  de novo não duplica) e salva pelo mesmo fluxo de auto-salvar. Se o card já está no texto, o chip aparece marcado.
- **Review**: novo campo "Review" por pessoa na Daily (coluna `ata_falas.review TEXT NOT NULL DEFAULT ''`, migração
  aditiva) com chips dos cards **em "Waiting review" no nome da pessoa** e **digitação livre**. É um **bloco extra**
  da ata (aba "Review" no relator e bloco no "Minha fala"). Na exportação, entra como `Review:` / `Waiting review:`
  (EN) e `Em revisão:` (PT), **só se houver texto**; se ninguém tiver, o documento fica idêntico ao modelo da
  professora. Fala com só `review` preenchido **conta** como fala preenchida? **Não**: o bônus de semente continua
  só para `feito` ou `planejado` (decisão: não premiar volume nem criar atalho de exploit).
- **Texto livre sempre disponível**: os chips são ajuda; qualquer `#número` digitado continua virando etiqueta/link.
- **Link dos cards**: com `gitlab_base_url` preenchida, `#123` vira `{base}/-/issues/123` na ata e na exportação.
- Cabeçalho discreto: "Cards do GitLab atualizados às HH:MM" (ou "ainda não sincronizado"). Se o retrato tem mais de
  ~1 dia, aviso "dados antigos". Nunca bloquear o preenchimento se o GitLab estiver fora.
- Tela **Membros** (admin): campo "Usuário no GitLab" e um aviso de quem ainda não está mapeado.

### 6.5 Testes e demonstração

- Fixtures JSON no formato real da API do GitLab (issues com `assignees`, `labels`, `web_url`, `iid`) e testes **sem
  rede** da montagem do retrato (casos: vários responsáveis, label em maiúsculas/minúsculas, issue sem responsável,
  card em Doing **e** em Waiting review, paginação simulada).
- Testes de rota: snapshot com Bearer certo/errado/ausente; sem `SYNC_TOKEN` no servidor; formato inválido; substitui
  (não acumula); `GET /api/gitlab/cards`; chips aparecem na ata/`/eu` quando há retrato e mapeamento; export com e
  sem `review`.
- `scripts/criar_banco_demo.py`: preencher `gitlab_user` das pessoas e um retrato de exemplo, para ver os chips.
- README: seção nova "Integração com o GitLab" com o passo a passo para o dono: criar o token pessoal (Preferências do
  usuário > Access tokens, escopo `read_api`), achar o ID do projeto (Configurações > Geral), definir as variáveis no
  PowerShell, rodar `--simular`, `--listar-usuarios`, rodar de verdade, e agendar no Windows. E onde definir
  `SYNC_TOKEN` no servidor (arquivo WSGI do PythonAnywhere, como os outros códigos). **Nada de segredo no README.**

## 6. Fora do escopo

- Sementes por card, por commit ou por merge request (nenhuma recompensa por volume).
- Escrever no GitLab (mover cards, comentar): a integração é **somente leitura**.
- Pacote da Sprint, Retro do jardim e agradecimentos entre colegas (ficam para depois).

## 7. Como trabalhar e entregar

1. Fase 5 primeiro, em `feature/daily-melhor`; só depois a Fase 6 em `feature/gitlab` (a partir da Fase 5 ou da
   `main`, o que for mais simples). Uma branch por fase, **sem commit** (o dono comita).
2. Teste manual contra o banco de demonstração; abra desktop e 375 px. Mostre telas/trechos relevantes.
3. Ao fim de cada fase: testes verdes, README e `docs/BALANCEAMENTO.md` (se algo de semente mudar, o que **não**
   deve acontecer aqui) atualizados e um resumo curto do que mudou e do que ficou de fora.
4. Dúvida de regra? Siga "sem punição, sem ranking, sem premiar volume". Se algo exigir mudar de arquitetura
   (por exemplo, o servidor conseguir falar com o GitLab), pare e pergunte.

## 8. Premissas (confirmar com o dono se discordar)

- Colunas do quadro: **Doing** e **Waiting review**; nomes configuráveis no script.
- O mapeamento pessoa ↔ usuário do GitLab é manual (campo na tela Membros).
- O retrato do quadro é empurrado do computador do dono; o servidor publicado nunca guarda o token do GitLab.
- O campo **Review** não rende semente.

## 9. Fase 6b: cards do Backlog (e recém-fechados) no campo "Done" (`feature/gitlab-backlog`)

Pedido do dono: no **primeiro campo da ata (Done / "o que fiz")** também deve ser possível **escolher cards do
Backlog**, ou eles devem aparecer como sugestão, além dos que já aparecem em Doing e Waiting review. Parta da `main`
(já tem as Fases 5 e 6). Mesmas regras: sem commit, sem segredo, stdlib, CRLF, testes verdes, nada rende semente.

**Comportamento desejado**
- No campo **Done**, abaixo do texto, mostrar chips tocáveis com: (a) os cards **da própria pessoa** em Doing e em
  Waiting review (muitas vezes o que ela concluiu saiu dali), (b) os cards **dela fechados recentemente** (coluna
  `done`, padrão últimos 7 dias) e (c) uma caixa **"Buscar no Backlog"**: ao digitar número ou parte do título,
  lista até 20 cards do Backlog **de qualquer pessoa ou sem responsável**; tocar acrescenta `#iid título` ao
  campo (nunca sobrescreve, não duplica). Digitação livre de `#123` continua funcionando sempre.
- Vale na **ata (relator)**, no **"Minha fala"** do `/eu` e no formulário da **tela de presença** (campo Done).
- No campo Doing/planejado, a caixa de busca do Backlog também pode aparecer (quem vai pegar um card do backlog
  hoje). Se ficar poluído no celular, deixe só no Done e em um link "buscar no backlog" no Doing.

**Dados (retrato)**
- Novas colunas no retrato: `backlog` (issues **abertas** com a label do Backlog, **inclusive sem responsável**;
  `usuario` vazio = sem responsável; um card com vários responsáveis gera uma linha por responsável) e `done`
  (issues **fechadas** nos últimos N dias, só as que têm responsável). Nomes por variável de ambiente no script:
  `GITLAB_LABEL_BACKLOG` (padrão `Backlog`), `GITLAB_DIAS_FECHADOS` (padrão 7). Confirme com o dono os nomes reais
  das colunas do quadro (as "labels" de cada lista do board).
- **Migração do banco**: a tabela `gitlab_cards` tem `CHECK (coluna IN ('doing','review'))`; no SQLite isso exige
  **recriar a tabela** (criar a nova, copiar, trocar). Faça de forma **idempotente e em transação**, só se a tabela
  ainda não aceitar as novas colunas, sem perder dados. A chave primária continua `(iid, coluna, usuario)`.
- Limites: o endpoint de snapshot já limita a ~2000 cards; no script, limite o Backlog a ~500 mais recentes
  (e avise no resumo se cortou). Validar tamanhos de texto como nas outras colunas.

**Endpoints**
- `GET /api/gitlab/cards?member_id=ID` passa a devolver também `done` (os recém-fechados dele). O `backlog` **não**
  vem aqui inteiro (pode ser grande).
- Novo `GET /api/gitlab/backlog?q=texto&limit=20`: busca por número exato (`123` ou `#123`) ou trecho do título
  (sem diferenciar maiúsculas/minúsculas) entre os cards do Backlog; devolve `[{iid, titulo, url, responsaveis:[...]}]`,
  sem duplicar o mesmo card por responsável. Somente leitura, aberto a quem vê o site. Sem retrato: lista vazia.

**Testes**: montagem do retrato com Backlog (com e sem responsável, vários responsáveis, label em
maiúsculas/minúsculas, card fechado antigo fora da janela); migração da tabela (banco antigo com `CHECK` antigo
vira o novo sem perder linhas, e rodar duas vezes não quebra); busca (número, trecho, limite, vazio); rota
`/api/gitlab/cards` com `done`; chips aparecem no Done da ata e do `/eu`. `scripts/criar_banco_demo.py` deve criar
cards de exemplo de backlog e done. README: atualizar a seção do GitLab (novas variáveis e o que cada coluna faz).
