from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn
from agent import process_chat

app = FastAPI(title="TAISA Backend Mock API")

class ChatRequest(BaseModel):
    query: str

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    # Chama a chain do LangChain com a pergunta do usuário
    resultado_estruturado = process_chat(request.query)
    
    # O FastAPI automaticamente converte o dict/Pydantic em JSON para o React
    return resultado_estruturado

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
    