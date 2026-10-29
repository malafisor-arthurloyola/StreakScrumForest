# Jardim da Equipe — Controle de Presenca

Site local para controlar a presenca dos membros do grupo em 3 eventos diarios obrigatorios:
**Daily**, **Presenca no Dev** e **Encerramento**. Cada presenca faz a planta de cada membro crescer.
Dados ficam salvos em um banco SQLite real (`data/strikes.db`), nao em localStorage.

## Documentação

- [docs/GDD.md](docs/GDD.md): **Game Design Document**. O que o jogo é, as regras, a economia de sementes, a loja,
  a ata e a rodada de fala, os papéis, a direção de arte e o que ainda é ideia.
- [docs/PROCESSO.md](docs/PROCESSO.md): relato do processo de criação, patch notes, problemas encontrados e correções.
- [docs/BALANCEAMENTO.md](docs/BALANCEAMENTO.md): as contas por trás das sementes e dos preços.
- [docs/HANDOFF-KIRO.md](docs/HANDOFF-KIRO.md) e [docs/HANDOFF-KIRO-2.md](docs/HANDOFF-KIRO-2.md): notas de passagem entre agentes.

## Como rodar

Pre-requisito: Python 3.9+ instalado.

1. Abra um terminal nesta pasta (`Contagem de strikes`).
2. (Recomendado) crie e ative um ambiente virtual:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
   No PowerShell, o comando de ativar é `venv\Scripts\Activate.ps1` (a partir da pasta do projeto).
   Se você estiver dentro de `venv\Scripts`, use `.\Activate.ps1` (o `cd Activate.ps1` não funciona,
   porque é um script, não uma pasta). Se aparecer erro de permissão de scripts, rode uma vez
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. Para sair do venv: `deactivate`.
3. Instale a dependencia (Flask):
   ```bash
   pip install -r requirements.txt
   ```
4. Rode o servidor:
   ```bash
   python app.py
   ```
5. Abra no navegador: [http://localhost:5000](http://localhost:5000)
6. Para rodar os testes (sempre com um banco de teste, nunca o real):
   ```powershell
   $env:STRIKES_DB = "$env:TEMP\strikes-teste.db"   # PowerShell
   python -m unittest discover tests
   ```
   Detalhes e os comandos para cmd/Linux na seção [Testes](#testes).

## Comandos do dia a dia (cola rápida)

Troque `SEUUSUARIO` pelo seu usuário do PythonAnywhere (o nome depois de `/home/` na aba Files).
Todos os comandos locais são para rodar **a partir da pasta do projeto** (`Contagem de strikes`).

### No seu computador (PowerShell)

| Para quê | Comando |
|---|---|
| Entrar na pasta do projeto | `cd "C:\Users\Inteli\Desktop\Módulo 3\Contagem de strikes"` |
| **Ativar o ambiente virtual** | `venv\Scripts\Activate.ps1` (aparece `(venv)` no começo da linha) |
| Sair do ambiente virtual | `deactivate` |
| Se der erro de permissão ao ativar (uma vez só) | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| **Rodar o site local** (com os dados reais) | `python app.py` e abrir http://localhost:5000 |
| Parar o site | `Ctrl + C` no terminal |
| Rodar o site com **banco de mentira** (seguro para testar) | `python scripts/criar_banco_demo.py C:\temp\jardim-demo.db` e depois `$env:STRIKES_DB = "C:\temp\jardim-demo.db"; python app.py` |
| Recriar o banco de mentira do zero | `python scripts/criar_banco_demo.py C:\temp\jardim-demo.db --forcar` |
| Voltar a usar o banco real no mesmo terminal | `Remove-Item Env:STRIKES_DB` (ou feche e abra o terminal) |
| **Rodar os testes** | `python -m unittest discover tests` (deve terminar em `OK`) |
| Instalar/atualizar as dependências | `pip install -r requirements.txt` |
| **Gerar um `SECRET_KEY`** novo | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| Backup do banco local agora | `python scripts/backup_db.py` |
| Ver quem está usando a porta 5000 (se der "porta em uso") | `netstat -ano \| findstr :5000` e depois `taskkill /PID <número> /F` |

> Dica: se o navegador mostrar a versão antiga do visual depois de atualizar, use **Ctrl + F5**.
> Cuidado: com `$env:STRIKES_DB` definido, o site usa **aquele** banco. Sem a variável, ele usa o real
> (`data/strikes.db`). A variável vale só para o terminal onde foi definida.

### No PythonAnywhere (aba Consoles > Bash)

| Para quê | Comando |
|---|---|
| **Atualizar o site com o código novo** | `cd ~/StreakScrumForest && git pull` e depois **Reload** na aba Web |
| Ver o código que está publicado (último commit) | `cd ~/StreakScrumForest && git log --oneline -3` |
| **Ver o log de erros** (quando o site der erro 500) | `tail -n 50 /var/log/SEUUSUARIO.pythonanywhere.com.error.log` (ou o link *Error log* na aba Web) |
| Ver o log de acessos | `tail -n 30 /var/log/SEUUSUARIO.pythonanywhere.com.access.log` |
| Conferir se o banco está no lugar certo | `ls -la ~/dados` (deve aparecer `strikes.db`) |
| Mover o banco, se subiu na pasta errada | `mv ~/strikes.db ~/dados/strikes.db` |
| Checar a integridade do banco | `sqlite3 ~/dados/strikes.db "PRAGMA integrity_check;"` (deve responder `ok`) |
| Quantos membros e presenças existem | `sqlite3 ~/dados/strikes.db "SELECT COUNT(*) FROM members; SELECT COUNT(*) FROM attendance;"` |
| **Backup agora** | `STRIKES_DB=~/dados/strikes.db ~/venv-jardim/bin/python ~/StreakScrumForest/scripts/backup_db.py` |
| Listar os backups | `ls -la ~/dados/backups` |
| Atualizar as dependências do servidor | `~/venv-jardim/bin/pip install -r ~/StreakScrumForest/requirements.txt` |
| Gerar um `SECRET_KEY` no servidor | `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |

Outras ações no site publicado:

- **Reload:** aba **Web** > botão verde **Reload** (necessário depois de `git pull` ou de mudar o arquivo WSGI).
- **Trocar códigos** (`ACCESS_CODE`, `ADMIN_CODE`, `SECRET_KEY`): aba **Web** > *WSGI configuration file* > editar > salvar > **Reload**.
  Trocar o `SECRET_KEY` ou o `ACCESS_CODE` desloga todo mundo.
- **Baixar uma cópia do banco do servidor:** entre como administrador e abra `https://SEUUSUARIO.pythonanywhere.com/admin/baixar-banco`.
- **Restaurar um backup:** pare o site (aba Web > Disable), copie o backup por cima do banco
  (`cp ~/dados/backups/<arquivo>.db ~/dados/strikes.db`), depois **Enable** e **Reload**.
- **Manter no ar:** a cada ~3 meses, aba **Web** > botão para estender a validade do app gratuito.
- **Nunca** suba o `data/strikes.db` do seu PC por cima do banco do servidor depois que o site estiver em uso.

### Git (no seu computador)

| Para quê | Comando |
|---|---|
| Ver o que mudou | `git status` |
| Ver em qual branch estou | `git branch --show-current` |
| Guardar as mudanças (o banco `data/*.db` já é ignorado) | `git add -A` e depois `git commit -m "mensagem"` |
| Enviar para o GitHub | `git push origin main` (ou o nome da branch) |
| Trazer o que está no GitHub | `git pull` |
| Trocar de branch | `git switch nome-da-branch` |
| Criar uma branch nova | `git switch -c nome-da-branch` |
| Juntar uma branch na `main` (sem commit de merge) | `git switch main` e `git merge --ff-only nome-da-branch` |
| Desfazer mudanças **não commitadas** de um arquivo | `git restore caminho/do/arquivo` (cuidado: apaga a alteração) |

> O banco real (`data/strikes.db`) **não vai mais para o GitHub** (está no `.gitignore`). Faça backup dele à parte.

### Fluxo para publicar uma mudança

1. Mexa no código, rode `python -m unittest discover tests` e teste com o banco de mentira.
2. `git add -A` · `git commit -m "..."` · `git push origin main`.
3. No PythonAnywhere: `cd ~/StreakScrumForest && git pull` e **Reload**.
4. Abra o site publicado e confira (Ctrl + F5).

## Aba Sementes: extrato e "por que a diferença?"

Em **Sementes** (`/sementes`), escolha um nome em "Acompanhar o progresso" (se você entrou no Meu jardim, ela já abre em você):
- **Total ganho, gasto na loja e saldo** de cada pessoa, com **todas** as fontes: presença nos eventos, semanas fechadas, marcos, dia cheio, Floresceu, boas-vindas, **atas preenchidas** e **Scrum (falas de colegas preenchidas)**.
- **Extrato**, ganho por ganho: cada linha traz a **data**, o **motivo** (ex.: "Daily preenchida", "Scrum: preencheu a Daily de colegas — Guilherme, Pablo", "Marco de sequência: 5 dias seguidos", "Compra na loja") e o **saldo acumulado** até ali. O total do extrato é **sempre igual** ao saldo real (há teste para isso).
- **Comparar com outra pessoa**: a tabela "De onde vem a diferença" mostra só as fontes em que os dois diferem (e o gasto na loja), para entender, por exemplo, por que alguém tem menos sementes.

## Quem pode alterar o quê (administrador x visitante)

O site é aberto a quem tem o código de acesso do grupo, mas **só o administrador altera o que é de
todos**. Os demais veem todas as abas (Hoje, Painel, Histórico, Ata, Membros, Calendário...) sem poder
mudar nada.

**Quem é administrador**
- **Quem está no computador onde o sistema roda** (abrindo `http://localhost:5000`). Vale sozinho, sem login.
- **O Scrum (relator) do dia**: quem foi escolhido como relator da ata de hoje e entrou no celular com o PIN
  em **Meu jardim**.
- **Quem entra com o código de administrador** (`ADMIN_CODE`, uma variável de ambiente no servidor): útil quando
  o site está publicado. Link "Sou o admin" no topo. Nunca coloque o código no repositório.

O administrador vê o selo **Administrador** no topo. No servidor publicado, o "computador" não existe (todos
entram de fora), então use o `ADMIN_CODE` ou o Scrum do dia. Para desligar o modo "computador" mesmo em
localhost, defina `ADMIN_LOCAL=0`.

**O que só o administrador faz:** marcar presença/avisou/faltou de qualquer pessoa e "todos presentes",
editar a ata e escolher o relator, mostrar o **QR de presença** (botões na tela Hoje e na Ata), adicionar,
editar, desativar ou excluir membros, resetar PIN, mudar o calendário e os feriados, definir as metas da
sprint e baixar o banco.

**O relator escreve a ata de qualquer aparelho, inclusive de um PC.** Na ata, quem ainda não é o relator vê "Sou o relator: entrar com o PIN" (volta para a ata depois) e, se a ata ainda não tem relator, "Assumir como relator desta ata". O relator de uma ata edita **aquela** ata (de hoje ou de outro dia), sem precisar estar no computador do sistema. Ninguém toma o lugar de outro relator.

**O que cada pessoa faz sozinha (sem ser admin):** marcar a **própria** presença pelo QR, preencher a
**própria** fala da daily em Meu jardim ou pelo QR, e usar a **própria loja** (compra, equipa, desfaz) depois de
entrar com o PIN. O administrador também pode escolher um perfil na Loja e comprar por ele.

## Guia de teste (com banco de demonstração)

Para experimentar o site **sem risco para os dados reais** (`data/strikes.db`), use um banco de
mentira. O passo a passo, a partir da pasta do projeto:

**1. Ative o ambiente virtual**

```powershell
venv\Scripts\Activate.ps1      # PowerShell
```
```cmd
venv\Scripts\activate          :: Prompt (cmd)
```
Se der erro de permissão no PowerShell: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
Para sair: `deactivate`.

**2. Crie o banco de demonstração** (7 pessoas da equipe, 3 convidados, histórico de presenças,
atas de exemplo e o PIN `1234` para a Arthur):

```powershell
python scripts/criar_banco_demo.py C:\temp\jardim-demo.db
```
O script **recusa** gravar em `data/` (o banco real) e só recria um arquivo existente com `--forcar`.

**3. Rode o site apontando para ele**

```powershell
$env:STRIKES_DB = "C:\temp\jardim-demo.db"     # PowerShell
python app.py
```
```cmd
set STRIKES_DB=C:\temp\jardim-demo.db           :: Prompt (cmd)
python app.py
```
Abra [http://localhost:5000](http://localhost:5000). Se esquecer o `STRIKES_DB`, o site usa o banco real:
confira sempre antes de marcar presenças de teste. A variável vale só para aquele terminal.

**4. O que testar** (a data de hoje precisa ser dia letivo para marcar presença; veja Calendário)

| Quero testar | Como |
|---|---|
| Jardim, convidados, tooltips | `/` (Hoje) e `/dashboard`; alterne "Ocultos / Em faixa / No fundo do jardim" |
| Dia cheio e animação | em Hoje, marque todos da equipe presentes (botão "Todos presentes") |
| Aba Sementes e marcos | `/sementes`, `/dashboard` (Próximos marcos) |
| Página pessoal e PIN | `/eu`: entre como Arthur com `1234`, ou crie um PIN para outra pessoa |
| QR de presença | abra `/qr/daily` no computador; escaneie com o celular na mesma Wi-Fi (veja "Acessar de outro aparelho") ou abra a URL mostrada no navegador do celular |
| Ata da daily | `/ata/AAAA-MM-DD/daily` (modo relator), depois "Ver / exportar" e "Copiar para o Google Docs" |
| Ata da sprint | `/ata/sprint/1` |
| Convidados fora do time | em Membros, troque alguém entre equipe e convidado e veja o dia cheio e o jardim coletivo |

**5. Zerar o teste:** apague o arquivo (`del C:\temp\jardim-demo.db`) e rode o passo 2 de novo, ou
use `--forcar`. O banco real não é tocado em nenhum momento.

**6. Rodar os testes automáticos** (já usam um banco temporário próprio, não tocam no real):

```powershell
python -m unittest discover tests
```
Ao fim deve aparecer `OK` (hoje são mais de 600 testes). Detalhes na seção [Testes](#testes).

**7. Testar a integração com o GitLab localmente (de ponta a ponta)**

Aqui você sobe o site **no seu computador**, lê o quadro do GitLab de verdade e empurra os cards
para esse site local — sem tocar na produção. Precisa de duas janelas de terminal.

Antes, configure o arquivo `.env` uma vez (copie o modelo e preencha):
```powershell
copy .env.exemplo .env       # depois edite o .env e preencha os valores abaixo
```
No `.env`, para teste local, deixe assim (o `SYNC_TOKEN` é uma senha que **você inventa**; pode ser
qualquer coisa, só precisa ser a mesma nos dois lugares):
```
GITLAB_URL=https://git.inteli.edu.br
GITLAB_PROJECT=graduacao/2026-2b/t24/g01
GITLAB_TOKEN=glpat-SEU_TOKEN_read_api
SITE_URL_LOCAL=http://localhost:5000
SITE_SYNC_TOKEN=um-segredo-qualquer-para-teste
```

**Janela A — o site local** (com banco de demonstração e o `SYNC_TOKEN` ligado):
```powershell
venv\Scripts\Activate.ps1
python scripts\criar_banco_demo.py C:\temp\jardim-demo.db --forcar
$env:STRIKES_DB = "C:\temp\jardim-demo.db"
$env:SYNC_TOKEN = "um-segredo-qualquer-para-teste"   # o MESMO do SITE_SYNC_TOKEN no .env
python app.py
```
Deixe essa janela rodando. O site fica em [http://localhost:5000](http://localhost:5000).

**Janela B — ler o GitLab e enviar** (abra outro terminal, na mesma pasta):
```powershell
venv\Scripts\Activate.ps1
python scripts\sync_gitlab.py --listar-usuarios   # ve os usuarios do GitLab (so leitura)
python scripts\sync_gitlab.py --simular           # mostra os cards, sem enviar
python scripts\sync_gitlab.py --destino local     # envia para o site da Janela A
```
Deve imprimir algo como `Retrato montado: N linha(s)` e `Enviado. O site guardou N card(s).`

**No navegador** (site local):
- Entre em **Membros** e confira o campo "Usuário no GitLab" de cada pessoa. O envio tenta casar
  sozinho pelo nome; quem não casar, você preenche à mão (use os nomes do `--listar-usuarios`) e
  clica em **Salvar GitLab**.
- Abra a **ata da daily** (`/ata/AAAA-MM-DD/daily`) ou entre em **Meu jardim** (`/eu`, Arthur PIN
  `1234`). Sob **Doing** e no campo **Waiting review** aparecem os chips dos cards; tocar
  acrescenta `#123 título` ao texto.

Se os chips não aparecerem, o diagnóstico é direto (a rota é só leitura, não precisa de login):
```powershell
curl.exe "http://localhost:5000/api/gitlab/cards?member_id=1"
```
- `"ultima_sync": ""` → o envio não chegou (confira `SYNC_TOKEN` igual nos dois lados e se a Janela A está no ar).
- `"configurado": false` → essa pessoa está sem "Usuário no GitLab" (preencha em Membros).
- `"configurado": true` com listas vazias → o usuário mapeado não bate com o responsável dos cards (ajuste em Membros).

Para apontar o mesmo comando para a **produção** depois, troque `--destino local` por
`--destino producao` (exige `SITE_URL_PRODUCAO` no `.env` e o `SYNC_TOKEN` definido no WSGI do
PythonAnywhere, com Reload). O token do GitLab **nunca** vai para o servidor.

## Visual

Jardim noturno em ilustracao plana: paleta verde-floresta com acento lima, tipografia
Bricolage Grotesque (licenca OFL, hospedada em `static/fonts/`, entao funciona offline), logo e
favicon em `static/favicon.svg`. As plantas sao um unico SVG em camadas (`templates/_planta.html`)
que cresce ao vivo ao marcar presenca. No celular a navegacao vira uma barra inferior e cada
membro vira um cartao compacto.

## Jardim vivo (branch `feature/jardim-vivo`)

- **Céu por horário**: o cenário muda com a hora do dia (madrugada, amanhecer, manhã, meio-dia,
  tarde, entardecer e noite), com sol e lua percorrendo o céu. Os estágios seguem o horário das
  aulas: **8h manhã** (a daily), **14h tarde** e **15h45 entardecer**, o "mais tarde" do encerramento;
  antes das 8h é amanhecer (a partir das 5h) e depois das 18h30 é noite. A regra está em `game.periodo_do_dia`
  e se repete em `periodoPorHora` (`static/app.js`), que usa a hora do navegador.
- **A planta muda todo dia**: cada presença avança uma barra até o próximo estágio ("faltam N dias"),
  faz nascer um brotinho no vaso e dá uma leve crescida. Os estágios agora são uniformes (um novo a
  cada ~4 dias; antes o Brotinho durava 7). Todo dia útil as plantas de quem ainda não veio mostram
  um balão de "sede"; ao marcar presença elas são regadas (animação) e o balão some.
- **Foguinho de sequência**: aparece ao lado do nome, com 4 níveis (1-2, 3-6, 7-13 e 14+ dias).
  Fica fraquinho enquanto a pessoa ainda não veio hoje e acende ao marcar presença. Marcos (3, 5, 7,
  10, 14, 20, 30 e 40 dias) ganham confete e aviso. No Painel há o foguinho do time (dias cheios).
- **Semana em chamas**: embaixo de cada planta, cinco marcas (seg a sex) com um foguinho por dia de
  presença, ponto azul para "avisou" e anel pulsando para hoje.

## Sementes e Loja (branch `feature/loja-sementes`)

- **Sementes** (derivadas do histórico, nunca perdem por falta): +1 por evento com presença (daily, dev e encerramento), +3 por
  semana fechada, +1 em "dia cheio" do time (todos presentes), +3/+5/+10/+20 nos marcos de
  sequência de 5/10/20/40 dias e +20 ao florescer. Um membro dedicado (3 eventos todo dia) junta ~265
  no projeto e um típico ~190. Os preços da loja foram dobrados para acompanhar. O balanceamento completo
  está em [docs/BALANCEAMENTO.md](docs/BALANCEAMENTO.md). O saldo só diminui com compras e nunca fica negativo.
- **Loja** (`/loja`): escolha quem você é (fica salvo no navegador) e gaste as sementes em
  espécies de planta (girassol, samambaia, lavanda, cerejeira, bambu, bonsai, jabuticabeira, ipê e
  baobá, que só desbloqueia depois de florescer), vasos, companheiros (joaninha, borboleta,
  vagalume, passarinho, gato), acessórios e plantinhas extras no canteiro (a segunda custa 60 e a
  terceira 110; elas crescem junto da principal, um pouco menores). É só enfeite: não muda o
  crescimento real. Sem login, no esquema de confiança: toda compra aparece em "Minhas compras" e
  pode ser desfeita, devolvendo as sementes.
- **Coleção** (`/album`): todos os itens, com os que faltam em silhueta.
- O catálogo e as regras de compra ficam em `catalog.py` (funções puras, com testes). O banco
  ganhou as tabelas `compras` e `equipados` (criadas sem mexer nos dados existentes).
- O Calendário agora é acessado pela tela **Membros**.

## Coletivo (branch `feature/coletivo`)

Pensado para o dia a dia em Scrum, sem prêmios de brincadeira nem comparação entre pessoas.

- **Metas da Sprint** (Painel): o time cria metas de engajamento para a sprint atual (% de presença
  do time, dias cheios, dias cheios seguidos) ou usa as sugeridas. O progresso é sempre calculado
  da presença, só com os dias que já passaram. As sprints vêm do Calendário (por padrão 5 sprints
  de 2 semanas).
- **Resumo da Sprint** (`/sprint/N`): página pensada para a Sprint Review e a Retro. Mostra
  presença do time, dias cheios, presença por evento (daily, dev e encerramento), metas cumpridas,
  evolução de cada planta na sprint e destaques positivos. O botão "Imprimir ou salvar em PDF" usa
  um estilo próprio para papel.
- **Marcos do jardim**: quando o jardim coletivo chega a 25%, 50%, 75% e 100%, o cenário ganha de
  graça uma fonte, vagalumes extras, chuva de pétalas e uma árvore do time.
- **Bosque da equipe**: quem floresce vira uma árvore fixa no bosque do Painel.
- **Trilha das semanas**: cada semana fechada vira uma florzinha (a semana de largada e semanas
  perdidas ficam neutras, sem punição).
- **Perfil do membro** (`/membro/ID`, clicando no nome): planta, sequência, sementes, trilha das 10
  semanas, calendário de presença (estilo mapa de calor) e conquistas.
- **Resumo da semana** no Painel: presença do time, dias cheios e quantas plantas subiram de estágio.
- A sequência de "dias cheios" do time agora considera só dias com registro (esquecer de marcar um
  dia não quebra a sequência; um dia em que alguém não veio quebra).
- O banco ganhou a tabela `metas_sprint` (criada sem mexer nos dados existentes).

## Deploy gratuito no PythonAnywhere, com código de acesso (branch `feature/deploy`)

O GitHub Pages só serve páginas estáticas e não roda Flask nem grava em SQLite, por isso não serve
para operar a plataforma. O plano gratuito do [PythonAnywhere](https://www.pythonanywhere.com)
roda o Flask como está, com disco persistente (o SQLite continua real) e HTTPS, num endereço
`seuusuario.pythonanywhere.com`. Confira no site do PythonAnywhere os limites atuais do plano
gratuito antes de começar.

**Como o código de acesso funciona**

- Local, sem nada configurado: o site abre normalmente, como sempre.
- Com a variável `ACCESS_CODE` definida: todas as páginas e a API pedem o código na tela
  `/entrar`. Depois de 5 erros seguidos o acesso daquele IP é bloqueado por 10 minutos. A sessão
  dura 30 dias e cai se você trocar o código. `/sair` encerra a sessão.
- O código e o `SECRET_KEY` ficam **só no servidor**, nunca neste repositório nem em conversas.

**O que são os códigos e variáveis (e onde pegar cada um)**

Você **não pega** esses valores em lugar nenhum: você mesmo **inventa** (ou gera) e escreve no arquivo WSGI do
servidor (aba **Web**, link *WSGI configuration file*). Nenhum deles vai para o GitHub nem para conversas.

| Variável | O que é, em linguagem simples | De onde vem |
|---|---|---|
| `ACCESS_CODE` | A "senha do portão": o código que **o grupo todo** digita na tela `/entrar` para ver o site. | Você inventa (uma frase fácil de falar) e combina com o time. |
| `ADMIN_CODE` | A senha **só do administrador**, para mexer no que é de todos (presença de todos, ata, membros, calendário) quando você não está no computador do sistema. Diferente do `ACCESS_CODE`. | Você inventa e não conta para ninguém. |
| `SECRET_KEY` | Um texto longo e aleatório que o servidor usa para **assinar os cookies de login**, para ninguém falsificar um login. Ninguém digita isso. Se trocar, todo mundo é deslogado. | Você gera com `python -c "import secrets; print(secrets.token_urlsafe(48))"` e cola. |
| `STRIKES_DB` | O **caminho do arquivo do banco** no servidor (`/home/SEUUSUARIO/dados/strikes.db`). | É o caminho onde você enviou o arquivo (passo 3). |
| `ADMIN_LOCAL` | Em `0`, nenhum acesso é tratado como "o computador do sistema". Use sempre `0` no servidor. | Fixo: `0`. |
| `COOKIE_SECURE` | Em `1`, o login só trafega por HTTPS. | Fixo: `1`. |
| `TZ` | (Opcional) O fuso do site. Sem ela, o `app.py` usa `America/Sao_Paulo`; o PythonAnywhere roda em UTC, e sem fuso o "hoje" viraria o dia seguinte às 21h. | Deixe sem definir, a não ser que o time mude de fuso. |

**Passo a passo**

1. Crie a conta gratuita no PythonAnywhere (você mesmo, com seu e-mail).
2. Em **Consoles > Bash**, baixe o código e instale as dependências:
   ```bash
   git clone https://github.com/malafisor-arthurloyola/StreakScrumForest.git
   cd StreakScrumForest
   git switch main        # ou a branch que você quiser publicar
   python3 -m venv ~/venv-jardim
   ~/venv-jardim/bin/pip install -r requirements.txt
   mkdir -p ~/dados
   ```
3. **Banco de dados**: ele fica numa pasta fora do repositório (`~/dados`), para o `git pull`
   nunca sobrescrevê-lo. Suba **uma única vez** o seu banco atual: na aba **Files**, **clique na pasta `dados/`** (para ficar dentro dela) e só então use *Upload a file* com o
   `data/strikes.db` do seu computador. Ele precisa ficar em `/home/SEUUSUARIO/dados/strikes.db`; se subir sem entrar na
   pasta, o arquivo cai na pasta inicial: mova com `mv ~/strikes.db ~/dados/strikes.db` no Bash.
   Nunca suba de novo por cima depois que o site estiver em uso.
4. Na aba **Web**, clique em *Add a new web app* e escolha *Manual configuration* (Python 3.10 ou
   mais novo). Em *Virtualenv*, informe `/home/SEUUSUARIO/venv-jardim`.
5. Ainda na aba **Web**, abra o *WSGI configuration file* e substitua todo o conteúdo por:
   ```python
   import os, sys

   sys.path.insert(0, "/home/SEUUSUARIO/StreakScrumForest")
   os.environ["STRIKES_DB"] = "/home/SEUUSUARIO/dados/strikes.db"
   os.environ["ACCESS_CODE"] = "escolha-um-codigo-que-o-grupo-saiba"
   os.environ["SECRET_KEY"] = "um-texto-aleatorio-bem-longo-so-seu"
   os.environ["ADMIN_CODE"] = "codigo-so-do-administrador-diferente-do-acesso"
   os.environ["ADMIN_LOCAL"] = "0"
   os.environ["COOKIE_SECURE"] = "1"

   from wsgi import application
   ```
6. Clique em **Reload**. Abra `https://SEUUSUARIO.pythonanywhere.com`: deve aparecer a tela de código.
7. **Atualizar o site depois**: no Bash, `cd ~/StreakScrumForest && git pull`, e **Reload** na aba Web.
8. **Backup diário**: na aba **Tasks**, crie uma tarefa diária com o comando
   ```bash
   STRIKES_DB=/home/SEUUSUARIO/dados/strikes.db /home/SEUUSUARIO/venv-jardim/bin/python /home/SEUUSUARIO/StreakScrumForest/scripts/backup_db.py
   ```
   Ela guarda os últimos 14 dias em `~/dados/backups/`. Para baixar uma cópia do banco a qualquer
   momento (logado), abra `/admin/baixar-banco`. Para restaurar, pare o site, copie o backup
   desejado por cima de `~/dados/strikes.db` e dê Reload.
9. **Manter no ar**: contas gratuitas pedem que, de tempos em tempos (a cada ~3 meses), você entre na
   aba **Web** e clique no botão para estender a validade do app.

**Administrador no site publicado:** quem não está no computador do sistema só altera o que é de todos se
for o **Scrum do dia** (relator, entrando em *Meu jardim* com o PIN) ou entrar com o `ADMIN_CODE` (link
"Sou o admin" no topo). Use um `ADMIN_CODE` **diferente** do `ACCESS_CODE` e só passe para quem vai
administrar. `ADMIN_LOCAL=0` garante que nenhum acesso seja tratado como "o computador". Veja a seção
[Quem pode alterar o quê](#quem-pode-alterar-o-quê-administrador-x-visitante).

**O banco não vai mais para o GitHub:** `data/*.db` está no `.gitignore` (o banco tem nomes, presenças e os
PINs em hash). Suba o banco só pela aba Files, como no passo 3, e nunca o publique.

**Trocar o código de acesso**: edite o `ACCESS_CODE` no arquivo WSGI e dê Reload; quem estava logado
precisa entrar de novo.

**Sobre o banco no GitHub**: o `data/strikes.db` do repositório é só um retrato de um momento. Em
produção, os dados vivos ficam em `~/dados/strikes.db` no servidor. Se você continuar rodando o
site também no seu computador, as duas bases vão divergir.

## Panorama do grupo e novas plantas (branch `feature/panorama-especies`)

- **Panorama do grupo** na tela Hoje (botao "Panorama do grupo"): visao estilo GitHub do projeto todo, da sprint ou da semana, com mapa de calor do time (cada quadrado e um dia; clique para abrir o dia) e uma linha por pessoa (clique no nome para ver o membro).
- **Destaques corrigidos**: em caso de empate, todo mundo que empatou aparece ("Bruno e Heloisa", "Todo o time").
- **Plantas com desenho proprio**: cacto, cogumelo, planta carnivora (armadilhas que abrem e fecham), girassol, samambaia, lavanda, bambu, bonsai, cerejeira, jabuticabeira, ipe e baoba. Cacto, cogumelo e carnivora sao novas na Loja.

## Sementes, dia cheio e Fundador (branch `feature/sementes-e-dia-cheio`)

- **Bug do dia cheio corrigido**: ao marcar a última presença que fecha o dia (todos presentes, ninguém faltou), o contador de sementes de **todos** os membros sobe +1 na hora, não só o de quem foi marcado. A resposta de `/api/attendance` agora traz as sementes de todos os ativos e o estado de dia cheio.
- **Celebração de dia cheio**: quando o dia passa de "não cheio" para "cheio" enquanto você usa a tela Hoje, aparece uma chuva de pétalas com "Dia cheio! +1 semente para todos". Some sozinha em ~3,5s, dispensa com clique ou Esc, não repete na mesma sessão e respeita `prefers-reduced-motion` (nesse caso, só um aviso discreto). Nunca dispara ao recarregar a página.
- **Aba Sementes** (`/sementes`): explica de forma visual todas as fontes de sementes (eventos, semana fechada, dia cheio, marcos de sequência, floresceu e boas-vindas), com os valores lidos das constantes de `game.py` (nunca duplicados no HTML). Tem a seção "a sequência não multiplica" e, se você escolheu quem é na Loja, mostra seu progresso (sequência, próximo marco e quanto rendeu cada fonte).
- **Card "Próximos marcos" no Painel**: cada pessoa em ordem alfabética, com a barra até o próximo marco de sequência (ex.: "8 de 10 dias, +5 sementes"). Só destaque positivo; leva para a aba Sementes.
- **Boas-vindas (+20)**: bônus único na primeira presença registrada de cada pessoa. Os totais do projeto passam a: dedicado 285, típico 211, só daily 195 (ver `docs/BALANCEAMENTO.md`).
- **Selo/acessório Fundador**: quem teve presença em qualquer dia até a data `fundador_ate` (padrão 23/10/2026, editável na tela Calendário) ganha o selo exclusivo "Fundador", visível no perfil e no álbum e equipável no vaso. É só cosmético, não está à venda e não muda nenhum total de sementes.

## Membros convidados (branch `feature/membros-convidados`)

Pessoas de fora do time podem participar do jardim sem entrar nas contas da equipe.

- **Tipo do membro**: cada pessoa é `equipe` ou `convidado` (coluna nova `members.tipo`, default `equipe`, migração aditiva e idempotente). Na tela Membros dá para escolher o tipo ao criar e trocar depois ("Tornar convidado" / "Tornar equipe").
- **Convidado tem jogo próprio**: planta, loja, sementes, sequência e perfil funcionam igual para convidados (inclusive as boas-vindas).
- **Convidado fica fora de tudo que é do time**: dia cheio, progresso do jardim coletivo, metas da sprint, destaques, panorama do grupo (inclusive o denominador do mapa de calor), trilha e bosque e o resumo da sprint. A separação é centralizada: tudo coletivo usa só a equipe (`tipo = 'equipe'`).
- **Onde aparecem**: na tela Hoje, os convidados ficam numa seção "Convidados" separada (marcam presença normalmente) e no jardim há 3 modos, escolhidos acima da cena e lembrados no navegador: **No fundo do jardim** (padrão: plantas pequenas atrás do time, nas frestas entre os vasos), **Em faixa** (faixa própria sob o jardim, com a sequência e o foguinho de cada um) ou **Ocultos**. Ao passar o mouse (ou tocar, no celular) num convidado sobe um cartão com sequência, estágio e sementes e o link para o perfil (`/membro/ID`, que mostra a nota "convidado"). O jardim também ganhou colinas altas com pinheiros e árvores, flores, cerca de madeira ao fundo, terra com pedrinhas, borda de canteiro em madeira e placas discretas de madeira escura com textura bem leve com nome, sequência e estágio. No modo "no fundo", os convidados ficam num terraço verde atrás do time, cada um com uma plaquinha de nome. Posição: primeiro centralizados na fileira, depois em ordem alfabética, ocupando frestas consecutivas entre os vasos do time.
- **Exemplo**: com 7 de equipe e 2 convidados, um dia com os 7 presentes (e os convidados ausentes) continua sendo "dia cheio"; adicionar ou reclassificar um convidado não muda o progresso coletivo nem as metas.

## Celular pessoal, PIN e QR de presença (branch `feature/acesso-pessoal`)

Cada pessoa passa a ter uma página pessoal no celular e pode marcar presença escaneando um QR.

- **Página pessoal (`/eu`)**: feita para o celular (mobile-first, alvos de toque grandes). Mostra a planta, as sementes, o progresso (sequência, dias presentes, próximo estágio) e a Loja para comprar e equipar. Convidados também entram e têm a página igual.
- **Login por PIN**: no primeiro acesso a pessoa escolhe o nome e cria um PIN de 4 dígitos; depois entra com nome + PIN. O aparelho lembra por 30 dias (cookie de sessão assinado, HttpOnly, SameSite=Lax). O PIN é guardado só como hash com sal (scrypt da stdlib), nunca em texto. Há limite de tentativas: 5 erros bloqueiam por 10 minutos, por IP e por membro. O PIN protege contra um colega marcar presença ou gastar sementes no nome de outro (o site já é protegido pelo código de acesso do grupo).
- **Reset de PIN**: na tela Membros, o dono pode resetar o PIN de alguém (a pessoa cria um novo no próximo acesso). Um selo "PIN ✓" mostra quem já tem PIN.
- **QR de presença (`/qr/<evento>`)**: o dono/relator abre `/qr/daily`, `/qr/dev` ou `/qr/encerramento`: a tela mostra a **data por extenso** em destaque, o nome do evento e um QR grande (Python puro, sem biblioteca externa). Quem escaneia cai em `/presenca/<evento>/<código>`, que mostra de novo a data e oferece **duas opções**: **"Marcar presença"** (só a presença) ou **"Marcar e preencher a Daily (+1 semente)"**, que abre dois campos (o que fez / o que vai fazer) e já grava a fala na ata, com a presença. Quem já estava marcado ainda pode preencher a fala depois. O Dev não tem ata, então só marca presença. Só marca o próprio membro, só hoje, e nunca marca "faltou".
- **Código que expira**: o código é um HMAC de `SECRET_KEY` sobre `data|evento|janela de 10 min`. Vale a janela atual e a anterior (para não "virar" na troca de janela) — depois disso expira. Código de outro evento ou de outro dia não funciona. A tela do QR se atualiza sozinha para o código não expirar enquanto está aberta.
- **Convidados**: entram na página pessoal e no QR normalmente; a presença por QR vale para eles, mas continua fora de todas as métricas do time.

O gerador de QR é próprio (`qr_puro.py`): modo byte, correção de erro nível M, Reed-Solomon, máscaras e SVG. Não foi preciso adicionar nenhuma dependência (o `requirements.txt` não muda).

## Ata da daily (branch `feature/acesso-pessoal`, sobre a Fase 3)

Substitui o Google Docs: a ata da daily e do fechamento do dia, pronta para entregar à professora.

- **Dois documentos por dia**, mapeados nos eventos: `daily` → **Daily** e o encerramento → **Day Closing** (`fechamento`). A tela é em português; a exportação sai em **inglês por padrão** (config `idioma_ata`, com opção `pt` — muda na tela Calendário).
- **Modo relator** (`/ata/<data>/<tipo>`): escolha o **relator (Scrum)** nos botões do topo (um toque marca, outro desmarca). A tela lista **todos os membros da equipe** (convidados ficam de fora), cada um com os botões **Presente** e **Avisou** e os campos de fala. **Relatar a fala de alguém já marca essa pessoa como presente** no evento da ata (Daily → `daily`, Day Closing → `encerramento`), a menos que ela tenha avisado. O `Present:` do documento é de quem está presente naquele evento, e quem avisou sai numa linha `Excused:`. A tela **atualiza sozinha** a cada poucos segundos: quem marca presença ou preenche a própria fala pelo celular aparece ali sem recarregar. Salva sozinho enquanto digita. Em "Done" há um botão opcional "usar o que ficou planejado ontem".
- **Fala própria no celular**: em `/eu`, quem está logado vê "Minha fala de hoje" e escreve a própria parte (Done/Doing). O relator vê o que já veio preenchido e completa. Ninguém é obrigado.
- **Rodada de fala (tela Hoje)**: serve para a **Daily** e para a **Day Closing** (escolha no seletor; depois das 15h45 abre na Day Closing, que tem só dois campos: o que concluí hoje e o que fica para amanhã). Na tela Hoje, o Scrum clica em *Sortear a ordem e começar*. A cada pessoa, a planta dela acende, o resto da tela escurece e aparece um painel com os três campos da daily (o que fiz de ontem para hoje, o que vou fazer hoje, cards aguardando revisão) com os cards sugeridos do GitLab. Por padrão a pessoa preenche no próprio celular (logada em Meu jardim) e todos veem o texto aparecer; o Scrum pode clicar em *Preencher por ela(e)* e escrever por ela, e então vale o bônus de relator (a pessoa ganha a semente da fala do mesmo jeito). Quem não está presente pode ser marcado como Presente, Avisou ou Faltou ali mesmo. A rodada também abre num dia que já passou, para fazer a ata daquele dia. O painel mostra para todos a posição e quem vem a seguir; a ordem sorteada fica no servidor, então outro aparelho do Scrum continua a mesma rodada. O QR e a ata continuam funcionando. O holofote se apaga ao encerrar ou sozinho depois de 3 horas.
- **Metas com recompensa** (Dashboard, seção "Metas com recompensa"): o administrador cria um combinado do time (ex.: "entregar o canvas e o backlog"), com **prazo**, **sementes** (1 a 30) e **quem recebe**: o time inteiro ou pessoas específicas. Quando o grupo entrega, o admin clica em **"Marcar como cumprida"** (a data de entrega é a de hoje; dá para reabrir). Só rende se a entrega for **até o prazo** (inclusive); depois disso aparece "Fora do prazo" e ninguém ganha nem perde nada. As sementes entram no saldo, na aba Sementes (linha "Meta cumprida" no extrato) e na comparação entre pessoas. Meta do time vale para toda a equipe (convidados ficam de fora).
- **Cards `#123`**: viram etiqueta no texto; não exigem nem geram link (config opcional `gitlab_base_url`; a integração real com o GitLab fica fora de escopo).
- **Impedimentos**: texto livre por ata, aparecem no relatório até serem marcados como resolvidos (lista "Blockers abertos/resolvidos" na ata da sprint). Impedimento **nunca rende semente**.
- **Recompensa (adubo)**: +1 semente por pessoa por ata (Daily e Day Closing) em que a fala esteja preenchida (feito ou planejado), sem avaliar conteúdo nem tamanho — máximo +2 por dia. O **relator (Scrum) ganha +1 por cada fala de outra pessoa que preenche** (por pessoa e por ata, **no máximo 3 por ata**); a fala dele mesmo rende o +1 normal; fala que a própria pessoa escreveu no celular não dá bônus ao relator. A planta fica "adubada" (brilho e flores extras), só visual. Dedicado passa de 285 para ~375 (ver `docs/BALANCEAMENTO.md`).
- **Exportação**: página imprimível (`/ata/<data>/<tipo>/imprimir`, com `@media print` para salvar em PDF) e botão **"Copiar para o Google Docs"** (copia HTML + texto puro no modelo exato, com `Present:` automático).
- **Ata da sprint** (`/ata/sprint/<n>`, linkada do Resumo da Sprint): todas as dailies e fechamentos da sprint em ordem, os cards citados agrupados, os impedimentos abertos e resolvidos e o panorama de presença — para a Review e a Retro.

A formatação fica em `ata_fmt.py` (módulo puro e testável): rótulos exatos em EN/pt, `Present:` automático, "None" quando vazio e as etiquetas de card.

## Preencher a daily sem atrito (branch `feature/daily-melhor`)

Ajustes para tornar o preenchimento da daily mais fácil (nenhuma regra de semente muda).

- **Presença e fala em sequência**: na tela de presença (`/presenca/<evento>/<código>`), depois de **"Marcar presença"** a tela **não some** — mostra "Presença registrada" e **mantém** o botão/formulário "Preencher a Daily" para a pessoa preencher na hora ou voltar depois (pelo mesmo QR ou por "Meu jardim"). Salvar a fala também garante a presença. No Dev (sem ata), só presença.
- **Cada um edita a própria linha na ata**: em `/ata/<data>/<tipo>`, quem está logado com o PIN e **não** é relator/admin vê **só a sua própria linha** editável (destacada, com o selo "você"); as demais ficam só de leitura. Isso salva por `POST /api/ata/minha-fala` (que valida que é a própria pessoa); o `POST /api/ata/salvar` continua **403** para quem não é relator/admin. O auto-salvar (pausa de 1,2 s + ao sair do campo) e a atualização automática a cada 4 s continuam valendo, sem sobrescrever o que você está digitando.
- **Quanto rende, sem promessa falsa**: na tela de presença e em "Minha fala" há um bloco **"Quanto rende"** lido das constantes de `game.py` (nunca número fixo no HTML): "Marcar presença +N", "Preencher a Daily/Day Closing +M", "juntos +(N+M) hoje". Depois de salvar, aparece o que foi ganho de fato ("Você ganhou +1 pela presença e +1 pela fala"). Editar a fala **não** rende de novo e apagar todo o texto remove o bônus (é derivado) — dito em uma linha discreta.

## Integração com o GitLab (branch `feature/gitlab`)

Sugere, na daily, os cards de cada pessoa que estão em **Doing** e em **Waiting review**, como chips tocáveis que você acrescenta à sua fala com um toque. É **só leitura**: o site nunca escreve no GitLab, e os cards **não rendem semente** (continua valendo só preencher a fala; a revisão não conta).

### Por que um script no seu computador?
O GitLab é o da faculdade e o site roda no PythonAnywhere grátis, que **não alcança** a rede da faculdade. Então a ponte é feita por você: um script lê o GitLab com o **seu** token pessoal e **empurra** um retrato pronto do quadro para o site. O token do GitLab **fica no seu computador** — nunca vai para o servidor, para o repositório, nem aparece em mensagens. O único segredo que o servidor guarda é o `SYNC_TOKEN` (um segredo combinado, definido como variável de ambiente no WSGI). Sem `SYNC_TOKEN` configurado, o endpoint de recebimento simplesmente não existe (ninguém consegue empurrar dados).

### No servidor (uma vez)
Defina a variável `SYNC_TOKEN` no WSGI/ambiente do PythonAnywhere com um segredo forte à sua escolha (o mesmo que o script vai usar). Não coloque esse valor no repositório.

### No seu computador
1. No GitLab, crie um **token de acesso pessoal** com escopo de **leitura** (`read_api`).
2. Descubra o **Project ID** (aparece na página inicial do projeto, em "Project ID").
3. Defina as variáveis (PowerShell):
   ```powershell
   $env:GITLAB_URL      = "https://gitlab.suafaculdade.br"
   $env:GITLAB_PROJECT  = "123"              # o Project ID
   $env:GITLAB_TOKEN    = "<seu token read_api>"
   $env:SITE_URL_PRODUCAO = "https://suaconta.pythonanywhere.com"   # o site publicado
   $env:SITE_URL_LOCAL    = "http://localhost:5000"                  # (opcional) o site no seu computador
   $env:SITE_SYNC_TOKEN   = "<o mesmo SYNC_TOKEN do servidor>"
   ```
   O mais confortável é colocar tudo num arquivo `.env` na pasta do projeto (copie o `.env.exemplo`): o script o lê sozinho e ele **nunca** é versionado.
   (no `cmd` use `set NOME=valor`). As labels do quadro podem ser trocadas, sem diferenciar maiúsculas/minúsculas, com `GITLAB_LABEL_DOING` (padrão `Doing`) e `GITLAB_LABEL_REVIEW` (padrão `Waiting review`).
4. Rode:
   ```powershell
   python scripts/sync_gitlab.py                 # lê o GitLab e empurra para o site (o publicado, se houver)
   python scripts/sync_gitlab.py --destino producao   # só para o site publicado
   python scripts/sync_gitlab.py --destino local      # só para o site no seu computador
   python scripts/sync_gitlab.py --destino ambos      # para os dois (se um falhar, o outro continua)
   python scripts/sync_gitlab.py --simular       # mostra o que enviaria, sem enviar
   python scripts/sync_gitlab.py --listar-usuarios  # lista os responsáveis (para mapear no site)
   python scripts/sync_gitlab.py --arquivo q.json   # lê de um arquivo, para testar sem rede
   ```
5. Para manter atualizado, agende o `python scripts/sync_gitlab.py` no **Agendador de Tarefas** do Windows (ex.: a cada 15 min, durante o horário do time).

### Quem é quem no GitLab (automático)
O script também lê os **membros do projeto** (usuário e nome) pela API e os envia junto. O site **liga sozinho** cada pessoa ao usuário dela quando o nome bate: nome igual, ou o nome da pessoa dentro do nome do GitLab (ex.: "Arthur" em "Arthur Loyola"), ou o usuário contendo o nome. Sem chute: se houver dúvida (dois "Ana"), ele não liga e você escolhe. Ele **nunca sobrescreve** o que você já definiu e nunca dá o mesmo usuário a duas pessoas. Se o seu token não puder listar membros, o script avisa e você preenche à mão.

### Na tela de Membros (admin)
O campo **"Usuário no GitLab"** de cada pessoa aparece **já preenchido** quando o casamento automático acertou; ao digitar nos demais, o campo sugere os usuários do projeto. Quem continua sem usuário ganha um aviso discreto "sem GitLab" — os cards dele simplesmente não aparecem, nada quebra.

### Só os cards da sprint atual (milestone)
Os chips de **Waiting review**, **Review** e **fechados** mostram só os cards da **milestone da sprint de hoje** (por exemplo, "Sprint 02") e **mudam sozinhos** quando a sprint muda, sem rodar nada de novo. O site descobre a milestone atual assim: a que tem hoje entre a data de início e a de fim (as datas vêm do GitLab); se hoje cair numa folga entre duas sprints, a última que começou; e, se as milestones não tiverem datas, a que tem o mesmo número da sprint do calendário ("Sprint 02" = sprint 2). Cards **sem milestone** ficam de fora quando existem milestones no quadro. **Doing** e **Backlog** não dependem da milestone (o que você vai fazer ou pegar não muda de sprint). O cabeçalho mostra "… revisão e fechados da Sprint 02". Para isso o script também envia a milestone de cada card: depois de atualizar o site, rode `python scripts/sync_gitlab.py --destino producao` uma vez.

### Links dos cards na exportação
Na exportação da ata (e na página imprimível/"Copiar para o Google Docs"), cada `#52` vira link para o card **exato** no GitLab (ex.: `https://git.inteli.edu.br/grupo/projeto/-/issues/52`). O site usa a URL que o próprio GitLab informou para cada card; para um número que não está no quadro, usa a base do projeto, que o script envia e se **corrige a cada envio**. Se algum link antigo sair errado, rode `python scripts/sync_gitlab.py --destino producao` uma vez.

### Cards também no Day Closing
O **Day Closing** (ata e Meu jardim) tem os mesmos chips e buscas: em **Concluí hoje** aparecem seus cards em Doing, em revisão e fechados (mais a busca em Waiting review/Review/fechados da sprint), e em **Ficou para depois** aparecem seus cards em Doing e a busca no **Backlog**. O campo "Vou revisar" continua só na Daily.

### Pesquisar cards
- **O que fiz** e **Vou revisar** têm uma caixa **"buscar card"** (na ata, em Meu jardim e na tela de presença): digite o **número** ou parte do **título** e toque no resultado para acrescentá-lo ao texto. A busca olha os cards em **Waiting review, Review e fechados** da **sprint atual**. **Exceção:** se você digitar um **número exato** (ex.: `#42`), o card aparece mesmo que seja de outra sprint, para registrar algo que ficou para trás.
- **O que vou fazer hoje** continua com a busca no **Backlog**.

### Como aparece
- Na daily (ata e "Minha fala"), sob **Doing** e no novo campo **Waiting review**, aparecem os chips `#123 título`. Tocar acrescenta ao texto (nunca sobrescreve, não duplica) e você pode digitar livre do mesmo jeito.
- Um cabeçalho discreto mostra **"GitLab: atualizado às HH:MM"**, ou "ainda não sincronizado", ou "dados antigos" se a última sincronização foi há mais de um dia. Se o GitLab estiver fora, **nada é bloqueado**.
- Na exportação da ata, a seção **"Waiting review"** (ou "Em revisão", em português) só aparece **se alguém tiver escrito algo ali** — sem isso, o documento fica idêntico ao modelo de sempre.

O que casa os cards (de issues para a lista enviada) fica em `gitlab_sync.py` (módulo puro e testável: um responsável por linha, labels sem diferenciar maiúsculas, um card pode estar em Doing e em Waiting review). O `scripts/sync_gitlab.py` e o site usam o mesmo módulo. **Fora de escopo:** semente por card/commit/merge request e escrever qualquer coisa no GitLab.

### Campos da daily repensados (branch `feature/gitlab-daily`)

A daily passou a ter **três campos em português**, cada um com uma bolinha **"i"** de ajuda (toque ou passe o mouse) e com chips de card conforme a coluna do quadro:

- **O que fiz**: sugere os seus cards em **Waiting review**, **Review** e os **fechados (Closed) nos últimos dias** — porque "concluí" normalmente é mandar para revisão ou fechar. (Guarda em `feito`.)
- **O que vou fazer hoje**: sugere os seus cards em **Doing** e tem uma caixa **"buscar no Backlog"** (digite número ou parte do título para puxar um card). (Guarda em `planejado`.)
- **Vou revisar**: mostra **todos** os cards do quadro em **Waiting review + Review** (de qualquer pessoa) e você toca nos que vai revisar — quem revisa não é o responsável do card, então não dá para adivinhar. (Guarda em `review` e **não rende semente**.)

Novas variáveis (opcionais) para o script, além de `GITLAB_LABEL_DOING`/`GITLAB_LABEL_REVIEW`:

| Variável | O que é | Padrão |
|---|---|---|
| `GITLAB_LABEL_REVIEW_EM` | label da coluna "Review" do quadro (quem está revisando) | `Review` |
| `GITLAB_LABEL_BACKLOG` | label da coluna "Backlog" | `Backlog` |
| `GITLAB_DIAS_FECHADOS` | quantos dias de cards **fechados** sugerir em "O que fiz" | `5` |

A **exportação** agora abre **em português por padrão** (com o botão para ver em inglês). Em um site que já existia, o idioma fica guardado como estava; para ver o português primeiro, troque uma vez na tela **Calendário**. A seção **"Em revisão"** (ou "Waiting review", em inglês) só aparece no documento **se alguém escreveu algo** em "Vou revisar" — sem isso, o documento fica idêntico ao modelo de sempre.

A regra de semente **não mudou**: só "O que fiz" e "O que vou fazer" (os antigos `feito`/`planejado`) rendem o adubo; "Vou revisar" nunca conta. Os rótulos na tela mudaram, as fontes de semente não.

## Como testar uma branch (`feature/deploy`, `feature/coletivo`, `feature/loja-sementes`, `feature/jardim-vivo` ou `redesign/visual`)

Use sempre uma **cópia** do banco para não alterar os dados reais do grupo.

1. Traga a branch e troque para ela (a partir da pasta do projeto):
   ```bash
   git fetch origin
   git switch feature/deploy
   ```
2. Se ainda não instalou as dependências:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Aponte o app para uma cópia do banco e rode:
   - PowerShell:
     ```powershell
     Copy-Item data\strikes.db $env:TEMP\strikes-teste.db
     $env:STRIKES_DB = "$env:TEMP\strikes-teste.db"
     python app.py
     ```
   - cmd:
     ```bash
     copy data\strikes.db %TEMP%\strikes-teste.db
     set STRIKES_DB=%TEMP%\strikes-teste.db
     python app.py
     ```
4. Abra [http://localhost:5000](http://localhost:5000) e confira: tela Hoje (marque Presente, Avisou e
   Faltou e veja a planta crescer), Painel, Histórico, Membros e Calendário. No celular, use o IP do
   notebook (`ipconfig`) com a porta 5000, ou o modo celular do navegador (F12).
5. Para rodar os testes automatizados: `python -m unittest discover tests`.
6. Para voltar ao normal: pare o servidor (Ctrl+C) e rode `git switch main`. A cópia em `%TEMP%` pode
   ser apagada.

Se você rodar o app **sem** `STRIKES_DB`, ele usa `data/strikes.db` (o banco real versionado) e pode
alterá-lo. Nesse caso, desfaça com `git checkout -- data/strikes.db`.

## Variavel de ambiente STRIKES_DB

Para rodar contra um banco diferente do real (recomendado para testes):

```bash
set STRIKES_DB=C:\caminho\para\outro\strikes.db
python app.py
```

O `BACKUP_DIR` fica automaticamente ao lado do banco apontado por `STRIKES_DB`.

## Acessar de outro aparelho (celular) na mesma rede

O servidor sobe em `0.0.0.0`. Descubra o IP local com `ipconfig` e acesse
`http://SEU_IP:5000` de qualquer dispositivo na mesma rede.

## Backups automaticos

- A cada inicializacao do servidor, se o banco ja existir, uma copia e salva em
  `data/backups/strikes-AAAA-MM-DD.db` (no maximo 1 por dia).
- Antes da migracao do schema (ao adicionar `justificada`): `strikes-pre-migracao-AAAA-MM-DD.db`.
- Antes de excluir um membro: `strikes-pre-exclusao-AAAA-MM-DD.db`.

Para restaurar: feche o servidor, copie o backup desejado para `data/strikes.db` e suba de novo.

## Como funciona

### Telas

- **Hoje** (`/`): faixa de jardim com plantas dos membros ativos; **rodada de fala** da Daily e da Day Closing (so o Scrum/admin, no dia de hoje); tabela de presenca com tres botoes
  por evento (Presente / Avisou / Faltou); coluna de sequencia atual. Navega por datas. Aviso visual
  quando o dia nao e letivo (feriado, fim de semana, fora do periodo).
- **Historico** (`/historico`): lista todos os dias registrados com faltas, justificadas e numero
  de membros com algum registro.
- **Dashboard** (`/dashboard`): jardim grande com todas as plantas, progresso coletivo, tendencia de
  presenca, dias presentes por membro, destaques positivos (maior sequencia, mais dias presentes).
- **Membros** (`/membros`): cadastra, renomeia, desativa ou exclui membros. Exclui com confirmacao
  obrigatoria digitando o nome.
- **Calendario** (`/calendario`): edita periodo do projeto (inicio, numero de semanas, sprint, contar
  a partir de), adiciona/remove feriados. Mudar aqui recalcula tudo automaticamente.

### Regras do jogo (Jardim)

Cada membro tem uma planta que cresce conforme sua presenca:

- **Presente**: +1 ponto de crescimento (G), +1 na sequencia atual.
- **Avisou** (justificada): neutro. Nao quebra a sequencia, nao soma nem desconta crescimento.
- **Faltou**: -2 pontos de crescimento (G), zera a sequencia.
- **Pendente** (sem marcacao no dia): ignorado.

**Meta de floracao**: `ceil(80% dos dias letivos)`. Com 45 dias letivos, meta = 36 presenças.

**Estagios** (0 a 10): Semente, Brotinho, Muda, Folhinhas, Jovem, Crescendo, Vicosa, Botoes, Florindo,
Frutificando, Floresceu. Estagio 1 com o primeiro dia presente. Estagio 10 (Floresceu) e permanente.

**Piso protegido**: uma falta nunca derruba a planta abaixo do inicio do estagio que ela ja alcancou.

**Vigor** (copa viva pela sequencia): murcha (0 dias), verde (1-2), vicosa (3-4), florida (5-9),
radiante (10+). Murchar e reversivel imediatamente.

**Frutos pos-floracao**: a cada 5 presenças alem da meta, 1 fruto na planta (ate 5).

### Regra da sequencia — mudanca em relacao a versao anterior

A sequencia agora conta dias com **pelo menos uma presença** (e sem falta). Antes contava dias sem
nenhuma falta, independente do registro. Ao atualizar, o calculo das sequencias de dias anteriores
pode mudar para membros que tinham dias com presença em um evento e falta em outro no mesmo dia.

### Status "Avisou" (justificada)

Significa "ausente, mas avisou". Clique em "Avisou" em vez de "Faltou". Efeito: neutro para o jogo
(zero para o crescimento, nao quebra a sequencia). Clicar no mesmo botao ativo volta ao pendente.

### Excluir membro

Em Membros, clique em "Excluir", confirme digitando o nome exato. A exclusao e **definitiva e
irreversivel**: remove o membro e todos os seus registros de presenca. Um backup e salvo antes.
"Desativar" e a alternativa reversivel (historico mantido, membro some da tela Hoje).

### Calendario e feriados

Em Calendario voce define:
- Inicio da semana 1, numero de semanas (padrão: 10 semanas, de 12/10 a 18/12/2026).
- Sprint em semanas (padrão: 2 semanas).
- Contar a partir de (padrão: 15/10/2026, primeiro dia real de uso).
- Feriados (padrão: 12/10 N.Sra.Aparecida, 02/11 Finados, 20/11 Consciencia Negra).

**Confirme os defaults com o time.** Mudar o calendario recalcula tudo sem migracao.

## Testes

Antes de tudo, **ative o ambiente virtual** (a partir da pasta do projeto):

```powershell
venv\Scripts\Activate.ps1      # PowerShell
venv\Scripts\activate          # Prompt (cmd)
```

Depois rode a suíte. **Sempre aponte `STRIKES_DB` para um arquivo de teste** para não tocar no banco
real — os testes criam e apagam dados:

```powershell
# PowerShell
$env:STRIKES_DB = "$env:TEMP\strikes-teste.db"
python -m unittest discover tests
```

```cmd
:: Prompt (cmd)
set STRIKES_DB=%TEMP%\strikes-teste.db
python -m unittest discover tests
```

```bash
# Linux/macOS (ou WSL)
STRIKES_DB=/tmp/strikes-teste.db python -m unittest discover tests
```

Sem ativar o venv, use o Python dele direto: `venv\Scripts\python -m unittest discover tests`.
Ao fim deve aparecer algo como `Ran 611 tests ... OK`.

> Para **testar o site no navegador** sem risco, use o mesmo truque: defina `STRIKES_DB` para uma
> cópia antes de `python app.py`. Sem isso, o app usa o banco real (`data/strikes.db`).
> ```powershell
> $env:STRIKES_DB = "C:\temp\jardim-teste.db"
> python app.py
> ```

## Estrutura do projeto

```
app.py                  # backend Flask: rotas, migracoes, papeis, ata, loja, holofote
game.py                 # regras do jogo (puras, testaveis, sem Flask): estagios, sequencia, sementes, metas
catalog.py              # catalogo da loja (especies, vasos, companheiros, acessorios, plantas extras)
ata_fmt.py              # exportacao da ata (texto e HTML, pt e en)
gitlab_sync.py          # regras do retrato do GitLab (milestone atual, mapeamento de usuarios)
qr_puro.py              # gerador de QR em Python puro
backup.py               # backups diarios do banco
wsgi.py                 # entrada para o PythonAnywhere
data/                   # banco SQLite e backups (nunca vao para o git)
docs/
  GDD.md                # Game Design Document (com stack e diagramas)
  PROCESSO.md           # relato do processo, patch notes e problemas
  img/                  # capturas de tela do GDD
  BALANCEAMENTO.md      # contas das sementes e dos precos
  HANDOFF-KIRO*.md      # notas de passagem entre agentes
scripts/
  gerar_especies.py     # gera as especies desenhadas em SVG (templates/_especies.html)
  sync_gitlab.py        # envia o retrato do GitLab para o site
  criar_banco_demo.py   # banco de demonstracao para testar sem tocar no real
  backup_db.py          # backup manual
templates/              # paginas (Jinja) e macros de planta, cena e especies
static/
  style.css             # estilos (tema escuro)
  app.js                # marcacao de presenca, jogo na tela, toasts, convidados
  holofote.js           # holofote e painel da rodada de fala (todas as telas)
  rodada.js             # controle da rodada de fala na tela Hoje (Scrum)
  gl-busca-sprint.js    # busca de cards do GitLab
tests/                  # mais de 600 testes (unittest)
```

## Resumo das mudancas (Fase A — Jardim da Equipe)

- Sistema de strikes e prendas **removido da interface** (dados preservados no banco).
- Novo status **Avisou** (justificada): neutro para o jogo.
- Novo sistema de **jogo: planta que cresce** com presenças (estagios 0-10, vigor).
- **Excluir membro** com confirmacao de nome e backup previo.
- **Calendario editavel** (inicio, fim, feriados) via tela propria.
- Novos dados **derivados do historico**: sequencia, estagio, vigor, frutos.
- **Dashboard** redesenhado: jardim visual, progresso coletivo, destaques positivos.
- SVG parametrico da planta (`_planta.html`) pronto para a Fase B (loja/especies).
- Migracao segura e idempotente do banco real com backup automatico.
- Variavel de ambiente `STRIKES_DB` para apontar para banco alternativo.

## Defaults de calendario assumidos — confirme com o time

| Campo                | Valor padrao    |
|----------------------|-----------------|
| Inicio da semana 1   | 2026-10-12      |
| Numero de semanas    | 10              |
| Fim do projeto       | 2026-12-18      |
| Sprint em semanas    | 2               |
| Contar a partir de   | 2026-10-15      |
| Feriados             | 12/10, 02/11, 20/11 |
| Dias letivos totais  | 45              |
| Meta de floracao     | 36 presenças    |

Acesse a tela **Calendario** para ajustar qualquer valor.
