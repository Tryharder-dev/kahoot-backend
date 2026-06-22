import asyncio
import random
import urllib.request
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

# Payload adaptado para receber o tipo de painel ativo no frontend
class VotoManualConfig(BaseModel):
    cor: Optional[str] = None
    texto: Optional[str] = None
    tipo: Optional[str] = "alternativas" # "alternativas", "vf", "texto"

class BotConfig(BaseModel):
    pin: int
    nome_base: str
    quantidade: int
    cor: Optional[str] = None
    atraso: Optional[float] = 1.5

def verificar_pin(pin: int) -> bool:
    """Valida o PIN diretamente nos servidores do Kahoot antes de prosseguir."""
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
        # O bot permanece vivo enquanto estiver na lista global
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
        return {"status": "erro", "mensagem": "PIN INVÁLIDO. Verifique os números ou se a sala está aberta."}
        
    clientes_ativos.clear()

    for i in range(1, config.quantidade + 1):
        nome = f"{config.nome_base}{i}"
        asyncio.create_task(criar_bot_web(config.pin, nome, config.cor, config.atraso, i))

    return {"status": "sucesso", "mensagem": f"{config.quantidade} bots injetados na sessão!"}

@app.post("/votar")
async def votar_ao_vivo(voto: VotoManualConfig):
    global clientes_ativos
    if not clientes_ativos:
        return {"status": "erro", "mensagem": "Nenhum bot conectado para receber ordens."}
        
    valor_final_resposta = None
    msg_log_terminal = ""

    # Tratamento baseado no tipo de pergunta selecionada pelo painel
    if voto.tipo == "texto":
        valor_final_resposta = voto.texto
        msg_log_terminal = f"Responderam por extenso: '{voto.texto}'"
        
    elif voto.tipo == "vf":
        # Correção estrita da inversão: Verdadeiro = Azul (Índice 1), Falso = Vermelho (Índice 0)
        if voto.cor == "azul":
            valor_final_resposta = 1
            msg_log_terminal = "Votaram VERDADEIRO"
        elif voto.cor == "vermelho":
            valor_final_resposta = 0
            msg_log_terminal = "Votaram FALSO"
            
    else: # alternativas / multipla escolha
        valor_final_resposta = CORES.get(voto.cor.lower())
        if valor_final_resposta is None:
            return {"status": "erro", "mensagem": "Cor de alternativa inválida."}
        msg_log_terminal = f"Votaram na cor {voto.cor.upper()}"

    # Dispara os pacotes em paralelo de forma imediata
    for i, cliente in enumerate(clientes_ativos):
        async def disparar(c, idx, id_p, val):
            await asyncio.sleep(idx * 0.002)
            try:
                await c.send_packet(RespondPacket(c.game_pin, val, id_p))
            except Exception:
                pass
        asyncio.create_task(disparar(cliente, i, getattr(cliente, 'pergunta_atual', 0), valor_final_resposta))

    return {"status": "sucesso", "mensagem": f"{msg_log_terminal}"}

@app.post("/desconectar")
async def expulsar_bots():
    global clientes_ativos
    quantidade = len(clientes_ativos)
    
    if quantidade > 0:
        bots_alvo = list(clientes_ativos)
        # Limpa imediatamente a lista síncrona. Isso quebra o laço 'while cliente in clientes_ativos' instantaneamente
        clientes_ativos.clear()
        
        # Função isolada para fechar conexões em segundo plano (evita timeouts HTTP no Render)
        async def desativar_sockets(lista_bots):
            for bot in lista_bots:
                try:
                    # Força o encerramento do protocolo WebSocket subjacente
                    if hasattr(bot, 'ws') and bot.ws:
                        await bot.ws.close()
                except:
                    pass
                try:
                    # Executa métodos de saída da biblioteca de forma não bloqueante
                    if hasattr(bot, 'leave_game'):
                        asyncio.create_task(bot.leave_game())
                    elif hasattr(bot, 'leave'):
                        asyncio.create_task(bot.leave())
                except:
                    pass

        asyncio.create_task(desativar_sockets(bots_alvo))
        
    return {"status": "sucesso", "mensagem": f"EXPULSÃO TERMINAL: {quantidade} bots eliminados com sucesso."}
        
