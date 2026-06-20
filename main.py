import asyncio
import random
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict
import os

# Suas importações estáveis da v17
from kahoot import KahootClient
from kahoot.packets.impl.respond import RespondPacket
from kahoot.packets.server.question_start import QuestionStartPacket

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CORES = {"vermelho": 0, "azul": 1, "amarelo": 2, "verde": 3}
# Guarda as tarefas dos bots ativos em background
jogos_ativos: Dict[int, list] = {}

class BotConfig(BaseModel):
    pin: int
    nome_base: str
    quantidade: int
    cor: Optional[str] = None
    atraso: Optional[float] = 1.5

async def criar_bot_web(pin: int, nome: str, cor_index: Optional[int], atraso_fixo: float):
    cliente = KahootClient()

    async def ao_iniciar_pergunta(packet: QuestionStartPacket):
        numero_pergunta: int = packet.game_block_index
        tempo_base_leitura = 4.0
        atraso_real = tempo_base_leitura + atraso_fixo
        
        await asyncio.sleep(atraso_real)
        escolha = cor_index if cor_index is not None else random.randint(0, 3)

        try:
            await cliente.send_packet(RespondPacket(cliente.game_pin, escolha, numero_pergunta))
        except Exception:
            pass

    cliente.on("question_start", ao_iniciar_pergunta)

    try:
        await cliente.join_game(pin, nome)
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        # Quando o pânico cancela a tarefa, desconecta o WebSocket de forma limpa
        try:
            await cliente.leave_game()
        except Exception:
            pass
    except Exception:
        pass

@app.post("/conectar")
async def conectar(config: BotConfig):
    if config.pin in jogos_ativos:
        await modo_panico(config.pin)

    cor_index = CORES.get(config.cor.lower()) if config.cor else None
    jogos_ativos[config.pin] = []

    for i in range(1, config.quantidade + 1):
        nome = f"{config.nome_base}{i}"
        tarefa = asyncio.create_task(criar_bot_web(config.pin, nome, cor_index, config.atraso))
        jogos_ativos[config.pin].append(tarefa)

    return {"status": "sucesso", "mensagem": f"{config.quantidade} bots enviados simultaneamente!"}

@app.post("/desconectar/{pin}")
async def modo_panico(pin: int):
    if pin not in jogos_ativos or not jogos_ativos[pin]:
        return {"status": "aviso", "mensagem": "Nenhum bot ativo para este PIN."}

    # Executa o botão de pânico cancelando todas as conexões assíncronas de uma vez
    for tarefa in jogos_ativos[pin]:
        tarefa.cancel()
        
    await asyncio.gather(*jogos_ativos[pin], return_exceptions=True)
    jogos_ativos[pin] = []
    
    return {"status": "sucesso", "mensagem": "PÂNICO! Todos os bots foram desconectados."}
    
