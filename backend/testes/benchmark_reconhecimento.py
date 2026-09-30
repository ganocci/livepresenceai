"""Mede o tempo de resposta de POST /sessoes/{id}/reconhecimento e o atraso de entrega
do evento pelo WebSocket, contra o backend real (Uvicorn, 1 processo) em 127.0.0.1:8000.

Usa dados temporários (professor, turma e 5 alunos) que são apagados ao final.
Resultados usados na seção 8.7 do TCC (três rodadas, 500 requisições medidas cada).

Uso, com o backend em execução e o ambiente virtual ativo, a partir do diretório backend:
    python testes/benchmark_reconhecimento.py [arquivo_saida.json]
"""
import asyncio
import json
import statistics
import sys
import time

import requests
import websockets

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import Professor, Turma, Aluno, Sessao, RegistroPresenca  # noqa: E402

URL = "http://127.0.0.1:8000"
WS = "ws://127.0.0.1:8000"
N_AQUECIMENTO = 20
N_MEDIDAS = 500
CHAVE = "livepresenceai-ia-dev"


def percentil(valores, p):
    ordenados = sorted(valores)
    k = (len(ordenados) - 1) * p / 100
    baixo, alto = int(k), min(int(k) + 1, len(ordenados) - 1)
    return ordenados[baixo] + (ordenados[alto] - ordenados[baixo]) * (k - baixo)


def resumo(nome, amostras_ms):
    return {
        "metrica": nome,
        "n": len(amostras_ms),
        "min": min(amostras_ms),
        "media": statistics.mean(amostras_ms),
        "desvio": statistics.stdev(amostras_ms),
        "mediana": statistics.median(amostras_ms),
        "p95": percentil(amostras_ms, 95),
        "p99": percentil(amostras_ms, 99),
        "max": max(amostras_ms),
    }


async def medir(sessao_id, alunos):
    http = requests.Session()
    http.headers.update({"X-API-Key": CHAVE})
    t_http, t_ws = [], []
    async def receber():
        mensagem = await ws.recv()
        return json.loads(mensagem), time.perf_counter()

    async with websockets.connect(f"{WS}/ws/sessoes/{sessao_id}") as ws:
        for i in range(N_AQUECIMENTO + N_MEDIDAS):
            aluno = alunos[i % len(alunos)]
            espera = asyncio.create_task(receber())  # escuta o WebSocket em paralelo ao POST
            await asyncio.sleep(0)
            t0 = time.perf_counter()
            resp = await asyncio.to_thread(
                http.post, f"{URL}/sessoes/{sessao_id}/reconhecimento",
                json={"aluno_id": aluno, "confianca": 0.9}, timeout=10,
            )
            t1 = time.perf_counter()
            msg, t2 = await asyncio.wait_for(espera, timeout=10)
            assert resp.status_code == 200 and resp.json()["registrado"], resp.text
            assert msg["aluno_id"] == aluno, msg
            if i >= N_AQUECIMENTO:
                t_http.append((t1 - t0) * 1000)   # ida e volta do POST
                t_ws.append((t2 - t0) * 1000)     # envio do POST -> evento recebido no WebSocket
    return t_http, t_ws


def main_bench():
    db = SessionLocal()
    prof = Professor(nome="BENCH", email="bench_desempenho@tmp", senha_hash="x")
    db.add(prof); db.commit()
    turma = Turma(nome="BENCH", professor_id=prof.id); db.add(turma); db.commit()
    alunos = [Aluno(nome=f"Aluno {i}", turma_id=turma.id) for i in range(1, 6)]
    db.add_all(alunos); db.commit()
    try:
        sessao = main.abrir_sessao(turma.id, professor=prof, db=db)
        t_http, t_ws = asyncio.run(medir(sessao.id, [a.id for a in alunos]))
        t0 = time.perf_counter()
        rel = main.encerrar_sessao(sessao.id, professor=prof, db=db)
        t_encerrar = (time.perf_counter() - t0) * 1000
        db.expire_all()
        deteccoes = sum(r.numero_deteccoes for r in db.query(RegistroPresenca).filter_by(sessao_id=sessao.id))
        resultado = {
            "http": resumo("POST reconhecimento (ida e volta HTTP)", t_http),
            "ws": resumo("Do envio do POST ao recebimento do evento no WebSocket", t_ws),
            "encerramento_ms": t_encerrar,
            "deteccoes_gravadas": deteccoes,
            "esperado": N_AQUECIMENTO + N_MEDIDAS,
            "alunos_no_relatorio": len(rel.alunos),
        }
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
        if len(sys.argv) > 1:
            with open(sys.argv[1], "w", encoding="utf-8") as f:
                json.dump(resultado, f, indent=2, ensure_ascii=False)
    finally:
        db.rollback()
        s_ids = [s.id for s in db.query(Sessao).filter(Sessao.turma_id == turma.id)]
        db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id.in_(s_ids)).delete(synchronize_session=False)
        db.query(Sessao).filter(Sessao.turma_id == turma.id).delete()
        db.query(Aluno).filter(Aluno.turma_id == turma.id).delete()
        db.delete(turma); db.delete(prof); db.commit()
        print("dados de teste removidos")


if __name__ == "__main__":
    main_bench()
