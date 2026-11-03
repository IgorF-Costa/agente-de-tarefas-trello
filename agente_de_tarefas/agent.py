"""Agente que organiza as tarefas do dia num quadro do Trello, por conversa.

Cada função abaixo marcada como ferramenta é registrada no agente no fim do
arquivo. O agente lê a docstring de cada uma para decidir qual chamar.
"""

import os
import unicodedata
from datetime import datetime, time, timedelta, timezone

from dotenv import load_dotenv
from google.adk.agents.llm_agent import Agent
from trello import TrelloClient

load_dotenv()

API_KEY = os.getenv("TRELLO_API_KEY")
API_SECRET = os.getenv("TRELLO_API_SECRET")
TOKEN = os.getenv("TRELLO_TOKEN")
QUADRO_PADRAO = os.getenv("TRELLO_BOARD", "DIO")

# Os três status do quadro, e todo jeito de escrever que o usuário pode usar.
# A chave é o que vai para o Trello; a lista são os apelidos aceitos.
STATUS = {
    "A FAZER": ["a fazer", "afazer", "to do", "todo", "pendente", "fazer", "aberto"],
    "EM ANDAMENTO": ["em andamento", "andamento", "doing", "fazendo", "em progresso", "progresso"],
    "CONCLUÍDO": ["concluido", "concluída", "concluida", "done", "feito", "pronto", "finalizado", "terminado"],
}


# ──────────────────────────────────────────────────────────────────────
# Ajudantes internos. Não são ferramentas: o agente não os enxerga.
# ──────────────────────────────────────────────────────────────────────

def _sem_acento(texto: str) -> str:
    """Devolve o texto em minúscula e sem acento, para comparar sem susto."""
    sem = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in sem if not unicodedata.combining(c)).strip().lower()


def _conectar():
    """Abre a conexão com o Trello. Antes isto estava copiado em cada ferramenta."""
    if not (API_KEY and API_SECRET and TOKEN):
        raise RuntimeError(
            "Faltam credenciais do Trello. Copie o .env.exemplo para .env e preencha "
            "TRELLO_API_KEY, TRELLO_API_SECRET e TRELLO_TOKEN."
        )
    return TrelloClient(api_key=API_KEY, api_secret=API_SECRET, token=TOKEN)


def _achar_quadro(nome_do_quadro: str):
    """Acha o quadro pelo nome, ignorando acento e maiúscula. Vazio = quadro padrão."""
    procurado = _sem_acento(nome_do_quadro) or _sem_acento(QUADRO_PADRAO)
    quadros = _conectar().list_boards()
    for quadro in quadros:
        if _sem_acento(quadro.name) == procurado:
            return quadro
    existentes = ", ".join(q.name for q in quadros) or "nenhum"
    raise LookupError(
        f"Não achei um quadro chamado '{nome_do_quadro or QUADRO_PADRAO}'. "
        f"Os seus quadros são: {existentes}."
    )


def _achar_lista(quadro, status: str):
    """Acha a lista do quadro que corresponde ao status pedido."""
    alvo = _status_oficial(status)
    for lista in quadro.list_lists():
        if _sem_acento(lista.name) == _sem_acento(alvo):
            return lista
    nomes = ", ".join(l.name for l in quadro.list_lists()) or "nenhuma"
    raise LookupError(
        f"O quadro '{quadro.name}' não tem uma lista '{alvo}'. As listas dele são: {nomes}."
    )


def _status_oficial(escrito: str) -> str:
    """Traduz o jeito que a pessoa escreveu para o nome exato da lista no Trello."""
    pedido = _sem_acento(escrito)
    for oficial, apelidos in STATUS.items():
        if pedido == _sem_acento(oficial) or pedido in [_sem_acento(a) for a in apelidos]:
            return oficial
    aceitos = " / ".join(STATUS.keys())
    raise ValueError(f"Não entendi o status '{escrito}'. Use um destes: {aceitos}.")


def _data_para_o_trello(due_date: str) -> str:
    """Transforma uma data escrita por gente na data certa no Trello.

    O agente original mandava a data crua. O Trello guarda tudo em UTC, então
    '2026-11-03' virava meia-noite em UTC, que no Brasil é 21h do dia 2 — e o
    card aparecia com um dia a menos. Aqui a data vira meio-dia no fuso desta
    máquina antes de virar UTC, e o dia para de andar para trás.
    """
    texto = (due_date or "").strip()
    if not texto:
        dia = datetime.now().date()
    else:
        dia = None
        for formato in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                dia = datetime.strptime(texto[:10], formato).date()
                break
            except ValueError:
                continue
        if dia is None:
            raise ValueError(
                f"Não entendi a data '{due_date}'. Escreva como 2026-11-03 ou 03/11/2026."
            )
    fuso_local = datetime.now().astimezone().tzinfo
    meio_dia_aqui = datetime.combine(dia, time(12, 0), tzinfo=fuso_local)
    return meio_dia_aqui.astimezone(timezone.utc).isoformat()


def _achar_card(quadro, nome_da_task: str):
    """Acha o card pelo nome em qualquer lista do quadro, e devolve o card e a lista."""
    procurado = _sem_acento(nome_da_task)
    for lista in quadro.list_lists():
        for card in lista.list_cards():
            if _sem_acento(card.name) == procurado:
                return card, lista
    # segunda passada, aceitando nome parcial
    for lista in quadro.list_lists():
        for card in lista.list_cards():
            if procurado and procurado in _sem_acento(card.name):
                return card, lista
    raise LookupError(f"Não achei nenhuma tarefa chamada '{nome_da_task}' no quadro '{quadro.name}'.")


# ──────────────────────────────────────────────────────────────────────
# As ferramentas do agente. Todas devolvem dicionário e nenhuma deixa
# exceção escapar: erro vira {"ok": False, "erro": "..."} para o agente
# poder explicar o problema em vez de quebrar a conversa.
# ──────────────────────────────────────────────────────────────────────

def obter_data_de_hoje() -> dict:
    """Devolve a data e a hora de agora, para abrir a conversa e datar as tarefas.

    Returns:
        dict: data no formato AAAA-MM-DD, hora, e o dia da semana por extenso.
    """
    agora = datetime.now()
    dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
            "sexta-feira", "sábado", "domingo"]
    return {
        "ok": True,
        "data": agora.strftime("%Y-%m-%d"),
        "hora": agora.strftime("%H:%M"),
        "dia_da_semana": dias[agora.weekday()],
    }


def listar_quadros() -> dict:
    """Lista os quadros do Trello desta conta, para saber em qual a tarefa entra.

    Returns:
        dict: os nomes dos quadros e qual é o quadro padrão.
    """
    try:
        nomes = [q.name for q in _conectar().list_boards()]
        return {"ok": True, "quadros": nomes, "quadro_padrao": QUADRO_PADRAO}
    except Exception as erro:
        return {"ok": False, "erro": str(erro)}


def adicionar_tarefa(nome_da_task: str, descricao_da_task: str, due_date: str,
                     nome_do_quadro: str) -> dict:
    """Cria um card na lista A FAZER com o nome, a descrição e a data de entrega.

    Args:
        nome_da_task: o título da tarefa, como ela vai aparecer no card.
        descricao_da_task: o detalhe da tarefa. Pode ser string vazia.
        due_date: a data de entrega, como 2026-11-03 ou 03/11/2026. Vazio = hoje.
        nome_do_quadro: o quadro onde criar. Vazio = o quadro padrão.

    Returns:
        dict: ok, o nome do card criado, o quadro, a lista e a data gravada.
    """
    try:
        quadro = _achar_quadro(nome_do_quadro)
        lista = _achar_lista(quadro, "A FAZER")
        vencimento = _data_para_o_trello(due_date)
        card = lista.add_card(name=nome_da_task, desc=descricao_da_task or "", due=vencimento)
        return {
            "ok": True,
            "tarefa": card.name,
            "quadro": quadro.name,
            "lista": lista.name,
            "vencimento": vencimento,
        }
    except Exception as erro:
        return {"ok": False, "erro": str(erro)}


def listar_tarefas(status: str, nome_do_quadro: str) -> dict:
    """Lista as tarefas do quadro, todas ou só as de um status.

    Args:
        status: 'todas', ou 'a fazer', 'em andamento', 'concluído'. Aceita
            variações como 'doing', 'done', 'concluido' sem acento.
        nome_do_quadro: o quadro a consultar. Vazio = o quadro padrão.

    Returns:
        dict: ok, quantas tarefas achou e a lista delas com nome, descrição,
        vencimento e status.
    """
    try:
        quadro = _achar_quadro(nome_do_quadro)
        pedido = _sem_acento(status)
        if pedido in ("", "todas", "todos", "tudo", "all"):
            listas = quadro.list_lists()
        else:
            listas = [_achar_lista(quadro, status)]

        tarefas = []
        for lista in listas:
            for card in lista.list_cards():
                tarefas.append({
                    "nome": card.name,
                    "descricao": card.desc,
                    "vencimento": str(card.due) if card.due else "",
                    "status": lista.name,
                })
        return {"ok": True, "quadro": quadro.name, "quantidade": len(tarefas), "tarefas": tarefas}
    except Exception as erro:
        return {"ok": False, "erro": str(erro)}


def mudar_status_tarefa(nome_da_task: str, novo_status: str, nome_do_quadro: str) -> dict:
    """Move a tarefa entre A FAZER, EM ANDAMENTO e CONCLUÍDO.

    Args:
        nome_da_task: o nome do card a mover. Aceita o nome parcial.
        novo_status: 'a fazer', 'em andamento' ou 'concluído'. Aceita variações
            com e sem acento, e também 'doing', 'done', 'pronto', 'feito'.
        nome_do_quadro: o quadro onde está a tarefa. Vazio = o quadro padrão.

    Returns:
        dict: ok, de qual lista saiu e para qual foi.
    """
    try:
        quadro = _achar_quadro(nome_do_quadro)
        lista_destino = _achar_lista(quadro, novo_status)
        card, lista_origem = _achar_card(quadro, nome_da_task)
        if lista_origem.id == lista_destino.id:
            return {"ok": True, "tarefa": card.name, "de": lista_origem.name,
                    "para": lista_destino.name, "aviso": "a tarefa já estava nessa lista"}
        card.change_list(lista_destino.id)
        return {"ok": True, "tarefa": card.name, "de": lista_origem.name, "para": lista_destino.name}
    except Exception as erro:
        return {"ok": False, "erro": str(erro)}


def remover_tarefa(nome_da_task: str, nome_do_quadro: str) -> dict:
    """Apaga uma tarefa do quadro. Só use quando a pessoa pedir para remover.

    Args:
        nome_da_task: o nome do card a apagar. Aceita o nome parcial.
        nome_do_quadro: o quadro onde está a tarefa. Vazio = o quadro padrão.

    Returns:
        dict: ok e o nome da tarefa que foi apagada.
    """
    try:
        quadro = _achar_quadro(nome_do_quadro)
        card, lista = _achar_card(quadro, nome_da_task)
        nome = card.name
        card.delete()
        return {"ok": True, "removida": nome, "estava_em": lista.name, "quadro": quadro.name}
    except Exception as erro:
        return {"ok": False, "erro": str(erro)}


root_agent = Agent(
    model="gemini-2.5-flash",
    name="agente_de_tarefas",
    description="Organiza as tarefas do dia num quadro do Trello, por conversa.",
    instruction="""
Você é um agente que organiza as tarefas do dia da pessoa num quadro do Trello.

Comece a conversa, assim que for ativado, chamando a ferramenta obter_data_de_hoje
e perguntando quais são as tarefas do dia, já dizendo a data e o dia da semana.
Depois de cada tarefa, pergunte se tem mais alguma, até a pessoa dizer que acabou.

O que você sabe fazer, e a ferramenta de cada coisa:
  1. criar uma tarefa, com nome, descrição e data de entrega  -> adicionar_tarefa
  2. listar as tarefas, todas ou só as de um status           -> listar_tarefas
  3. mover a tarefa entre A FAZER, EM ANDAMENTO e CONCLUÍDO   -> mudar_status_tarefa
  4. apagar uma tarefa do quadro                              -> remover_tarefa
  5. dizer que quadros existem nesta conta                    -> listar_quadros
  6. saber a data e a hora de agora                           -> obter_data_de_hoje

Marcar uma tarefa como concluída é mover ela para CONCLUÍDO com mudar_status_tarefa.
Não existe outra ferramenta para isso, e não prometa nada fora desta lista.

Sobre o quadro: quando a pessoa não disser em qual quadro a tarefa entra, mande
nome_do_quadro vazio, que o quadro padrão é usado. Se a pessoa tiver mais de um
quadro e a tarefa parecer de outro, pergunte em qual antes de criar.

Toda ferramenta devolve um campo "ok". Quando vier ok falso, leia o campo "erro",
explique em português simples o que aconteceu e diga o que a pessoa pode fazer.
Nunca invente que deu certo.

Quando a pessoa contar o que já fez durante o dia, mova as tarefas correspondentes
sem pedir confirmação. Para apagar, confirme antes: apagar não tem volta.
""",
    tools=[
        obter_data_de_hoje,
        listar_quadros,
        adicionar_tarefa,
        listar_tarefas,
        mudar_status_tarefa,
        remover_tarefa,
    ],
)
