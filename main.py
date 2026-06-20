import asyncio
import random
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

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

# Rastreamento global definitivo para o Botão de Pânico
clientes_ativos = []

class BotConfig(BaseModel):
    pin: int
    nome_base: str
    quantidade: int
    cor: Optional[str] = None
    atraso: Optional[float] = 1.5

async def criar_bot_web(pin: int, nome: str, cor_index: Optional[int], atraso_fixo: float, index_bot: int):
    cliente = KahootClient()
    clientes_ativos.append(cliente)

    async def ao_iniciar_pergunta(packet: QuestionStartPacket):
        numero_pergunta: int = packet.game_block_index
        tempo_base_kahoot = 4.0  # Tempo de espera da animação de introdução da pergunta
        
        # Micro-escalonamento para burlar o bloqueio de IP do Kahoot
        # Cria uma fila milimétrica de milissegundos entre os bots
        micro_atraso = index_bot * 0.025
        atraso_final = tempo_base_kahoot + atraso_fixo + micro_atraso
        
        await asyncio.sleep(atraso_final)
        escolha = cor_index if cor_index is not None else random.randint(0, 3)

        try:
            await cliente.send_packet(RespondPacket(cliente.game_pin, escolha, numero_pergunta))
        except Exception:
            pass

    cliente.on("question_start", ao_iniciar_pergunta)

    try:
        await cliente.join_game(pin, nome)
        # Mantém o bot vivo enquanto ele estiver na lista global de ativos
        while cliente in clientes_ativos:
            await asyncio.sleep(1)
    except Exception:
        pass
    finally:
        if cliente in clientes_ativos:
            clientes_ativos.remove(cliente)

@app.post("/conectar")
async def conectar(config: BotConfig):
    # Garante limpeza de sessões fantasmas anteriores antes de reatar
    global clientes_ativos
    clientes_ativos.clear()

    cor_index = CORES.get(config.cor.lower()) if config.cor else None

    for i in range(1, config.quantidade + 1):
        nome = f"{config.nome_base}{i}"
        # Dispara os bots passando o seu índice na fila para o micro-escalonamento
        asyncio.create_task(criar_bot_web(config.pin, nome, cor_index, config.atraso, i))

    return {"status": "sucesso", "mensagem": f"{config.quantidade} bots preparados na fila de injeção!"}

@app.post("/desconectar")
async def modo_panico():
    global clientes_ativos
    if not clientes_ativos:
        return {"status": "aviso", "mensagem": "Nenhum bot ativo encontrado no servidor."}

    quantidade_derrubada = len(clientes_ativos)
    
    # Executa desconexão forçada na raiz do protocolo de rede
    for cliente in list(clientes_ativos):
        try:
            await cliente.leave_game()
        except Exception:
            pass
            
    clientes_ativos.clear()
    return {"status": "sucesso", "mensagem": f"PÂNICO EXECITADO! {quantidade_derrubada} conexões encerradas."}
    
