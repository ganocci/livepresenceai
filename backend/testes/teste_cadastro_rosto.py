"""
LivePresenceAI - Teste do cadastro facial pelo app (POST/DELETE /alunos/{id}/rosto e autorizacao).

Requisicoes HTTP reais ao backend em execucao. Usa a foto de exemplo do InsightFace (t1.jpg, 6 pessoas)
para montar as fotos de teste em memoria. Cria uma turma, alunos e um segundo professor temporarios e
apaga tudo ao final.

Uso (backend ligado, venv do backend ativo, na pasta backend):
    python testes/teste_cadastro_rosto.py
"""
import os
import secrets
import sys
import time

import cv2
import numpy as np
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal  # noqa: E402
from main import pwd_context  # noqa: E402
from models import Aluno, Professor, Turma  # noqa: E402

B = os.getenv("LIVEPRESENCEAI_BACKEND", "http://127.0.0.1:8000")
SUFIXO = secrets.token_hex(3).upper()
falhas = []


def confere(descricao, condicao, detalhe=""):
    print(f"[{'ok' if condicao else 'FALHOU'}] {descricao}{'' if condicao else f' -> {detalhe}'}")
    if not condicao:
        falhas.append(descricao)


def jpeg(imagem) -> bytes:
    return cv2.imencode(".jpg", imagem)[1].tobytes()


def fotos_de_teste():
    """Recortes de cada pessoa da foto de exemplo, ampliados (como um celular a meio metro)."""
    import insightface
    from insightface.app import FaceAnalysis

    grupo = cv2.imread(os.path.join(os.path.dirname(insightface.__file__), "data", "images", "t1.jpg"))
    modelo = FaceAnalysis(name="buffalo_l", allowed_modules=["detection", "recognition"],
                          providers=["CPUExecutionProvider"])
    modelo.prepare(ctx_id=-1, det_size=(640, 640))
    rostos = sorted(modelo.get(grupo), key=lambda f: f.bbox[0])
    recortes, vetores = [], []
    for rosto in rostos:
        x1, y1, x2, y2 = rosto.bbox.astype(int)
        w, h = x2 - x1, y2 - y1
        recorte = grupo[max(0, y1 - h // 2):y2 + h // 2, max(0, x1 - w // 2):x2 + w // 2]
        recortes.append(cv2.resize(recorte, None, fx=2, fy=2))
        vetores.append(rosto.normed_embedding)
    return grupo, recortes, vetores


def enviar(H, aluno_id, imagens):
    arquivos = [("fotos", (f"foto{i}.jpg", conteudo, "image/jpeg")) for i, conteudo in enumerate(imagens)]
    return requests.post(f"{B}/alunos/{aluno_id}/rosto", headers=H, files=arquivos, timeout=120)


def main():
    grupo, recortes, vetores = fotos_de_teste()
    p1 = recortes[0]
    variacoes = [jpeg(p1), jpeg(cv2.resize(p1, None, fx=0.9, fy=0.9)),
                 jpeg(cv2.convertScaleAbs(p1, alpha=1.1, beta=10)), jpeg(cv2.resize(p1, None, fx=1.1, fy=1.1))]

    db = SessionLocal()
    senha = secrets.token_urlsafe(12)
    outro = Professor(nome="Professor Temporario", email=f"temp_{SUFIXO.lower()}@teste.local",
                      senha_hash=pwd_context.hash(senha))
    db.add(outro)
    db.commit()
    turma_id = None
    try:
        login = lambda e, s: {"Authorization": "Bearer " + requests.post(  # noqa: E731
            f"{B}/login", data={"username": e, "password": s}).json()["access_token"]}
        H, H2 = login("professor@livepresenceai.com", "senha123"), login(outro.email, senha)
        turma_id = requests.post(f"{B}/turmas", headers=H, json={"nome": "Teste Rosto"}).json()["id"]
        autorizado = requests.post(f"{B}/turmas/{turma_id}/alunos", headers=H,
                                   json={"nome": "Autorizado", "ra": f"R{SUFIXO}1", "autorizou_biometria": True}).json()
        sem_aut = requests.post(f"{B}/turmas/{turma_id}/alunos", headers=H,
                                json={"nome": "Sem Autorizacao", "ra": f"R{SUFIXO}2"}).json()
        confere("aluno criado com autorizacao (data registrada)",
                autorizado["autorizacao_biometrica"] and autorizado["autorizacao_biometrica_em"], autorizado)
        confere("aluno criado sem autorizacao", sem_aut["autorizacao_biometrica"] is False, sem_aut)

        r = enviar(H, sem_aut["id"], variacoes[:3])
        confere("sem autorizacao -> 409", r.status_code == 409, r.text)
        r = enviar(H2, autorizado["id"], variacoes[:3])
        confere("outro professor -> 404", r.status_code == 404, r.text)
        r = enviar(H, autorizado["id"], variacoes[:2])
        confere("so 2 fotos -> 422", r.status_code == 422, r.text)
        r = enviar(H, autorizado["id"], [jpeg(grupo)] * 3)
        confere("foto com varias pessoas -> 422 com mensagem", r.status_code == 422 and "mais de um rosto" in r.text, r.text)
        pequena = cv2.resize(grupo, None, fx=0.3, fy=0.3)
        x = [cv2.resize(p1, (60, 80))] * 3
        r = enviar(H, autorizado["id"], [jpeg(i) for i in x])
        confere("rosto pequeno -> 422", r.status_code == 422, r.text)
        r = enviar(H, autorizado["id"], [b"isto nao e uma imagem"] * 3)
        confere("arquivo invalido -> 422", r.status_code == 422 and "não pôde ser lida" in r.text, r.text)
        r = enviar(H, autorizado["id"], variacoes[:3] + [jpeg(recortes[3])])
        confere("fotos de pessoas diferentes -> 422", r.status_code == 422 and "pessoas diferentes" in r.text, r.text)
        del pequena

        inicio = time.perf_counter()
        r = enviar(H, autorizado["id"], variacoes)
        tempo = time.perf_counter() - inicio
        confere(f"4 fotos validas -> cadastro facial ({tempo:.1f} s)", r.status_code == 200 and r.json()["cadastro_facial"], r.text)
        inicio = time.perf_counter()
        enviar(H, autorizado["id"], variacoes[:3])
        print(f"      segundo cadastro (modelo ja carregado): {time.perf_counter() - inicio:.1f} s")

        db.expire_all()
        vetor = np.array(db.query(Aluno).filter(Aluno.id == autorizado["id"]).one().embedding)
        similaridades = [float(vetor @ v) for v in vetores]
        confere(f"vetor do app reconhece a pessoa no modulo da sala (similaridade {similaridades[0]:.2f}; "
                f"maior com outra pessoa {max(similaridades[1:]):.2f})",
                similaridades[0] >= 0.6 and max(similaridades[1:]) < 0.6, similaridades)

        r = requests.put(f"{B}/alunos/{autorizado['id']}", headers=H, json={"nome": "Autorizado Editado", "ra": f"R{SUFIXO}1"})
        confere("editar sem o campo mantem autorizacao e rosto",
                r.json()["autorizacao_biometrica"] and r.json()["cadastro_facial"], r.text)
        r = requests.delete(f"{B}/alunos/{autorizado['id']}/rosto", headers=H)
        confere("excluir rosto mantem a autorizacao",
                r.status_code == 200 and not r.json()["cadastro_facial"] and r.json()["autorizacao_biometrica"], r.text)
        enviar(H, autorizado["id"], variacoes[:3])
        r = requests.put(f"{B}/alunos/{autorizado['id']}", headers=H,
                         json={"nome": "Autorizado Editado", "ra": f"R{SUFIXO}1", "autorizou_biometria": False})
        confere("revogar autorizacao apaga o rosto",
                not r.json()["autorizacao_biometrica"] and not r.json()["cadastro_facial"], r.text)
        db.expire_all()
        confere("no banco: vetor e data de autorizacao nulos",
                db.query(Aluno).filter(Aluno.id == autorizado["id"], Aluno.embedding.is_(None),
                                       Aluno.consentimento_biometrico_em.is_(None)).count() == 1)
    finally:
        db.rollback()
        if turma_id:
            db.query(Aluno).filter(Aluno.turma_id == turma_id).delete(synchronize_session=False)
            db.query(Turma).filter(Turma.id == turma_id).delete(synchronize_session=False)
        db.query(Professor).filter(Professor.id == outro.id).delete(synchronize_session=False)
        db.commit()
        print("dados de teste removidos")
    print(f"\n{'TODOS OS TESTES PASSARAM' if not falhas else f'{len(falhas)} FALHA(S)'}")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
