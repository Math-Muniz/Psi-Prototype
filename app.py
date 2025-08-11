import os
import streamlit as st
from dotenv import load_dotenv
from typing import TypedDict, Annotated, Sequence, Set
from langgraph.graph import StateGraph
from langchain_groq import ChatGroq
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph.message import add_messages
from prompts import prompt_pre_contemplacao, prompt_contemplacao, prompt_avaliador

# --- Configuração Inicial e Carregamento de Chaves ---
load_dotenv()

# --- Configuração do LLM ---
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=os.getenv("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY"),
    temperature=0.2
)

# --- Definição do Estado e Constantes (Lógica do Agente) ---
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    stage: str
    tecnicas_utilizadas: Set[str]

TECNICAS_REQUERIDAS = {
    "PERGUNTAS_ABERTAS", "ESCUTA_REFLEXIVA", "REFORCO_AUTOEFICACIA", "RESUMO", "MENU_DE_OPCOES"
}

# --- Preparação dos Prompts de Sistema ---
pre_contemplacao_message = SystemMessage(content=prompt_pre_contemplacao)
contemplacao_message = SystemMessage(content=prompt_contemplacao)

# --- Definição dos Nós de Ação (Paciente) ---
@st.cache_resource
def get_compiled_agent():
    """Compila e retorna o agente LangGraph, usando o cache para performance."""
    
    def call_pre_contemplacao(state: AgentState) -> dict:
        response = llm.invoke([pre_contemplacao_message] + state["messages"])
        return {"messages": [response]}

    def call_contemplacao(state: AgentState) -> dict:
        response = llm.invoke([contemplacao_message] + state["messages"])
        return {"messages": [response]}

    def route_by_stage(state: AgentState) -> str:
        return state["stage"]

    graph = StateGraph(AgentState)
    graph.add_node("pre_contemplacao", call_pre_contemplacao)
    graph.add_node("contemplacao", call_contemplacao)
    graph.add_conditional_edges(
        "__start__",
        route_by_stage,
        {"pre_contemplacao": "pre_contemplacao", "contemplacao": "contemplacao"}
    )
    graph.add_edge("pre_contemplacao", "__end__")
    graph.add_edge("contemplacao", "__end__")
    
    return graph.compile()

agent = get_compiled_agent()

# --- Função de Avaliação ---
def evaluate_user_turn(state: AgentState) -> Set[str]:
    """Chama o LLM para avaliar a última fala do usuário."""
    conversation_text = "\n".join([f"{msg.type}: {msg.content}" for msg in state['messages']])
    prompt = prompt_avaliador.format(conversation_text=conversation_text)
    evaluation = llm.invoke(prompt)
    
    raw_response = evaluation.content.strip().upper()
    if raw_response and raw_response != "NENHUMA":
        return {tech.strip() for tech in raw_response.split(',')}
    return set()

# --- Interface Gráfica com Streamlit ---

st.set_page_config(page_title="Simulador de Entrevista", layout="centered")

st.title("🤖 Simulador de Entrevista Motivacional")
st.markdown("Converse com um paciente simulado, e pratique suas habilidades de entrevista.")

# Inicialização do estado da sessão do Streamlit
if "current_state" not in st.session_state:
    # Mensagem inicial de Mário
    initial_ai_message = AIMessage(content="Olá, sou Mário.")
    
    st.session_state.current_state = {
        "messages": [initial_ai_message],
        "stage": "pre_contemplacao",
        "tecnicas_utilizadas": set()
    }
    # Inicializa o log detalhado na memória da sessão
    st.session_state.detailed_log = [
        {"message": initial_ai_message, "evaluation": None}
    ]

# --- Painel Lateral (Sidebar) ---
with st.sidebar:
    # --- PAINEL DE ANÁLISE ---
    st.header("📊 Análise da Sessão")
    stage = st.session_state.current_state["stage"]
    tecnicas = st.session_state.current_state["tecnicas_utilizadas"]
    
    if stage == "pre_contemplacao":
        st.subheader("Estágio Atual: Pré-Contemplação")
        st.write("Objetivo: Ajudar Mário a reconhecer a ambivalência.")
        st.progress(len(tecnicas) / len(TECNICAS_REQUERIDAS))
        st.write(f"**Técnicas Utilizadas: {len(tecnicas)} de {len(TECNICAS_REQUERIDAS)}**")
        
        for tecnica in sorted(list(TECNICAS_REQUERIDAS)):
            st.checkbox(tecnica, value=(tecnica in tecnicas), disabled=True)
            
    elif stage == "contemplacao":
        st.subheader("Estágio Atual: Contemplação")
        st.success("🎉 META ATINGIDA! Mário está refletindo sobre a mudança.")
        st.write("Objetivo: Ajudar Mário a resolver a ambivalência e fortalecer a motivação.")

    st.divider()

    # --- PAINEL DE OPÇÕES ---
    st.header("⚙️ Opções")

    # Função para formatar o log para download
    def format_log_for_download(log_data):
        """Formata a lista de log em uma string para download."""
        log_string = "Log da Conversa com Análise de Técnicas:\n\n"
        for entry in log_data:
            message = entry["message"]
            evaluation = entry["evaluation"]

            if isinstance(message, HumanMessage):
                log_string += f"Usuário: {message.content}\n"
                if evaluation is not None:
                    if evaluation:
                        log_string += f"  [Técnicas Identificadas: {', '.join(sorted(list(evaluation)))}]\n"
                    else:
                        log_string += "  [Técnicas Identificadas: Nenhuma]\n"
            
            elif isinstance(message, AIMessage):
                log_string += f"Mário: {message.content}\n\n"
        
        log_string += "\nFim do log."
        return log_string

    # Botão para salvar a conversa
    log_text_data = format_log_for_download(st.session_state.detailed_log)
    st.download_button(
        label="📄 Salvar Conversa",
        data=log_text_data.encode('utf-8'),
        file_name="Entrevista.txt",
        mime="text/plain"
    )

    # Salvar Grafo
    st.download_button(
        label="📈 Salvar Grafo do Agente",
        data=agent.get_graph().draw_mermaid_png(),
        file_name="workflow_agente.png",
        mime="image/png"
    )

    # Botão para reiniciar a simulação
    if st.button("🔄 Reiniciar Simulação"):
        st.session_state.clear()
        st.rerun()

# --- Interface de Chat Principal ---
for msg in st.session_state.current_state["messages"]:
    if isinstance(msg, AIMessage):
        st.chat_message("assistant", avatar="🧑‍🦱").write(msg.content)
    elif isinstance(msg, HumanMessage):
        st.chat_message("user", avatar="🧑‍⚕️").write(msg.content)

if prompt := st.chat_input("Digite sua resposta aqui..."):
    human_message = HumanMessage(content=prompt)
    st.session_state.current_state["messages"].append(human_message)
    st.chat_message("user", avatar="🧑‍⚕️").write(prompt)

    turn_evaluation = None
    if st.session_state.current_state["stage"] == "pre_contemplacao":
        with st.status("Avaliando técnicas..."):
            novas_tecnicas = evaluate_user_turn(st.session_state.current_state)
            st.session_state.current_state["tecnicas_utilizadas"].update(novas_tecnicas)
            turn_evaluation = novas_tecnicas
            if TECNICAS_REQUERIDAS.issubset(st.session_state.current_state["tecnicas_utilizadas"]):
                st.session_state.current_state["stage"] = "contemplacao"

    # Adiciona a fala do usuário e sua avaliação ao log detalhado
    st.session_state.detailed_log.append({"message": human_message, "evaluation": turn_evaluation})

    with st.spinner("Mário está pensando..."):
        try:
            result = agent.invoke(st.session_state.current_state)
            st.session_state.current_state = result
        except Exception as e:
            st.error(f"Ocorreu um erro ao contatar o modelo: {e}")
            st.session_state.current_state["messages"].pop()
            st.session_state.detailed_log.pop()

    ai_response = st.session_state.current_state["messages"][-1]
    # Adiciona a resposta da IA ao log detalhado
    st.session_state.detailed_log.append({"message": ai_response, "evaluation": None})
    

    st.rerun()
