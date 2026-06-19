import asyncio
import random
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict

try:
    from kahoot import KahootClient
    from kahoot.packets.impl.respond import RespondPacket
    from kahoot.packets.server.question_start import QuestionStartPacket
except ImportError:
    pass

app = FastAPI()

# Permite que o seu site no Vercel acesse o Render sem bloqueios de segurança
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CORES = {"vermelho": 0, "azul": 1, "amarelo": 2, "verde": 3}
jogos_ativos: Dict[int, list] = {}

class BotConfig(BaseModel):
    pin: int
    nome_base: str
    quantidade: int
    cor: Optional[str] = None
    atraso: Optional[float] = 1.5

async def rodar_bot_individual(pin, nome, cor_index, atraso_fixo):
    cliente = KahootClient()
    
    async def ao_iniciar_pergunta(packet: QuestionStartPacket):
        numero_pergunta = packet.game_block_index
        tempo_base_leitura = 4.0
        await asyncio.sleep(tempo_base_leitura + atraso_fixo)
        
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
        try:
            if hasattr(cliente, 'ws') and cliente.ws:
                await cliente.ws.close()
        except Exception:
            pass

@app.post("/conectar")
async def conectar_bots(config: BotConfig):
    if config.pin in jogos_ativos:
        await desconectar_bots(config.pin)

    cor_index = CORES.get(config.cor.lower()) if config.cor else None
    jogos_ativos[config.pin] = []

    for i in range(1, config.quantidade + 1):
        nome_completo = f"{config.nome_base}{i}"
        tarefa = asyncio.create_task(
            rodar_bot_individual(config.pin, nome_completo, cor_index, config.atraso)
        )
        jogos_ativos[config.pin].append(tarefa)

    return {"status": "sucesso", "mensagem": f"{config.quantidade} bots enviados!"}

@app.post("/desconectar/{pin}")
async def desconectar_bots(pin: int):
    if pin not in jogos_ativos or not jogos_ativos[pin]:
        return {"status": "aviso", "mensagem": "Nenhum bot ativo."}

    for tarefa in jogos_ativos[pin]:
        tarefa.cancel()
    
    await asyncio.gather(*jogos_ativos[pin], return_exceptions=True)
    jogos_ativos[pin] = []
    return {"status": "sucesso", "mensagem": "Modo pânico ativado! Bots removidos."}
      
