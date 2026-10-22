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

### 4.1 Fontes de ganho

| Fonte | Valor | Observação |
|---|---|---|
| Presença na **daily** | +1 | por dia |
| Presença no **dev** | +1 | por dia |
| Presença no **encerramento** | +1 | por dia (novo: antes só o dia inteiro rendia 1) |
| Semana fechada | +3 | 4 presenças na semana (ou dias letivos - 1 em semana com feriado) |
| Marco de sequência | +3 / +5 / +10 / +20 | uma vez cada, em 5 / 10 / 20 / 40 dias seguidos |
| Dia cheio do time | +1 | para cada pessoa presente num dia em que todos vieram |
| Floresceu | +20 | uma vez |
| Justificada | 0 | neutro |

Um dia com os três eventos rende até **3 sementes** (antes rendia 1). Cada evento vale o mesmo, porque
os três são obrigatórios e igualmente importantes para o time. Os pesos ficam em
`SEED_POR_EVENTO` (`game.py`), então dá para dar peso diferente a um evento depois.

### 4.2 Totais esperados no projeto inteiro (simulação)

| Perfil | Antes | Agora | Composição (agora) |
|---|---|---|---|
| **Dedicado**: 3 eventos, 45 dias | 175 | **265** | 135 eventos + 27 semanas + 38 marcos + 45 dia cheio + 20 floresceu |
| **Típico**: ~88% dos dias, daily sempre, dev ~85%, encerramento ~75% | 129 | **191** | 102 eventos + 27 semanas + 18 marcos + 24 dia cheio + 20 floresceu |
| **Só daily**: 45 dias, nunca dev nem encerramento | 175 | **175** | 45 eventos + 27 + 38 + 45 + 20 |

Leitura: quem vai a tudo ganha 51% mais que antes; quem faz só a daily fica igual. Isso é o efeito
desejado: o dev e o encerramento passam a ter recompensa própria.

### 4.3 Curva de saldo acumulado (sem gastar), por fim de semana

| Semana | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 |
|---|---|---|---|---|---|---|---|---|---|---|
| Dedicado | 16 | 42 | 70 | 89 | 122 | 141 | 164 | 207 | 250 | 265 |
| Típico | 13 | 31 | 51 | 63 | 82 | 100 | 115 | 133 | 160 | 191 |

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

Exemplo de orçamento típico (191): 2ª plantinha (60) + espécie rara (70) + vaso (24) + companheiro (30)
= 184. Exemplo dedicado (265): isso tudo + uma espécie épica.

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
| Bônus de semana (+3), dia cheio (+1), floresceu (+20) | `calcular_sementes` em `game.py` |
| Marcos de sequência | `SEED_MILESTONES` em `game.py` |
| Preços | `catalog.py` (campo `preco`) |
| Meta de floração (80%) | `meta_floracao` em `game.py` |
| Calendário e feriados | tela Calendário |

Ao mexer em qualquer valor, rode `python -m unittest discover tests`. Os testes de faixa de preço e de
total esperado (`tests/test_catalog.py`, `tests/test_game.py`) avisam se o equilíbrio saiu do alvo.

## 9. Histórico de mudanças

- **Fase B**: sementes por dia de presença (+1), semana, marcos, dia cheio e floresceu; preços de 6 a 60.
- **Sementes por evento**: +1 para cada um de daily, dev e encerramento; preços dobrados (12 a 120).
