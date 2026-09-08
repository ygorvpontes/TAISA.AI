from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import os
from agent import process_chat

app = FastAPI(title="TAISA Backend API - Supply Chain")

# Configuração de CORS para permitir que o React (Vite) acesse o FastAPI sem bloqueios
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite qualquer origem em ambiente de desenvolvimento local
    allow_credentials=True,
    allow_methods=["*"],  # Permite GET, POST, OPTIONS, etc.
    allow_headers=["*"],
)

OUTPUT_DIR = "output"

class ChatRequest(BaseModel):
    query: str

@app.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    resultado_estruturado = process_chat(request.query)
    return resultado_estruturado

@app.get("/api/download/{filename}")
async def download_excel(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    
    if os.path.exists(file_path):
        return FileResponse(
            path=file_path, 
            filename=filename, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    raise HTTPException(status_code=404, detail="Arquivo não encontrado ou expirado.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)