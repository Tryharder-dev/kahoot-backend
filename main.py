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
clientes_ativos = []

class BotConfig(BaseModel):
    pin: int
    nome_base: str
    quantidade: int
    cor: Optional[str] = None
    atraso: Optional[float] = 1.5

class VotoManualConfig(BaseModel):
    cor: str

async def criar_bot_web(pin: int, nome: str, cor_estrategia: Optional[str], atraso_fixo: float, index_bot: int):
    cliente = KahootClient()
    cliente.pergunta_atual = 0  # Guarda o ID da pergunta atual para o voto manual
    clientes_ativos.append(cliente)

    async def ao_iniciar_pergunta(packet: QuestionStartPacket):
        cliente.pergunta_atual = packet.game_block_index
        
        # Se estiver no modo manual, o bot apenas aguarda a sua ordem e não faz nada sozinho
        if cor_estrategia == "manual":
            return
            
        # Sincronização Absoluta (Automático)
        micro_atraso = index_bot * 0.005 # 5ms entre cada bot para bater todos no mesmo segundo sem dar bloqueio
        atraso_final = 4.0 + atraso_fixo + micro_atraso
        
        await asyncio.sleep(atraso_final)
        
        escolha = CORES.get(cor_estrategia) if cor_estrategia in CORES else random.randint(0, 3)
        try:
            await cliente.send_packet(RespondPacket(cliente.game_pin, escolha, cliente.pergunta_atual))
        except Exception:
            pass

    cliente.on("question_start", ao_iniciar_pergunta)

    try:
        await cliente.join_game(pin, nome)
        while cliente in clientes_ativos:
            await asyncio.sleep(1)
    except Exception:
        pass
    finally:
        if cliente in clientes_ativos:
            clientes_ativos.remove(cliente)

@app.post("/conectar")
async def conectar(config: BotConfig):
    global clientes_ativos
    clientes_ativos.clear()

    for i in range(1, config.quantidade + 1):
        nome = f"{config.nome_base}{i}"
        asyncio.create_task(criar_bot_web(config.pin, nome, config.cor, config.atraso, i))

    return {"status": "sucesso", "mensagem": f"{config.quantidade} bots na sessão!"}

@app.post("/votar")
async def votar_ao_vivo(voto: VotoManualConfig):
    global clientes_ativos
    if not clientes_ativos:
        return {"status": "erro", "mensagem": "Nenhum bot conectado para votar."}
        
    cor_index = CORES.get(voto.cor.lower())
    if cor_index is None:
        return {"status": "erro", "mensagem": "Cor inválida."}

    votos_enviados = 0
    # Dispara a horda inteira quase simultaneamente
    for i, cliente in enumerate(clientes_ativos):
        async def enviar_voto(c, idx, id_pergunta):
            await asyncio.sleep(idx * 0.005) # Sincronização perfeita de 5ms
            try:
                await c.send_packet(RespondPacket(c.game_pin, cor_index, id_pergunta))
            except Exception:
                pass
        
        asyncio.create_task(enviar_voto(cliente, i, getattr(cliente, 'pergunta_atual', 0)))
        votos_enviados += 1

    return {"status": "sucesso", "mensagem": f"Ataque em massa: Voto {voto.cor.upper()} enviado!"}

@app.post("/desconectar")
async def modo_panico():
    global clientes_ativos
    quantidade = len(clientes_ativos)
    for cliente in list(clientes_ativos):
        try:
            await cliente.leave_game()
        except Exception:
            pass
    clientes_ativos.clear()
    return {"status": "sucesso", "mensagem": f"PÂNICO: {quantidade} bots desconectados."}
    
