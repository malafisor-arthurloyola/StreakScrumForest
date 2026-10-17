# Controle de Presença — Strikes e Prendas

Site local para controlar a presença dos membros do grupo em 3 eventos diários obrigatórios:
**Daily**, **Presença no Dev** e **Encerramento**. Cada falta vira 1 strike; ao acumular 3
strikes o membro "deve prenda". Dados ficam salvos em um banco SQLite real (`data/strikes.db`),
não em localStorage — persistem entre reinícios do site.

## Como rodar

Pré-requisito: Python 3.9+ instalado.

1. Abra um terminal nesta pasta (`Contagem de strikes`).
2. (Opcional, mas recomendado) crie um ambiente virtual:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
3. Instale a única dependência (Flask):
   ```bash
   pip install -r requirements.txt
   ```
4. Rode o servidor:
   ```bash
   python app.py
   ```
5. Abra no navegador: [http://localhost:5000](http://localhost:5000)

Na primeira execução o banco `data/strikes.db` é criado automaticamente e já vem com os
9 membros informados (Arthur, Bento, Dominique, Vitor, Tiago, Rafael, Alexandre, Heloisa, João).
Você pode editar essa lista a qualquer momento pela tela **Membros**.

## Acessar de outro aparelho (celular etc.) na mesma Wi-Fi

O servidor já sobe em `0.0.0.0`, então outros aparelhos na mesma rede conseguem acessar.

1. Descubra o IP do seu notebook na rede local:
   ```bash
   ipconfig
   ```
   (procure por "Endereço IPv4", algo como `192.168.0.x`)
2. No celular, acesse `http://192.168.0.x:5000` (trocando pelo IP encontrado).

Se não conectar, verifique se o firewall do Windows está bloqueando a porta 5000 na rede
privada (ele costuma perguntar na primeira vez que o servidor sobe — permita o acesso).

## Backup automático

Toda vez que você roda `python app.py`, se já existir um `data/strikes.db`, o app salva uma
cópia dele em `data/backups/strikes-AAAA-MM-DD.db` **antes** de tocar em qualquer coisa (no
máximo 1 backup por dia, mesmo que você reinicie o servidor várias vezes). Isso existe como uma
rede de segurança — se algo der errado (edição em massa por engano, banco corrompido, etc.), dá
pra restaurar: feche o servidor, copie o arquivo de backup desejado para `data/strikes.db`
(substituindo o atual) e suba o servidor de novo.

## Como funciona

- **Hoje** (`/`): marca presença/falta de cada membro nos 3 eventos do dia. Dá para navegar
  para dias anteriores/seguintes ou digitar uma data específica. Cada coluna de evento tem um
  botão "marcar todos presentes" no cabeçalho, para o caso comum de quase todo mundo ter
  comparecido — sobrescreve as marcações já feitas naquele evento.
- **Histórico** (`/historico`): lista todos os dias já registrados, com total de faltas, e
  permite abrir qualquer dia (passado ou futuro) para corrigir um registro.
- **Dashboard** (`/dashboard`): mostra dois gráficos (tendência de presença geral nos últimos
  dias e um comparativo de faltas por membro, separado por evento) e a tabela com strikes atuais
  e total de prendas pagas de cada membro, com destaque vermelho para quem "deve prenda!". Tem o
  botão para marcar a prenda como paga. Os gráficos são gerados em SVG/CSS puro pelo próprio
  servidor — sem nenhuma biblioteca externa, para manter o site leve e funcionando 100% offline.
- **Membros** (`/membros`): cadastra novos membros, renomeia ou desativa membros que saíram do
  grupo (o histórico deles é mantido, mas eles somem da tela "Hoje").

### Regra dos strikes

- Cada falta marcada em qualquer um dos 3 eventos soma 1 strike ao contador atual do membro.
- Um evento não marcado por ninguém fica "pendente" e **não** conta como falta.
- Com 2 strikes o membro ganha um badge âmbar de alerta ("quase lá"); ao chegar a 3 strikes,
  vira o badge vermelho "DEVE PRENDA!".
- O botão "Marcar prenda paga" zera o contador atual e soma 1 ao histórico de prendas pagas
  daquele membro.
- Corrigir uma falta de um dia antigo recalcula o contador atual automaticamente — **a menos**
  que aquela falta já tenha sido "coberta" por uma prenda paga anteriormente, caso em que ela
  fica congelada no histórico e não mexe no contador atual (evita reabrir uma prenda já paga).

### Sequência sem faltar

Cada membro tem um badge roxo mostrando há quantos dias seguidos ele não falta em nenhum dos 3
eventos (aparece no Dashboard e em Membros). Um dia "conta" para a sequência quando o membro tem
pelo menos um evento marcado presente e nenhum marcado como falta naquele dia; um dia com falta
zera a sequência. Quando o recorde é maior que a sequência atual, ele aparece como texto pequeno
abaixo do badge. Assim como os strikes, é recalculado automaticamente a partir do histórico —
corrigir um dia antigo pode mudar a sequência na hora.

## Estrutura do projeto

```
app.py                # backend Flask + rotas da API + inicialização do banco
data/strikes.db        # banco SQLite (criado automaticamente na primeira execução)
templates/             # páginas HTML (Jinja2)
static/style.css       # estilos
static/app.js          # lógica de marcar presença/falta sem recarregar a página
```
