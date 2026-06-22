import asyncio
import random
import urllib.request
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

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

class VotoManualConfig(BaseModel):
    cor: Optional[str] = None
    texto: Optional[str] = None
    lista: Optional[List[int]] = None  # Recebe a ordenação do Puzzle ex: [3, 0, 1, 2]
    tipo: Optional[str] = "alternativas"  # "alternativas", "vf", "texto", "puzzle"

class BotConfig(BaseModel):
    pin: int
    nome_base: str
    quantidade: int
    cor: Optional[str] = None
    atraso: Optional[float] = 1.5

def verificar_pin(pin: int) -> bool:
    try:
        req = urllib.request.Request(f"https://kahoot.it/reserve/session/{pin}/", headers={'User-Agent': 'Mozilla/5.0'})
        urllib.request.urlopen(req)
        return True
    except Exception:
        return False

async def criar_bot_web(pin: int, nome: str, cor_estrategia: Optional[str], atraso_fixo: float, index_bot: int):
    cliente = KahootClient()
    cliente.pergunta_atual = 0
    clientes_ativos.append(cliente)

    async def ao_iniciar_pergunta(packet: QuestionStartPacket):
        cliente.pergunta_atual = packet.game_block_index
        
        if cor_estrategia == "manual":
            return
            
        micro_atraso = index_bot * 0.005
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
            await asyncio.sleep(0.5)
    except Exception:
        pass
    finally:
        if cliente in clientes_ativos:
            clientes_ativos.remove(cliente)

@app.post("/conectar")
async def conectar(config: BotConfig):
    global clientes_ativos
    if not verificar_pin(config.pin):
        return {"status": "erro", "mensagem": "PIN INVÁLIDO. Verifique a sala."}
        
    clientes_ativos.clear()

    for i in range(1, config.quantidade + 1):
        nome = f"{config.nome_base}{i}"
        asyncio.create_task(criar_bot_web(config.pin, nome, config.cor, config.atraso, i))

    return {"status": "sucesso", "mensagem": f"{config.quantidade} bots injetados com sucesso!"}

@app.post("/votar")
async def votar_ao_vivo(voto: VotoManualConfig):
    global clientes_ativos
    if not clientes_ativos:
        return {"status": "erro", "mensagem": "Nenhum bot ativo no momento."}
        
    valor_final_resposta = None
    msg_log_terminal = ""

    # Sistema Inteligente de Mapeamento de Tipos de Questão
    if voto.tipo == "texto":
        valor_final_resposta = voto.texto
        msg_log_terminal = f"Responderam por extenso: '{voto.texto}'"
        
    elif voto.tipo == "vf":
        # CORREÇÃO DA INVERSÃO: No Kahoot True/False, o índice 0 é Verdadeiro e o 1 é Falso
        if voto.cor == "azul":
            valor_final_resposta = 0
            msg_log_terminal = "Votaram VERDADEIRO"
        elif voto.cor == "vermelho":
            valor_final_resposta = 1
            msg_log_terminal = "Votaram FALSO"
            
    elif voto.tipo == "puzzle":
        valor_final_resposta = voto.lista
        msg_log_terminal = f"Enviaram ordenação Puzzle: {voto.lista}"
        
    else:  # Alternativas / Múltipla Escolha Padrão
        valor_final_resposta = CORES.get(voto.cor.lower())
        if valor_final_resposta is None:
            return {"status": "erro", "mensagem": "Alternativa inválida."}
        msg_log_terminal = f"Votaram na cor {voto.cor.upper()}"

    # Disparo em massa assíncrono e ultra veloz
    for i, cliente in enumerate(clientes_ativos):
        async def disparar(c, idx, id_p, val):
            await asyncio.sleep(idx * 0.002)
            try:
                await c.send_packet(RespondPacket(c.game_pin, val, id_p))
            except:
                pass
        asyncio.create_task(disparar(cliente, i, getattr(cliente, 'pergunta_atual', 0), valor_final_resposta))

    return {"status": "sucesso", "mensagem": msg_log_terminal}

@app.post("/desconectar")
async def expulsar_bots():
    global clientes_ativos
    quantidade = len(clientes_ativos)
    
    if quantity_to_kill := len(clientes_ativos):
        alvos = list(clientes_ativos)
        clientes_ativos.clear()  # Corta loops imediatos de sustentação
        
        async def matar_sockets(lista):
            for bot in lista:
                try:
                    # Força o desligamento direto da conexão TCP/WS subjacente
                    if hasattr(bot, 'ws') and bot.ws:
                        await bot.ws.close()
                    if hasattr(bot, 'socket') and bot.socket:
                        await bot.socket.close()
                except: pass
                try:
                    if hasattr(bot, 'leave'): await bot.leave()
                except: pass

        asyncio.create_task(matar_sockets(alvos))
        
    return {"status": "sucesso", "mensagem": f"EXPULSÃO DEFINITIVA: {quantidade} conexões terminadas."}
        
