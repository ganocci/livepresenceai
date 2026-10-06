"""
LivePresenceAI - Teste da autenticacao do WebSocket da chamada.

Backend em execucao. Cria um segundo professor, uma turma e um aluno temporarios (apagados ao final) e
confere: sem token e com token de outro professor a conexao e recusada (4401); com o token do dono, o
evento de reconhecimento chega.

Uso (na pasta backend, venv ativo): python testes/teste_websocket_auth.py
"""
import asyncio
import json
import os
import secrets
import sys

import requests
import websockets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import Aluno, Professor, RegistroPresenca, Sessao, Turma  # noqa: E402

B = os.getenv("LIVEPRESENCEAI_BACKEND", "http://127.0.0.1:8000")
WS = B.replace("http", "ws", 1)
falhas = []


def confere(descricao, condicao, detalhe=""):
    print(f"[{'ok' if condicao else 'FALHOU'}] {descricao}{'' if condicao else f' -> {detalhe}'}")
    if not condicao:
        falhas.append(descricao)


async def codigo_recusa(url):
    """Codigo de fechamento quando o servidor recusa a conexao, ou None se aceitou."""
    try:
        async with websockets.connect(url) as ws:
            await asyncio.wait_for(ws.recv(), timeout=2)
            return None
    except websockets.exceptions.ConnectionClosed as e:
        return e.rcvd.code if e.rcvd else None
    except websockets.exceptions.InvalidStatus as e:
        return e.response.status_code
    except asyncio.TimeoutError:
        return None


async def recebe_evento(url, sessao_id, aluno_id):
    async with websockets.connect(url) as ws:
        await asyncio.to_thread(requests.post, f"{B}/sessoes/{sessao_id}/reconhecimento",
                                headers={"X-API-Key": main.CHAVE_MODULO_IA},
                                json={"aluno_id": aluno_id, "confianca": 0.9})
        return json.loads(await asyncio.wait_for(ws.recv(), timeout=5))


def principal():
    db = SessionLocal()
    sufixo = secrets.token_hex(3)
    dono = db.query(Professor).filter(Professor.email == "professor@livepresenceai.com").one()
    outro = Professor(nome="Outro", email=f"ws_{sufixo}@teste.local", senha_hash="x")
    db.add(outro)
    db.commit()
    turma = Turma(nome="Teste WS", professor_id=dono.id)
    db.add(turma)
    db.commit()
    aluno = Aluno(nome="Aluno WS", turma_id=turma.id)
    db.add(aluno)
    db.commit()
    try:
        sessao = main.abrir_sessao(turma.id, professor=dono, db=db)
        url = f"{WS}/ws/sessoes/{sessao.id}"
        confere("sem token -> recusado", asyncio.run(codigo_recusa(url)) is not None)
        confere("token invalido -> recusado", asyncio.run(codigo_recusa(url + "?token=abc")) is not None)
        token_outro = main.criar_token(outro.email)
        confere("token de outro professor -> recusado",
                asyncio.run(codigo_recusa(f"{url}?token={token_outro}")) is not None)
        evento = asyncio.run(recebe_evento(f"{url}?token={main.criar_token(dono.email)}", sessao.id, aluno.id))
        confere("token do dono -> recebe o evento", evento.get("aluno_id") == aluno.id, evento)
    finally:
        db.rollback()
        ids = [s.id for s in db.query(Sessao).filter(Sessao.turma_id == turma.id)]
        db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id.in_(ids)).delete(synchronize_session=False)
        db.query(Sessao).filter(Sessao.id.in_(ids)).delete(synchronize_session=False)
        db.query(Aluno).filter(Aluno.turma_id == turma.id).delete(synchronize_session=False)
        db.query(Turma).filter(Turma.id == turma.id).delete(synchronize_session=False)
        db.query(Professor).filter(Professor.id == outro.id).delete(synchronize_session=False)
        db.commit()
        print("dados de teste removidos")
    print("\nTODOS OS TESTES PASSARAM" if not falhas else f"\n{len(falhas)} FALHA(S)")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    principal()
