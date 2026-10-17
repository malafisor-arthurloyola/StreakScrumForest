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

## Como testar a branch de redesign (`redesign/visual`)

Use sempre uma **cópia** do banco para não alterar os dados reais do grupo.

1. Traga a branch e troque para ela (a partir da pasta do projeto):
   ```bash
   git fetch origin
   git switch redesign/visual
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
