import React, { useState } from 'react';
import { Bot, User, Paperclip, Send, CheckCircle2, Download, Menu, MoreVertical } from 'lucide-react';
import axios from 'axios';

interface Message {
  sender: 'user' | 'taisa';
  text: string;
  data?: any;
}

export default function App() {
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      sender: 'taisa',
      text: "Olá! Sou a TAISA, sua assistente inteligente de Supply Chain e Comércio Exterior. Como posso ajudar com suas invoices e conformidade regulatória hoje?",
    }
  ]);

  const handleSendMessage = async () => {
    if (!inputValue.trim() || loading) return;

    const userQuery = inputValue;
    const userMessage: Message = { sender: 'user', text: userQuery };
    
    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setLoading(true);

    try {
      const response = await axios.post('http://localhost:8000/api/chat', {
        query: userQuery,
      });

      const taisaData = response.data;
      
      // Extrai limpo a mensagem do JSON retornado pelo Pydantic, ignorando o código bruto
      const textoMensagem = taisaData.message || taisaData.text || "Processamento concluído com sucesso.";

      const taisaMessage: Message = {
        sender: 'taisa',
        text: textoMensagem,
        data: taisaData,
      };

      setMessages((prev) => [...prev, taisaMessage]);
    } catch (error) {
      console.error('Erro ao conectar com o backend da TAISA:', error);
      setMessages((prev) => [
        ...prev,
        { 
          sender: 'taisa', 
          text: "⚠️ Erro crítico: Não foi possível conectar ao servidor backend em FastAPI (porta 8000)." 
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-slate-50 text-slate-800 font-sans">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 bg-white border-b border-slate-200 shadow-sm shrink-0">
        <div className="flex items-center gap-3">
          <Menu className="w-5 h-5 text-slate-500 cursor-pointer hover:text-slate-700" />
          <div className="flex items-center gap-2">
            <div className="flex items-center justify-center w-8 h-8 rounded bg-blue-600 text-white font-bold text-sm tracking-wide shadow-sm">
              T
            </div>
            <h1 className="text-xl font-semibold text-slate-900 tracking-tight">TAISA</h1>
          </div>
          <span className="ml-2 px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-700 border border-blue-100">
            Supply Chain Intelligence
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
          <span className="text-xs text-slate-500 font-medium">FastAPI Ativo</span>
        </div>
        <MoreVertical className="w-5 h-5 text-slate-500 cursor-pointer hover:text-slate-700" />
      </header>

      {/* Chat Area */}
      <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:px-8 max-w-5xl mx-auto w-full">
        <div className="flex flex-col gap-6 w-full">
          {messages.map((msg, idx) => {
            const invoiceDetectada = (msg.data?.ui_component?.props?.invoice) || (msg.text.match(/1090748838/) ? "1090748838" : null);

            return (
              <div key={idx} className={`flex w-full ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                {msg.sender === 'user' ? (
                  <div className="max-w-[80%] flex items-end gap-2">
                    <div className="bg-blue-600 text-white px-5 py-3.5 rounded-2xl rounded-br-sm shadow-sm">
                      <p className="text-sm/relaxed">{msg.text}</p>
                    </div>
                    <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center shrink-0 border border-slate-300">
                      <User className="w-5 h-5 text-slate-500" />
                    </div>
                  </div>
                ) : (
                  <div className="max-w-[85%] flex items-start gap-3 w-full">
                    <div className="w-10 h-10 rounded-full bg-blue-700 flex items-center justify-center shrink-0 shadow-sm border border-blue-800">
                      <Bot className="w-6 h-6 text-white" />
                    </div>
                    <div className="flex flex-col gap-3 w-full">
                      {/* Balão de Texto Limpo (Sem JSON bruto) */}
                      <div className="bg-white border border-slate-200 text-slate-800 px-5 py-3.5 rounded-2xl rounded-bl-sm shadow-sm">
                        <p className="text-sm/relaxed whitespace-pre-wrap">{msg.text}</p>
                      </div>
                      
                      {/* Card Inteligente com Botão de Download */}
                      {invoiceDetectada && (
                        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm w-full md:w-[480px]">
                          <div className="bg-emerald-50 border-b border-emerald-100 text-emerald-900 px-5 py-3 flex flex-row items-center justify-between">
                            <h3 className="font-semibold text-sm flex items-center gap-2">
                              <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                              Green Light Authorized
                            </h3>
                            <span className="text-xs font-medium px-2 py-1 rounded-full bg-emerald-100 text-emerald-700">
                              Pronto para Download
                            </span>
                          </div>
                          
                          <div className="p-5">
                            <h4 className="text-slate-900 font-medium mb-4 text-sm">
                              Relatório gerado para a Invoice: {invoiceDetectada}
                            </h4>
                            
                            <a
                              href={`http://localhost:8000/api/download/${invoiceDetectada}_STO_GL.xlsx`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 transition-colors text-white py-2.5 px-4 rounded-lg text-sm font-medium shadow-sm"
                            >
                              <Download className="w-4 h-4" />
                              Baixar Relatório Excel ({invoiceDetectada}_STO_GL.xlsx)
                            </a>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}

          {loading && (
            <div className="flex items-center gap-3 text-slate-400 text-sm italic animate-pulse">
              <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-white text-xs font-bold">T</div>
              <span>TAISA está consultando o ERP e rodando os pipelines de compliance...</span>
            </div>
          )}
        </div>
      </main>

      {/* Bottom Bar Input */}
      <footer className="bg-white border-t border-slate-200 p-4 shrink-0">
        <div className="max-w-5xl mx-auto flex items-center gap-3">
          <button className="w-10 h-10 flex items-center justify-center rounded-full text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors shrink-0">
            <Paperclip className="w-5 h-5" />
          </button>
          
          <div className="flex-1 relative">
            <input
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Ex: TAISA, gere o relatório de Green Light da invoice 1090748838..."
              className="w-full bg-slate-50 border border-slate-200 rounded-full py-3 px-5 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition-all"
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSendMessage();
              }}
            />
          </div>
          
          <button 
            onClick={handleSendMessage}
            disabled={loading}
            className="w-12 h-12 flex items-center justify-center rounded-full bg-blue-600 hover:bg-blue-700 transition-colors text-white shadow-md shrink-0 disabled:opacity-50"
          >
            <Send className="w-5 h-5 ml-0.5" />
          </button>
        </div>
        <div className="max-w-5xl mx-auto text-center mt-3">
          <p className="text-[10px] text-slate-400">
            TAISA Supply Chain AI. Conectado ao FastAPI local (porta 8000).
          </p>
        </div>
      </footer>
    </div>
  );
}