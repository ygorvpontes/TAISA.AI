import json
import os
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.messages import HumanMessage
from schemas import TAISAResponse

# ==========================================
# IMPORTAÇÃO DO MÓDULO DE GREEN LIGHT (Data Engine)
# ==========================================
from data_engine import run_green_light_pipeline


# ==========================================
# 1. DEFINIÇÃO DAS TOOLS (As habilidades da TAISA)
# ==========================================

@tool
def buscar_status_comex(invoice_number: str) -> str:
    """Busca o status aduaneiro e logístico de uma carga usando o número da Invoice (ex: INV-229910)."""
    
    print(f"\n[LOG BACKEND] 🛠️ Tool Acionada! Buscando no ERP a invoice: {invoice_number}")
    
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
    
    data = mocks.get(invoice_number.upper(), {"error": f"Invoice {invoice_number} não encontrada no sistema."})
    return json.dumps(data)


@tool
def gerar_green_light(invoice_numbers: list, fonte: str = "STO") -> str:
    """
    ÚTIL PARA: Gerar relatórios de Green Light, checar regras regulatórias (ANVISA), travas de preço ou Check Points de compliance para exportação/importação.
    COMO USAR: Passe uma lista de números de invoices (faturas). Exemplo: ["1090748838"]
    Opcional: Passe fonte="BILL2" caso o usuário peça explicitamente na base antiga, senão o padrão é "STO".
    """
    
    print(f"\n[LOG BACKEND] 🚦 Tool de Green Light Acionada! Invoices: {invoice_numbers} | Fonte: {fonte}")
    
    try:
        df = run_green_light_pipeline(invoice_numbers, fonte)
        
        if df.empty:
            return json.dumps({"error": f"Nenhuma invoice {invoice_numbers} encontrada na base {fonte}."})
            
        total_itens = len(df)
        valor_total = round(df['Extended Price'].sum(), 2)
        alertas = df['Check Point'].value_counts().to_dict()
        
        resultado = {
            "status": "sucesso",
            "invoices": invoice_numbers,
            "total_linhas_processadas": total_itens,
            "valor_total_faturado": valor_total,
            "resumo_check_points": alertas,
            "acao_gerada": f"Arquivo {invoice_numbers[0]}_{fonte}_GL.xlsx salvo na pasta output e pronto para download."
        }
        
        return json.dumps(resultado)
        
    except Exception as e:
        return json.dumps({"error": f"Erro interno no motor Python: {str(e)}"})


# ==========================================
# 2. CONFIGURAÇÃO DA IA E DO PARSER
# ==========================================

GROQ_KEY = "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".strip()
os.environ["GROQ_API_KEY"] = GROQ_KEY

# Usando um modelo garantido pela sua tabela de limites da conta
llm = ChatGroq(
    model="openai/gpt-oss-20b", 
    api_key=GROQ_KEY,
    temperature=0.1
)

llm_with_tools = llm.bind_tools([buscar_status_comex, gerar_green_light])

parser = JsonOutputParser(pydantic_object=TAISAResponse)

final_prompt = ChatPromptTemplate.from_messages([
    ("system", """Você é a TAISA, uma assistente inteligente de Supply Chain e Comércio Exterior.
    
    REGRAS DE COMPONENTES VISUAIS (UI):
    - Se encontrar travas/alertas regulatórios ou operacionais, use alert_level = 'critical' e channel_color = 'red' ou 'yellow'.
    - Se estiver tudo 100% liberado ("Green Light Autorizado" absoluto), use alert_level = 'info' e channel_color = 'green'.
    - Se a ferramenta devolver erro ou invoice não encontrada, gere um card de alerta.
    
    INSTRUÇÕES DE SAÍDA:
    Seja executiva e profissional na resposta textual.
    Responda obrigatoriamente e apenas no formato JSON, sem marcações markdown como ```json no início ou no fim:
    {format_instructions}
    """),
    ("user", "Pergunta do analista: {user_query}\n\nDados brutos de sistema retornados pelas Tools: {tool_data}")
])

final_chain = final_prompt | llm | parser


# ==========================================
# 3. O ORQUESTRADOR (Two-Pass)
# ==========================================

def process_chat(user_query: str):
    print(f"\n[LOG BACKEND] 🗣️ Usuário: {user_query}")
    
    messages = [HumanMessage(content=user_query)]
    ai_msg = llm_with_tools.invoke(messages)
    
    tool_data = "Nenhuma ação de sistema necessária para esta mensagem."
    
    if ai_msg.tool_calls:
        tool_data_list = []
        
        for tool_call in ai_msg.tool_calls:
            nome_da_tool = tool_call["name"]
            argumentos = tool_call["args"]
            
            if nome_da_tool == "buscar_status_comex":
                retorno = buscar_status_comex.invoke(argumentos)
                tool_data_list.append(f"[Status Comex]: {retorno}")
                
            elif nome_da_tool == "gerar_green_light":
                retorno = gerar_green_light.invoke(argumentos)
                tool_data_list.append(f"[Relatório Green Light]: {retorno}")
                
        tool_data = " \n".join(tool_data_list)
        
    print(f"[LOG BACKEND] 📦 Informação crua enviada para a IA formatar:\n{tool_data}")

    try:
        response = final_chain.invoke({
            "user_query": user_query,
            "tool_data": tool_data,
            "format_instructions": parser.get_format_instructions()
        })
        return response
    except Exception as e:
        print(f"[ERRO DE PARSING JSON]: {e}")
        return {"error": "Falha ao estruturar o JSON de resposta da TAISA."}