# Hand-off para o Kiro: Jardim da Equipe, próximas fases

Documento autossuficiente. Leia a seção 1 e a seção 2 inteiras antes de escrever qualquer código.
As fases (seção 4) são independentes e devem ser feitas **na ordem**, uma branch por fase.

## 1. Regras inegociáveis

1. **`data/strikes.db` é o banco real do time (7 membros ativos, dados reais). Nunca apague, recrie,
   sobrescreva, nem semeie dados de teste nele.** O dono já perdeu dados uma vez. Todo teste e toda
   verificação manual usam um banco descartável fora do projeto, apontado pela variável de ambiente
   `STRIKES_DB` (ex.: `$env:STRIKES_DB="C:\temp\teste.db"`). Não faça commit de `data/strikes.db`
   (ele aparece como modificado no `git status`; ignore e nunca use `git add -A` sem conferir).
2. Mudanças de schema só **aditivas e idempotentes** (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD
   COLUMN` com default, checando antes se a coluna existe). O banco real não pode perder nada.
   `init_db()` roda a cada start e já faz backup diário antes.
3. Segredos (`ACCESS_CODE`, `SECRET_KEY`, qualquer token) nunca no repositório nem em mensagens.
4. **Sem punição, sem ranking de "quem está pior".** Falta nunca reduz sementes. Planta nunca morre.
   Só destaques positivos. Tom acolhedor e de time profissional (a equipe segue Scrum), nada infantil.
5. Interface em **português do Brasil com acentos**. Sem emojis em código/arquivos. Sem bibliotecas
   externas de front (HTML + CSS + JS puros). Comentários só para o porquê não óbvio.
6. Os arquivos do projeto usam **CRLF**. Mantenha (leia com `newline=""` e preserve).
7. Termine cada fase com `python -m unittest discover tests` verde (hoje: 213 testes) e README/docs
   atualizados. Escreva os testes **junto** do código (TDD na regra de jogo, que fica pura em `game.py`).

## 2. Contexto do projeto

**O que é.** Site Flask + SQLite que controla a presença de um time de 7 alunos (Arthur, Heloisa, Pablo,
Bruno, Luiz, Rachel, Guilherme) em 3 eventos diários (`daily`, `dev`, `encerramento`) num projeto
Scrum de 10 semanas. Virou um jogo: cada pessoa tem uma planta que cresce com a presença, chama de
sequência, sementes para gastar numa loja, metas da sprint, bosque e trilha. Só presença e jogo, nada
de punição.

**Stack.** Python 3.9+, Flask, sqlite3 (`Row`), Jinja2, CSS/JS puros, SVG inline para as plantas. Roda
com `python app.py` (porta 5000), em Windows/PowerShell. venv: `venv\Scripts\Activate.ps1`.
Deploy previsto: PythonAnywhere gratuito (`wsgi.py`, `ACCESS_CODE` e `SECRET_KEY` por variável de
ambiente, login por código de acesso em `/entrar`, header `X-Requested-With: fetch` obrigatório em
POST `/api/*`, já tratado no wrapper de `fetch` no topo de `static/app.js`).

**Arquivos principais**

| Arquivo | Papel |
|---|---|
| `app.py` | rotas, `init_db()`, consultas, `get_member_stats()` (calcula tudo derivado) |
| `game.py` | regras puras e testáveis: estágios, sequência, sementes, semanas, sprints, metas |
| `catalog.py` | catálogo e regras da loja (preços, requisitos) |
| `templates/` | `dia.html` (tela Hoje), `dashboard.html`, `loja.html`, `membro.html`, `sprint.html`, `_planta.html`, `_panorama.html` etc. |
| `static/app.js`, `static/style.css` | toda a interatividade e o visual |
| `docs/BALANCEAMENTO.md` | **leia**: todas as fontes de sementes e preços, com a simulação |
| `tests/` | `unittest`; use `Flask test client` com `STRIKES_DB` temporário |

**Schema atual** (todas as tabelas existem): `members(id, name, active, reset_cursor, created_at)`,
`attendance(member_id, event_date 'AAAA-MM-DD', event_type, status in presente|faltou|justificada,
UNIQUE(member_id, event_date, event_type))`, `config(chave, valor)`, `feriados(data, nome)`,
`compras`, `equipados`, `metas_sprint`, `prenda_payments` (legado, não usar).

**Modelo de jogo em uma tela**
- Dia letivo = seg a sex, sem feriado, entre `contar_a_partir_de` (15/10/2026) e o fim: D = 45,
  meta de floração = 36 presenças. Crescimento da planta é **por dia** (basta um evento presente).
- **Sementes** são derivadas do histórico, nunca guardadas (`game.calcular_sementes`): +1 por evento
  com presença (daily, dev, encerramento), +3 por semana fechada, marcos de sequência (+3/+5/+10/+20
  aos 5/10/20/40 dias), +1 por **dia cheio** do time, +20 ao florescer. Saldo = ganho - gastos
  (`compras`), nunca negativo. Detalhes e simulação em `docs/BALANCEAMENTO.md`.
- **Dia cheio** (`game.dia_cheio`): todos os membros **ativos** tiveram presença e ninguém faltou.
- **Registro de presença**: `POST /api/attendance` (upsert; `status` nulo apaga) devolve o estado de jogo
  só do membro marcado, em `jogo`; `static/app.js` atualiza a tela com ele.
- Tudo é recalculado do histórico: corrigir um registro antigo corrige o resto.

## 3. Fora do escopo (não implemente)

- **Integração com o GitLab** (sincronizar issues/cards): fica com o Claude, em fase posterior. Aqui só
  aceite referências `#123` digitadas.
- Pacote da Sprint, agradecimentos entre colegas, Retro do jardim (ficam para depois).
- Quiz, qualquer "mecânica que premie impedimento" (ver 4.4: impedimento **nunca** rende semente).

## 4. Fases

### Fase 1: ajustes rápidos (branch `feature/sementes-e-dia-cheio`)

**1.1 Bug do dia cheio (contadores).** O servidor calcula certo; a tela é que só atualiza o contador do
membro marcado. Quando todos os ativos ficam presentes, **todos** ganham +1, mas só o último vê.
- Aceite: ao marcar presença, a resposta de `/api/attendance` e de `/api/attendance/marcar_todos`
  inclui as sementes (e o estado de dia cheio) de **todos os membros ativos**; o JS atualiza todos os
  contadores `[data-sementes-for="ID"]` com a animação de "+N" existente. Teste de rota: 7 ativos,
  marcar todos, todos com `sementes_ganhas` +1 de dia cheio (a mesma conta de `game.calcular_sementes`).

**1.2 Animação de dia cheio.** Quando o dia passa de "não cheio" para "cheio" **durante o uso da tela**
(transição detectada na resposta da API, nunca ao simplesmente abrir/recarregar a página), mostrar uma
celebração em tela cheia, sobre o jardim: chuva de pétalas em CSS, mensagem "Dia cheio! +1 semente para
todos", some sozinha em ~3,5 s e pode ser dispensada com clique/Esc. Respeitar
`prefers-reduced-motion` (sem movimento: só um aviso fixo discreto). Não repetir se o dia sair e voltar
a ser cheio na mesma sessão (guardar em `sessionStorage`, com try/catch).

**1.3 Aba "Sementes"** (`/sementes`, item no menu): explica **de forma visual** todas as fontes de
sementes (cards: eventos, semana fechada, marcos de sequência, dia cheio, floresceu, boas-vindas),
com os valores lidos das constantes de `game.py` (nunca duplicar números no HTML). Inclui a seção
"E a sequência multiplica? Não: os marcos são bônus fixos" (ver `BALANCEAMENTO.md` seção 4.2). Se a
pessoa já escolheu "quem sou eu" na Loja (valor salvo no `localStorage`, ver `loja.html`), mostrar o
**progresso dela**: sequência atual, próximo marco e quanto falta, semanas fechadas, sementes ganhas
por fonte (`game.calcular_sementes` já devolve o detalhamento).
- Aceite: página responde 200, mostra todos os valores das constantes, funciona sem "quem sou eu".

**1.4 Card "Próximos marcos" no Painel**: lista cada membro ativo com a barra de progresso até o próximo
marco de sequência (ex.: "Bruno: 8 de 10 dias, +5 sementes"). Só destaques positivos; sem ordenar de
forma a expor quem está atrás (ordem alfabética). Tooltip/link do contador de sementes leva a `/sementes`.
Precisa de `game.proximo_marco(streak_atual)` puro, com testes.

**1.5 Boas-vindas.** Duas regras novas em `game.calcular_sementes` (derivadas, sem tabela nova):
- **+20 sementes de boas-vindas, uma vez**, para todo membro que tenha pelo menos 1 presença
  registrada. Chave nova no retorno: `por_boas_vindas`.
- **Selo e acessório "Fundador"** para quem teve presença em qualquer dia até `fundador_ate`
  (nova chave de `config`, default `2026-10-23`, editável na tela Calendário). Acessório **exclusivo**
  (não aparece à venda; entra no catálogo com `preco` 0 e flag `exclusivo`, e `pode_comprar` o recusa;
  o jogador o equipa se `fundador` for verdadeiro). Mostrar o selo no perfil e no álbum.
- Atualize `docs/BALANCEAMENTO.md` (totais passam a incluir +20; dedicado ~285, típico ~211) e os
  testes de totais (`tests/test_game.py`, `tests/test_loja.py`). Rode a simulação para conferir.

### Fase 2: membros convidados (branch `feature/membros-convidados`)

Pessoas de fora do time querem participar. Regras decididas pelo dono:
- Convidados têm planta, loja, sementes, streak e perfil como qualquer um, **mas não entram em nada que
  seja do time**: dia cheio, progresso do jardim coletivo, metas da sprint, destaques do time,
  panorama do grupo (denominador do mapa de calor), trilha/bosque do time e resumo da sprint.
- **Aparecem no jardim de forma secundária**: plantas menores, em segundo plano (atrás/abaixo das do
  time, em faixa separada "Convidados"), e por toque dá para ver streak, estágio e sementes
  (reaproveite o perfil `/membro/ID`, com a nota "convidado").
- Schema: `ALTER TABLE members ADD COLUMN tipo TEXT NOT NULL DEFAULT 'equipe'` (valores `equipe` |
  `convidado`), com a checagem de coluna existente. Tela Membros: ao criar/editar, escolher o tipo.
- Implementação: todo cálculo coletivo passa a usar só `tipo = 'equipe'` (centralize num helper, ex.:
  `ativos_do_time`). Convidados marcam presença normalmente na tela Hoje, em seção separada.
- Aceite: com 7 de equipe + 2 convidados, um dia com os 7 presentes e os convidados ausentes **é dia
  cheio**; progresso coletivo e metas não mudam ao adicionar um convidado; testes cobrindo cada ponto.

### Fase 3: celular pessoal, PIN e QR de presença (branch `feature/acesso-pessoal`)

- **Página pessoal no celular** (`/eu`): planta, sementes, Loja (comprar/equipar) e progresso da pessoa,
  com layout mobile primeiro (2 colunas ou cartões, alvos de toque grandes).
- **Identificação com PIN.** No primeiro acesso a pessoa escolhe o nome e cria um **PIN de 4 dígitos**
  (guardar só o hash com salt, ex.: `hashlib.scrypt`/`pbkdf2_hmac`, nova coluna `members.pin_hash`
  e `pin_salt`). Depois entra com nome + PIN; o celular lembra por 30 dias (cookie de sessão assinado,
  `HttpOnly`, `SameSite=Lax`). Limite de tentativas por IP e por membro (5 erros = bloqueio de 10 min).
  Na tela Membros, o dono pode **resetar o PIN** de alguém. O PIN protege contra um colega marcar
  presença ou gastar sementes no nome de outro (o site já é protegido pelo código de acesso do grupo).
- **QR de presença.** Em `/qr/<evento>` (acesso do dono/relator) mostra um QR grande e o código curto
  do evento do dia (`daily`, `dev` ou `encerramento`). Quem escaneia abre `/presenca/<codigo>`; logada
  a pessoa tem a presença **dela, naquele evento, naquele dia** registrada (`status = presente`, idempotente)
  e vê a confirmação com a animação da planta. Regras: o código muda a cada evento e **expira**
  (HMAC de `SECRET_KEY|data|evento|janela de 10 min`, aceitando a janela atual e a anterior); só marca
  o próprio membro, só hoje, nunca marca "faltou"; a marcação manual da tela Hoje continua funcionando.
  Gerar o QR **sem biblioteca externa** (implementação mínima de QR em Python puro no servidor, SVG) ou,
  se for inviável, uma única dependência pequena e pura em `requirements.txt` com justificativa no README.
- Aceite: testes de PIN (criação, erro, bloqueio, reset), de código expirado/outro evento/outro dia,
  de idempotência, e de que um membro não consegue marcar outro. Verificar em 375 px de largura.

### Fase 4: Ata da daily (branch `feature/ata-daily`)

Objetivo: substituir o Google Docs. O dono é o Scrum Master e entrega essa ata à professora. No módulo
anterior o formato era em **inglês**. A tela é em português, mas a **exportação** vem em inglês por
padrão, com opção `pt` (nova chave `config.idioma_ata`, default `en`).

**Dois documentos por dia**, mapeados nos eventos já existentes: `daily` -> "Daily" e `encerramento`
-> "Day Closing". Modelo exato a reproduzir na exportação (texto e HTML):

```
Daily — 26/08
Scrum: <relator>
Present: <presentes do dia, automático pela tabela attendance (qualquer evento)>

Done:
* <Nome>: <texto livre, pode citar cards como #101>
Doing:
* <Nome>: <texto livre>
Blockers: <texto livre ou "None">

Day Closing — 26/08
Scrum: <relator>
Present: <presentes>

Completed today:
* <Nome>: <texto>
Carried over:
* <Nome>: <texto>
New blockers: <texto ou "None">
Board updated: yes/no
```

- **Schema** (novas tabelas): `atas(data, tipo 'daily'|'fechamento', relator_id, bloqueios, quadro_atualizado,
  PRIMARY KEY(data, tipo))` e `ata_falas(data, tipo, member_id, feito, planejado, PRIMARY KEY(data, tipo,
  member_id))`. Em `daily`: `feito` = Done, `planejado` = Doing. Em `fechamento`: `feito` = Completed today,
  `planejado` = Carried over.
- **Modo relator**: uma tela (`/ata/<data>/<tipo>`) em que **uma pessoa digita por todos**, uma linha
  por membro presente, enquanto cada um fala. O relator é escolhido na tela (rodízio) e aparece em
  "Scrum:". Pensada para desktop e celular (campos grandes, salva sozinha ao sair do campo).
  Cada pessoa também pode, se quiser, escrever a própria fala do celular (Fase 3); o relator vê o que já
  veio preenchido e pode editar. **Ninguém é obrigado a escrever.**
- **Sem restrição ao "ontem"**: os campos são texto livre. Como ajuda opcional (nunca obrigatória nem
  limitante), mostre em "Done" um botão "usar o que ficou planejado ontem" que **acrescenta** o texto
  planejado do dia útil anterior, para a pessoa editar e somar coisas a mais. Quem entrega além do
  planejado simplesmente escreve.
- **Cards `#123`**: aceite `#número` digitado no texto e destaque-o como etiqueta; **não** exija nem
  gere link. (Configuração opcional `gitlab_base_url`, se vazia nada vira link; a integração com o
  GitLab da faculdade fica para o Claude, fora de escopo.)
- **Impedimentos** (`bloqueios`) são texto livre por ata e aparecem no relatório até serem marcados como
  resolvidos (lista "Blockers abertos" no relatório da sprint). **Impedimento nunca rende semente**
  (senão vira exploit). Só o texto e o status.
- **Recompensa (adubo fixo).** +1 semente por pessoa por ata (`daily` e `fechamento`) em que a fala
  esteja registrada com texto não vazio em `feito` ou em `planejado`, **sem avaliar conteúdo nem
  tamanho**. O relator ganha +1 por ata que redigiu (e +1 da própria fala se também falou). Nova chave
  `por_ata` e `por_relator` em `game.calcular_sementes`. A planta fica "adubada" no dia com um brilho
  e flores extras (**só visual**; crescimento continua por presença). Máximo adicional: 2 sementes por
  pessoa por dia, mais o bônus de relator. Atualize `BALANCEAMENTO.md` (dedicado ~375 no projeto, já com as boas-vindas e sem contar o bônus de relator).
- **Exportação** (a parte que o dono usa de verdade):
  - Página de ata imprimível (`@media print` limpa, para salvar em PDF).
  - Botão **"Copiar para o Google Docs"**: copia o texto formatado (HTML + texto puro, via
    `navigator.clipboard.write` com fallback de seleção) no formato acima, com `Present:` automático.
  - **Ata da sprint** (`/ata/sprint/<n>`): todas as dailies e fechamentos da sprint em ordem, os
    cards citados (`#...`) agrupados, a lista de impedimentos abertos e resolvidos e o panorama de
    presença. Linkar a partir de `/sprint/<n>` (Resumo da Sprint) para uso na Review e na Retro.
- Aceite: testes de modelo de dados, de cálculo da recompensa (fala vazia não conta; conteúdo e
  tamanho não influem; impedimento não rende), de relator, e de exportação (texto contém os rótulos
  exatos do modelo, `Present` correto, "None" quando vazio).

## 5. Como trabalhar e entregar

1. Uma branch por fase, a partir da `main` (`git switch -c ...`), commits pequenos com mensagem em
   português. A `main` local tem commits ainda não enviados ao GitHub; **não** dê `push --force`.
2. Teste manual sempre contra uma cópia: `$env:STRIKES_DB="C:\temp\jardim-teste.db"; python app.py`,
   criando dados de exemplo nessa cópia. Para ver o visual, abra desktop e 375 px de largura.
3. Ao fim de cada fase: `python -m unittest discover tests`, README (seção da fase) e
   `docs/BALANCEAMENTO.md` atualizados, e um resumo curto do que mudou e do que ficou de fora.
4. Dúvida de regra de jogo? Siga o princípio da seção 1.4: nunca punir. Se algo parecer exigir
   punir, penalizar volume de entrega ou premiar quem tem mais impedimentos, pare e pergunte.

## 6. Premissas assumidas (confirmar com o dono se discordar)

- Presença em **qualquer** evento do dia mantém o crescimento da planta por dia (não muda).
- Idioma da exportação da ata em inglês por padrão (conforme o modelo da professora), configurável.
- `fundador_ate` = 23/10/2026.
- Convidados ficam fora de qualquer métrica do time, inclusive do denominador do mapa de calor.
