import json
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.messages import HumanMessage
from schemas import TAISAResponse

# ==========================================
# 1. DEFINIÇÃO DAS TOOLS (As habilidades da TAISA)
# ==========================================

@tool
def buscar_status_comex(invoice_number: str) -> str:
    """Busca o status aduaneiro e logístico de uma carga usando o número da Invoice (ex: INV-229910)."""
    
    print(f"\n[LOG BACKEND] 🛠️ Tool Acionada! Buscando no ERP a invoice: {invoice_number}")
    
    # Nosso banco de dados fake (Mock)
    mocks = {
        "INV-229910": {
            "channel": "RED",
            "priority": "CRITICAL",
            "reason": "Divergência de NCM",
            "pending_action": "Apresentar laudo técnico do produto"
        },
        "INV-112233": {
            "channel": "GREEN",
            "priority": "LOW",
            "reason": "Desembaraço automático, tudo certo.",
            "pending_action": "Nenhuma"
        }
    }
    
    # Busca a invoice no mock ignorando maiúsculas/minúsculas
    data = mocks.get(invoice_number.upper(), {"error": f"Invoice {invoice_number} não encontrada no sistema."})
    return json.dumps(data)


# ==========================================
# 2. CONFIGURAÇÃO DA IA E DO PARSER
# ==========================================

llm = ChatOllama(model="llama3.1", temperature=0.1)

# Conectamos a ferramenta ao Cérebro da IA
llm_with_tools = llm.bind_tools([buscar_status_comex])

parser = JsonOutputParser(pydantic_object=TAISAResponse)

final_prompt = ChatPromptTemplate.from_messages([
    ("system", """Você é a TAISA, uma assistente de Supply Chain.
    
    REGRAS DE UI:
    - RED = level 'critical', channel_color 'red'
    - YELLOW = level 'warning', channel_color 'yellow'
    - GREEN = level 'info', channel_color 'green'
    - Se houver erro, crie um componente informando que não encontrou.
    
    INSTRUÇÕES DE SAÍDA:
    Responda obrigatoriamente no formato JSON:
    {format_instructions}
    """),
    ("user", "Pergunta original: {user_query}\n\nDados brutos retornados pelo ERP: {tool_data}")
])

final_chain = final_prompt | llm | parser

# ==========================================
# 3. O ORQUESTRADOR (Two-Pass)
# ==========================================

def process_chat(user_query: str):
    print(f"\n[LOG BACKEND] 🗣️ Usuário perguntou: {user_query}")
    
    # --- PASSO 1: O Llama decide se usa a Tool e extrai parâmetros ---
    messages = [HumanMessage(content=user_query)]
    ai_msg = llm_with_tools.invoke(messages)
    
    tool_data = "Nenhum dado consultado."
    
    # Verifica se a IA decidiu usar alguma ferramenta
    if ai_msg.tool_calls:
        for tool_call in ai_msg.tool_calls:
            if tool_call["name"] == "buscar_status_comex":
                # A IA extraiu o argumento da frase!
                invoice_arg = tool_call["args"]["invoice_number"]
                # Executa a função Python real com o argumento que a IA achou
                tool_data = buscar_status_comex.invoke({"invoice_number": invoice_arg})
    else:
        tool_data = "Nenhum sistema acionado. Pode ser apenas uma saudação ou pergunta genérica."

    print(f"[LOG BACKEND] 📦 Dados que o ERP devolveu para a IA: {tool_data}")

    # --- PASSO 2: A IA formata a resposta baseada nos dados encontrados ---
    response = final_chain.invoke({
        "user_query": user_query,
        "tool_data": tool_data,
        "format_instructions": parser.get_format_instructions()
    })
    
    return response