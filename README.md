# Jardim da Equipe — Controle de Presenca

Site local para controlar a presenca dos membros do grupo em 3 eventos diarios obrigatorios:
**Daily**, **Presenca no Dev** e **Encerramento**. Cada presenca faz a planta de cada membro crescer.
Dados ficam salvos em um banco SQLite real (`data/strikes.db`), nao em localStorage.

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

## Visual

Jardim noturno em ilustracao plana: paleta verde-floresta com acento lima, tipografia
Bricolage Grotesque (licenca OFL, hospedada em `static/fonts/`, entao funciona offline), logo e
favicon em `static/favicon.svg`. As plantas sao um unico SVG em camadas (`templates/_planta.html`)
que cresce ao vivo ao marcar presenca. No celular a navegacao vira uma barra inferior e cada
membro vira um cartao compacto.

## Jardim vivo (branch `feature/jardim-vivo`)

- **Céu por horário**: o cenário muda com a hora do dia (madrugada, amanhecer, manhã, meio-dia,
  tarde, entardecer e noite), com sol e lua percorrendo o céu. A regra está em `game.periodo_do_dia`
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
   nunca sobrescrevê-lo. Suba **uma única vez** o seu banco atual: na aba **Files**, envie o
   arquivo `data/strikes.db` do seu computador para `/home/SEUUSUARIO/dados/strikes.db`.
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

- **Hoje** (`/`): faixa de jardim com plantas dos membros ativos; tabela de presenca com tres botoes
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

```bash
venv\Scripts\python -m unittest discover tests
```

## Estrutura do projeto

```
app.py                  # backend Flask + rotas + migracao
game.py                 # logica de jogo (pura, testavel, sem Flask)
tests/test_game.py      # 48 testes unitarios
data/strikes.db         # banco SQLite (criado automaticamente)
data/backups/           # backups automaticos
templates/
  base.html             # layout base
  _planta.html          # macro SVG parametrico da planta
  dia.html              # tela Hoje
  dashboard.html        # dashboard e jardim grande
  historico.html        # historico de dias
  membros.html          # gerenciar membros
  calendario.html       # configurar periodo e feriados
static/style.css        # estilos (tema escuro)
static/app.js           # logica de marcacao e toasts
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
