import sys
# Desativa verificações de tipo que causam erro no Python moderno
sys.modules['typing.Union'] = None 

import asyncio
import random
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict

# Importa a biblioteca exatamente como ela está no seu Termux
import kahoot

app = FastAPI()

# Permite que o seu site na Vercel se comunique com o Render sem bloqueios de segurança
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
    # Cria o cliente usando a estrutura correta da biblioteca kahoot 1.1.0
    cliente = kahoot.Client()
    
    # Evento disparado quando uma pergunta começa no telão
    @cliente.on("question_start")
    async def ao_iniciar_pergunta(packet):
        numero_pergunta = getattr(packet, 'game_block_index', 0)
        tempo_base_leitura = 4.0
        await asyncio.sleep(tempo_base_leitura + atraso_fixo)
        
        # Escolhe a cor travada ou uma aleatória (0=Vermelho, 1=Azul, 2=Amarelo, 3=Verde)
        escolha = cor_index if cor_index is not None else random.randint(0, 3)
        try:
            # Envia a resposta usando o método da biblioteca
            await cliente.answer(escolha)
        except Exception:
            pass

    try:
        # Bot tenta entrar no jogo
        await cliente.join(pin, nome)
        
        # Mantém o bot vivo no servidor em segundo plano
        while True:
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        # Se o modo pânico for ativado, desconecta o bot limpando o cache
        try:
            await cliente.leave()
        except Exception:
            pass
    except Exception:
        pass

@app.post("/conectar")
async def conectar_bots(config: BotConfig):
    # Se já existirem bots desse PIN rodando, limpa eles antes
    if config.pin in jogos_ativos:
        await desconectar_bots(config.pin)

    cor_index = CORES.get(config.cor.lower()) if config.cor else None
    jogos_ativos[config.pin] = []

    # Cria e dispara os bots em paralelo usando tarefas assíncronas nativas do FastAPI
    for i in range(1, config.quantidade + 1):
        nome_completo = f"{config.nome_base}{i}"
        tarefa = asyncio.create_task(
            rodar_bot_individual(config.pin, nome_completo, cor_index, config.atraso)
        )
        jogos_ativos[config.pin].append(tarefa)

    return {"status": "sucesso", "mensagem": f"{config.quantidade} bots enviados com sucesso!"}

@app.post("/desconectar/{pin}")
async def desconectar_bots(pin: int):
    if pin not in jogos_ativos or not jogos_ativos[pin]:
        return {"status": "aviso", "mensagem": "Nenhum bot ativo para este PIN."}

    # Cancela todas as tarefas dos bots em background
    for tarefa in jogos_ativos[pin]:
        tarefa.cancel()
    
    # Aguarda a finalização segura de todas as conexões
    await asyncio.gather(*jogos_ativos[pin], return_exceptions=True)
    jogos_ativos[pin] = []
    
    return {"status": "sucesso", "mensagem": "Modo pânico ativado! Todos os bots foram removidos."}
    
