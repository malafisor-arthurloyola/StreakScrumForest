# Balanceamento do Jardim da Equipe

Este documento descreve os números do jogo, o raciocínio por trás deles e onde mexer para ajustar.
Os valores abaixo foram conferidos por simulação sobre o calendário real (45 dias letivos, meta de 36)
e estão protegidos por testes automáticos (`tests/test_game.py`, `tests/test_loja.py`).

## 1. Princípios

1. **Nunca punir.** A planta nunca morre, sementes nunca diminuem por falta e o saldo só cai por compra.
2. **Crescimento e dinheiro são coisas separadas.** O crescimento da planta mede constância (dias);
   as sementes medem esforço (eventos). Comprar algo nunca altera o crescimento real.
3. **Orçamento para escolher.** Ninguém compra o catálogo inteiro: o time decide o que vale a pena.
4. **Tudo é derivado do histórico.** Corrigir um registro antigo recalcula tudo, sem migração.
5. **Tom Scrum.** Justificada ("avisou") é neutra: não ajuda nem atrapalha.

## 2. Calendário (base de todo o resto)

| Item | Valor padrão |
|---|---|
| Semana 1 | 12/10/2026 |
| Duração | 10 semanas (até 18/12) |
| Sprints | 5, de 2 semanas |
| Início da contagem | 15/10/2026 |
| Feriados | 12/10, 02/11, 20/11 |
| Dias letivos (D) | **45** (seg a sex, sem feriado, desde 15/10) |

Tudo é editável na tela Calendário. Se D mudar, a meta e os estágios se ajustam sozinhos.

## 3. Crescimento da planta (por dia, não por evento)

- Um dia conta como **presença** se o membro marcou **pelo menos um** dos três eventos.
- Meta de floração: `ceil(0,80 x D)` = **36 presenças**. Folga de 20% para imprevistos.
- Presença: +1. Falta (só faltou, sem nenhuma presença no dia): -2. Justificada e pendente: neutro.
- Estágios 0 a 10; um estágio novo a cada 3 a 4 dias letivos. O estágio 10 (Floresceu) é permanente.
- Piso protegido: falta nunca derruba abaixo do início do maior estágio já alcançado.

**Por que o crescimento continua por dia?** Se crescesse por evento, quem perde só o encerramento
(por compromisso, por exemplo) pareceria "atrasado" na planta. As sementes premiam o esforço extra
sem deixar ninguém para trás no visual.

## 4. Sementes (a economia)

### 4.1 De onde vêm as sementes, explicado do zero

Existem **7 jeitos** de ganhar sementes. Só o primeiro é "por evento"; os outros seis são bônus
automáticos que o sistema soma sozinho por cima.

**Jeito 1: presença nos eventos (a base, o que você pediu)**

| Evento | Sementes |
|---|---|
| Presença na daily | +1 |
| Presença no dev | +1 |
| Presença no encerramento | +1 |

Um dia em que a pessoa vai aos três rende **3 sementes**. Durante os 45 dias letivos, o máximo
possível é 45 x 3 = **135 sementes só da base**.

**Jeito 2: semana fechada (+3)**: bônus por constância semanal. Uma semana "fecha" quando a pessoa
teve presença (em qualquer evento) em pelo menos 4 dias da semana. Em semana com feriado, vale um dia
a menos do que os dias letivos (feriado não pune). Das 10 semanas do projeto, 9 podem fechar; a
semana 1 só tem 2 dias contados (o uso começou em 15/10), então não fecha. Máximo: 9 x 3 = **27**.

**Jeito 3: marco de sequência (bônus único)**: ao alcançar uma **sequência** de dias seguidos com
presença, a pessoa ganha um prêmio **uma vez só** por marco:

| Sequência alcançada | Prêmio (uma vez) |
|---|---|
| 5 dias seguidos | +3 |
| 10 dias seguidos | +5 |
| 20 dias seguidos | +10 |
| 40 dias seguidos | +20 |

Quem consegue 40 dias seguidos leva os quatro (3+5+10+20), total **38**.

**Jeito 4: dia cheio do time (+1)**: quando **todos** os membros ativos foram ao menos a um evento
no mesmo dia e ninguém faltou, cada pessoa presente naquele dia ganha +1 extra. É o bônus coletivo,
para incentivar o time a vir junto. Máximo: 45 dias cheios = **45**.

**Jeito 5: Floresceu (+20)**: quando a planta chega ao estágio 10 (atingiu as 36 presenças). Bônus único.

**Jeito 6: Boas-vindas (+20)**: um presente único na **primeira presença registrada** de cada pessoa
(derivado: vale assim que `dias_presentes >= 1`). É o "bem-vindo ao jardim", para quem começa já sair
do zero. Bônus único, não se repete.

**Jeito 7: Ata da daily (adubo, +1 por ata)**: cada ata (a **Daily** e o **Day Closing** do dia) em que
a pessoa deixa a fala registrada — texto não vazio em "feito" **ou** em "planejado" — rende **+1**. Não
avalia conteúdo nem tamanho: escreveu, ganhou. Como há 2 atas por dia, o máximo é **+2 por pessoa por
dia**. O **relator** (Scrum) ganha **+1 por cada fala de OUTRA pessoa que ele preenche** na ata (uma por pessoa e por ata; na Daily e no Day Closing), à parte (bônus de relator). A fala dele mesmo rende só o +1 normal. Só vale a fala que o relator escreveu pela pessoa: se a pessoa a escreveu no próprio celular, não rende ao relator (o sistema guarda quem escreveu por último).
Impedimentos são texto livre e **nunca rendem semente** (senão viraria exploit). A planta fica
"adubada" no dia (brilho e flores extras), mas isso é só visual: o crescimento continua por presença.

> **Selo Fundador** (não é semente): quem teve presença em qualquer dia até `fundador_ate`
> (padrão 23/10/2026, editável na tela Calendário) ganha o selo e o acessório exclusivo "Selo Fundador".
> É só cosmético: aparece no perfil e no álbum, não está à venda e não muda nenhum total de sementes.

> Justificada ("avisou") rende 0 sementes e não quebra nenhum desses bônus.

### 4.2 A streak (sequência) multiplica o ganho? Não

**Não existe multiplicador.** Uma sequência longa não aumenta o valor de cada evento: o daily vale
+1 no dia 1 e continua valendo +1 no dia 40. A streak entra na economia de duas formas, sem
multiplicar nada:

1. **Marcos únicos** (Jeito 3): bônus fixos em 5, 10, 20 e 40 dias seguidos (total de 38).
2. **Visual, sem semente**: a chama e o vigor da planta (verde, viçosa, florida, radiante) refletem a
   sequência atual, mas só mudam a aparência.

Por que não multiplicador? Em um multiplicador a diferença cresce bola de neve: quem quebra a
sequência uma vez perde muito, o que cria ansiedade (o mesmo problema criticado no Duolingo) e fere o
princípio "nunca punir". Os marcos dão a recompensa de constância sem esse risco: quebrar a
sequência não tira nada do que já foi ganho, só reinicia a contagem para o próximo marco.

Se o time preferir um multiplicador, dá para adicionar (por exemplo +1 semente extra por dia de
presença com sequência acima de 10). Isso aumentaria o total do dedicado e exigiria subir os preços
de novo. Ver a seção 8.

### 4.3 Por que o perfil dedicado chega a 375 (conta passo a passo)

"Dedicado" = foi aos 3 eventos todos os 45 dias letivos, sem nenhuma falta, o time inteiro também, e
deixou a fala registrada nas duas atas de cada dia.

| Origem | Conta | Sementes |
|---|---|---|
| Presença nos eventos | 45 dias x 3 eventos x 1 | 135 |
| Semanas fechadas | 9 semanas x 3 | 27 |
| Marcos de sequência | 3 + 5 + 10 + 20 | 38 |
| Dia cheio do time | 45 dias x 1 | 45 |
| Floresceu | bônus único | 20 |
| Boas-vindas | bônus único | 20 |
| Ata da daily (adubo) | 45 dias x 2 atas x 1 | 90 |
| **Total** | | **375** |

O total **375** é sem contar o bônus de relator (+1 por fala de outra pessoa que ele preenche, à parte, conforme o
rodízio). Impedimentos não entram. Só 135 de 375 vêm de "estar presente em cada evento"; o resto são
os bônus de constância, de time, de boas-vindas e de ata (Jeitos 2 a 7).

### 4.4 Totais esperados no projeto inteiro (simulação)

| Perfil | Fase 3 (sem ata) | Agora (com ata) | Composição (agora) |
|---|---|---|---|
| **Dedicado**: 3 eventos, 45 dias, 2 atas/dia | 285 | **375** | 135 eventos + 27 semanas + 38 marcos + 45 dia cheio + 20 floresceu + 20 boas-vindas + 90 ata |
| **Típico**: ~88% dos dias, dev ~85%, enc. ~75%, fala em ~1,5 ata/dia | 211 | **~275** | 211 de antes + ~64 de ata (≈ 43 dias x 1,5) |
| **Só daily**: 45 dias, nunca dev/enc., fala só na daily | 195 | **240** | 195 de antes + 45 (só a daily) |

Leitura: a ata vira a maior fonte de "esforço extra" depois dos eventos. Cada pessoa controla quanto
ganha dela só escrevendo a própria fala; o relator ganha +1 por cada colega que ele preenche (mais trabalho, mais semente).
O bônus de relator não entra nos totais acima porque depende do rodízio. Ordem de grandeza: num dia em que ele preenche as duas atas de todos os outros 6, são até +12; com rodízio entre 7 pessoas, cada um relata ~6 dias do projeto, ou seja, até ~+72 no máximo, e na prática bem menos (quem escreve a própria fala não conta). Se pesar demais, dá para limitar por ata em `SEED_RELATOR`/`_contagem_atas`.

### 4.5 Curva de saldo acumulado (sem gastar), por fim de semana

Os valores abaixo já incluem as boas-vindas (+20), creditadas na primeira semana com presença.

| Semana | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Dedicado | 36 | 62 | 90 | 109 | 142 | 161 | 184 | 227 | 270 | 285 |
| Típico | 33 | 51 | 71 | 83 | 102 | 120 | 135 | 153 | 180 | 211 |

## 5. Loja: preços

Triplicar o ganho diário sem mexer nos preços faria tudo ficar barato demais (o dedicado compraria a
loja quase inteira). Por isso **todos os preços dobraram**. A proporção entre "quanto o jogador
junta" e "quanto o catálogo custa" ficou perto da original (típico: 18% do catálogo antes, 13% agora;
dedicado: 25% antes, 19% agora), um pouco mais exigente para dar sensação de escolha.

| Tipo | Itens e preços |
|---|---|
| Plantinha extra | 2ª: **60**, 3ª: **110** |
| Espécies | Girassol 40, Samambaia 40, Cacto 50, Lavanda 50, Cerejeira 70, Bambu 70, Cogumelo 80, Bonsai 90, Jabuticabeira 90, Carnívora 110, Ipê 120, Baobá 120 (só depois de florescer) |
| Vasos | 12, 16, 20, 24, 30 |
| Companheiros | 20, 24, 30, 40, 50 |
| Acessórios | 16, 20, 24 |
| **Total do catálogo** | **1.426** |

### 5.1 Ritmo de compra (dia letivo em que o saldo alcança cada valor)

| Saldo | 12 (1º vaso) | 24 | 40 (1ª espécie) | 60 (2ª plantinha) | 80 | 120 (espécie épica) |
|---|---|---|---|---|---|---|
| Dedicado | dia 3 | dia 6 | dia 9 | dia 12 | dia 16 | dia 23 |
| Típico | dia 4 | dia 6 | dia 12 | dia 18 | dia 23 | dia 34 |
| Só daily | dia 5 | dia 9 | dia 13 | dia 20 | dia 24 | dia 36 |

Meta de ritmo: primeira compra na primeira semana, 2ª plantinha por volta da semana 3 ou 4 e espécie
épica no fim do projeto para o típico. O ritmo atual cumpre isso.

Exemplo de orçamento típico (211): 2ª plantinha (60) + espécie rara (70) + vaso (24) + companheiro (30)
= 184. Exemplo dedicado (285): isso tudo + uma espécie épica.

## 6. Metas coletivas

- **Jardim coletivo**: soma do crescimento de todos / (ativos x meta). Marcos grátis para todos aos
  25%, 50%, 75% e 100% (fonte, vagalumes, chuva de pétalas, árvore do time).
- **Metas da Sprint**: o time escolhe 1 a 3 (presença %, dias cheios, dias cheios seguidos). Nenhuma
  recompensa em sementes, só selo de sprint cumprida.
- **Dia cheio** (todos presentes, ninguém faltou) é o único gatilho que olha o time e rende semente
  (+1 por pessoa presente). Ele considera "presente" qualquer evento, então não muda com a nova regra.

## 7. Cuidados e armadilhas

- **Marcar tudo por marcar**: o botão "marcar todos presentes por evento" já existia e agora rende
  semente. Na prática o time se confia na honestidade; não há login. Se virar problema, dá para
  limitar o bônus de dev e encerramento ao horário do dia ou exigir confirmação.
- **Inflação**: mexer nos pesos dos eventos obriga a revisar os preços na mesma proporção (regra de
  ouro: dobrar o ganho = dobrar os preços).
- **Saldo nunca negativo**: se uma correção retroativa reduzir o ganho abaixo do gasto, o saldo vira 0
  e bloqueia compra nova, mas nenhum item comprado é removido.

## 8. Onde mexer

| Quero mudar | Onde |
|---|---|
| Peso de cada evento | `SEED_POR_EVENTO` em `game.py` |
| Multiplicador de sequência (não existe hoje) | seria código novo em `calcular_sementes` |
| Bônus de semana, dia cheio, floresceu, boas-vindas | `SEED_SEMANA_FECHADA`, `SEED_DIA_CHEIO`, `SEED_FLORESCEU`, `SEED_BOAS_VINDAS` em `game.py` |
| Bônus de ata e de relator | `SEED_ATA`, `SEED_RELATOR` em `game.py` |
| Marcos de sequência | `SEED_MILESTONES` em `game.py` |
| Preços | `catalog.py` (campo `preco`) |
| Meta de floração (80%) | `meta_floracao` em `game.py` |
| Fundador (data limite) | `fundador_ate` na tela Calendário |
| Idioma da exportação da ata / link do GitLab | `idioma_ata`, `gitlab_base_url` (config) |
| Calendário e feriados | tela Calendário |

Ao mexer em qualquer valor, rode `python -m unittest discover tests`. Os testes de faixa de preço e de
total esperado (`tests/test_catalog.py`, `tests/test_game.py`) avisam se o equilíbrio saiu do alvo.

## 9. Histórico de mudanças

- **Fase B**: sementes por dia de presença (+1), semana, marcos, dia cheio e floresceu; preços de 6 a 60.
- **Sementes por evento**: +1 para cada um de daily, dev e encerramento; preços dobrados (12 a 120).
- **Fase 1 (sementes e dia cheio)**: as fontes de bônus viraram constantes nomeadas em `game.py`
  (fonte única, sem números mágicos); nova aba `/sementes`; card "Próximos marcos" no Painel; e a 6ª
  fonte, **boas-vindas (+20)**, bônus único na primeira presença (dedicado 265 -> 285, típico 191 -> 211,
  só daily 175 -> 195). Selo/acessório **Fundador** (cosmético, não rende semente), ligado a `fundador_ate`.
- **Fase 4 (ata da daily)**: 7ª fonte, **ata (adubo, +1 por ata com fala)** — a Daily e o Day Closing
  de cada dia, máximo +2 por pessoa por dia; o relator ganha +1 por fala de outra pessoa que preenche (à parte). Impedimento
  nunca rende semente. Dedicado 285 -> 375 (sem contar o bônus de relator). Constantes `SEED_ATA` e
  `SEED_RELATOR` em `game.py`.
- **Fase 6c (campos da daily + GitLab)**: a daily passou a ter três campos em português ("O que fiz",
  "O que vou fazer hoje", "Vou revisar") com chips dos cards do GitLab (Doing, Waiting review, Review,
  Backlog e fechados recentes). **Nada disso mudou o balanceamento**: as fontes de semente continuam
  sendo só "O que fiz" e "O que vou fazer" (os campos `feito`/`planejado`); "Vou revisar"
  (`ata_falas.review`) **nunca rende**. Os rótulos visíveis mudaram; as constantes e os totais acima
  seguem iguais.
