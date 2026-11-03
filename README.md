# Agente de tarefas no Trello

Um agente de conversa, feito em Python com o ADK do Google e o Gemini, que organiza as tarefas do dia num quadro do Trello. Você conta o que tem para fazer, ele cria os cards. Você conta o que já fez, ele move os cards.

Entrega do desafio da DIO, a partir do agente base em [`agents/agent04`](https://github.com/digitalinnovationone/agent-carbon-footprint/tree/main/agents/agent04).

---

## O que ele faz

Abre a conversa perguntando quais são as tarefas do dia, já dizendo a data e o dia da semana. Depois de cada tarefa, pergunta se tem mais alguma, até você dizer que acabou.

Cada função Python do `agent.py` é uma ferramenta que ele pode chamar sozinho:

| ferramenta | o que faz |
|---|---|
| `obter_data_de_hoje` | devolve a data, a hora e o dia da semana, para abrir a conversa e datar as tarefas |
| `listar_quadros` | diz quais quadros existem na sua conta do Trello |
| `adicionar_tarefa` | cria um card na lista **A FAZER**, com nome, descrição e data de entrega |
| `listar_tarefas` | lista as tarefas, todas ou só as de um status |
| `mudar_status_tarefa` | move o card entre **A FAZER**, **EM ANDAMENTO** e **CONCLUÍDO** |
| `remover_tarefa` | apaga um card do quadro |

---

## Como rodar

### 1. O quadro no Trello

Crie um quadro com três listas, exatamente com estes nomes:

```
A FAZER        EM ANDAMENTO        CONCLUÍDO
```

O nome do quadro pode ser qualquer um — você escreve qual é no `.env`. No agente original ele estava escrito dentro do código, como `DIO`.

### 2. As chaves do Trello

Em [trello.com/power-ups/admin](https://trello.com/power-ups/admin), crie um Power-Up para a sua conta. Ele te dá a **chave** e o **segredo**. Na mesma tela, o link *Token* gera o **token** da sua conta.

### 3. A chave do Gemini

Em [aistudio.google.com/apikey](https://aistudio.google.com/apikey), gere uma chave gratuita.

### 4. O ambiente

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Precisa de Python 3.10 ou mais novo. O `readme.md` do repositório base fala em 3.7, mas o ADK de hoje não roda nessa versão.

### 5. As credenciais

Copie `agente_de_tarefas/.env.exemplo` para `agente_de_tarefas/.env` e preencha. O `.env` está no `.gitignore` e nunca entra no repositório.

### 6. Rodar

```bash
adk web
```

Abra o endereço que ele mostrar, escolha `agente_de_tarefas` e comece a conversar.

---

## As melhorias que eu fiz, e por quê

O desafio lista seis defeitos do agente base e pede que eu escolha um. Fiz os seis, porque cinco deles são a mesma doença: a função não tratava o caso torto, e o erro chegava ao usuário como uma quebra.

### 1. A data chegava ao Trello com um dia a menos

**O que acontecia:** o agente base mandava a data crua, como `2026-11-03`. O Trello guarda tudo em UTC, então essa data vira meia-noite em UTC — que no Brasil é 21h do dia **2**. O card nascia um dia antes do combinado.

**O que eu fiz:** a função `_data_para_o_trello` transforma a data em **meio-dia no fuso desta máquina** antes de converter para UTC. Meio-dia tem doze horas de folga para cada lado, então o dia não anda para trás nem para frente, em nenhum fuso do Brasil.

**Como testei:** rodei a conversão com a data de hoje e conferi o dia que volta do Trello depois de criar o card.

### 2. "concluído" com acento dava status inválido

**O que acontecia:** o mapa de status tinha as chaves `"a fazer"`, `"em andamento"` e `"concluido"`, comparadas com o texto cru. Quem escrevesse `concluído`, com acento, recebia *status inválido* — e é assim que qualquer pessoa escreve.

**O que eu fiz:** toda comparação passa por `_sem_acento`, que tira acento e maiúscula. E cada status ganhou uma lista de apelidos: `concluído`, `concluido`, `done`, `feito`, `pronto`, `finalizado`, `terminado`.

### 3. Faltava a ferramenta de remover

**O que acontecia:** a instrução do agente prometia *"Remover tarefas da lista"*, e a ferramenta não existia. O agente dizia que ia remover e não removia.

**O que eu fiz:** criei `remover_tarefa`, e reescrevi a instrução para descrever só o que existe. A instrução agora cita a ferramenta de cada coisa, e manda confirmar antes de apagar, porque apagar não tem volta.

### 4. Só uma ferramenta tinha `try/except`

**O que acontecia:** apenas `mudar_status_tarefa` tratava erro. Nas outras, um quadro com nome errado ou uma credencial faltando viravam exceção crua.

**O que eu fiz:** todas as ferramentas devolvem dicionário com o campo `ok`. Quando algo falha, vem `{"ok": false, "erro": "..."}`, e a instrução manda o agente ler esse campo e explicar. O erro conta o que estava errado: se o quadro não existe, ele lista os quadros que existem; se a lista não existe, lista as listas do quadro.

### 5. A conexão com o Trello estava copiada em cada função

**O que acontecia:** as quatro ferramentas repetiam o mesmo `TrelloClient(...)`. Mudar qualquer coisa na conexão exigia mudar em quatro lugares.

**O que eu fiz:** uma função `_conectar`, usada por todas. Ela ainda avisa, com texto claro, quando falta credencial no `.env` — que é o erro número um de quem roda pela primeira vez.

### 6. Trabalhava com um quadro só

**O que acontecia:** o nome `DIO` estava escrito dentro do código, em quatro lugares.

**O que eu fiz:** o quadro padrão vem do `.env`, na variável `TRELLO_BOARD`, e **toda ferramenta aceita o nome de um quadro**. A instrução manda o agente perguntar em qual quadro a tarefa entra quando houver mais de um e a tarefa parecer de outro. A ferramenta `listar_quadros` existe para ele poder perguntar sabendo as opções.

---

## Uma coisa que não é defeito, mas mudei

As ferramentas do agente base devolviam texto com emoji dentro (`❌ Status inválido`). Agora devolvem dicionário. O modelo lê dado melhor do que lê frase pronta, e quem escreve a resposta para a pessoa passa a ser o agente, não a função.
