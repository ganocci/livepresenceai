"""
LivePresenceAI - Teste de primeiro acesso, administracao de professores, salas e modulo de IA por sala.

Parte 1 (funcoes do backend contra um schema PostgreSQL temporario e vazio): configuracao inicial so
funciona uma vez. Parte 2 (HTTP real ao backend em execucao, dados temporarios apagados ao final):
perfis, professores, salas, chamada por sala (RN-13) e rotas /ia/salas.

Uso (na pasta backend, venv ativo, backend ligado): python testes/teste_admin_salas.py
"""
import os
import secrets
import sys

import requests
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main  # noqa: E402
import migracoes  # noqa: E402
from database import DATABASE_URL, Base, SessionLocal  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from models import Aluno, Professor, RegistroPresenca, Sala, Sessao, Turma  # noqa: E402
from schemas import PrimeiroAcessoIn  # noqa: E402

B = "http://127.0.0.1:8000"
K = {"X-API-Key": main.CHAVE_MODULO_IA}
falhas = []


def confere(descricao, condicao, detalhe=""):
    print(f"[{'ok' if condicao else 'FALHOU'}] {descricao}{'' if condicao else f' -> {detalhe}'}")
    if not condicao:
        falhas.append(descricao)


def parte1_primeiro_acesso():
    base_url = DATABASE_URL.split("?")[0]
    adm = create_engine(base_url)
    with adm.begin() as c:
        c.execute(text("DROP SCHEMA IF EXISTS teste_primeiro_acesso CASCADE; CREATE SCHEMA teste_primeiro_acesso"))
    try:
        motor = create_engine(base_url + "?options=-csearch_path%3Dteste_primeiro_acesso")
        migracoes.preparar_banco(motor, Base)
        db = sessionmaker(bind=motor)()
        confere("banco vazio: nao configurado", main.estado_configuracao(db) == {"configurado": False})
        r = main.configuracao_inicial(PrimeiroAcessoIn(nome="Admin", email="ADMIN@Escola.edu", senha="segura123"), db)
        confere("configuracao inicial cria administrador e devolve token", "access_token" in r)
        admin = db.query(Professor).one()
        confere("e-mail normalizado e perfil administrador", admin.email == "admin@escola.edu" and admin.perfil == "administrador")
        try:
            main.configuracao_inicial(PrimeiroAcessoIn(nome="Outro", email="x@y.com", senha="segura123"), db)
            confere("segunda configuracao -> 409", False)
        except HTTPException as e:
            confere("segunda configuracao -> 409", e.status_code == 409)
        db.close()
        motor.dispose()
    finally:
        with adm.begin() as c:
            c.execute(text("DROP SCHEMA IF EXISTS teste_primeiro_acesso CASCADE"))


def parte2_http():
    db = SessionLocal()
    sufixo = secrets.token_hex(3)
    senha = secrets.token_urlsafe(10)
    admin = Professor(nome="Admin Temp", email=f"adm_{sufixo}@teste.local", senha_hash=main.pwd_context.hash(senha),
                      perfil="administrador")
    db.add(admin)
    db.commit()
    criados = {"professores": [admin.id], "salas": [], "turmas": []}
    try:
        login = lambda e, s: requests.post(f"{B}/login", data={"username": e, "password": s})  # noqa: E731
        HA = {"Authorization": "Bearer " + login(admin.email, senha).json()["access_token"]}
        confere("estado: configurado", requests.get(f"{B}/configuracao/estado").json()["configurado"] is True)
        confere("configuracao inicial depois de configurado -> 409",
                requests.post(f"{B}/configuracao/inicial", json={"nome": "x", "email": "x@y.com", "senha": "12345678"}).status_code == 409)
        confere("/eu do administrador", requests.get(f"{B}/eu", headers=HA).json()["perfil"] == "administrador")

        # professores
        r = requests.post(f"{B}/professores", headers=HA, json={"nome": "Prof Temp", "email": f"PROF_{sufixo}@Teste.local",
                                                                 "senha": "inicial123"})
        confere("admin cria professor (e-mail em minusculas)", r.status_code == 201 and r.json()["email"] == f"prof_{sufixo}@teste.local", r.text)
        prof = r.json()
        criados["professores"].append(prof["id"])
        confere("senha curta -> 422", requests.post(f"{B}/professores", headers=HA, json={
            "nome": "x", "email": f"y_{sufixo}@t.local", "senha": "123"}).status_code == 422)
        confere("e-mail repetido -> 409", requests.post(f"{B}/professores", headers=HA, json={
            "nome": "x", "email": prof["email"], "senha": "inicial123"}).status_code == 409)
        HP = {"Authorization": "Bearer " + login(prof["email"], "inicial123").json()["access_token"]}
        confere("professor nao lista professores (403)", requests.get(f"{B}/professores", headers=HP).status_code == 403)
        confere("professor nao cria sala (403)", requests.post(f"{B}/salas", headers=HP, json={"nome": "x"}).status_code == 403)
        r = requests.put(f"{B}/eu/senha", headers=HP, json={"senha_atual": "errada", "nova_senha": "novasenha1"})
        confere("trocar senha com a atual errada -> 400", r.status_code == 400)
        r = requests.put(f"{B}/eu/senha", headers=HP, json={"senha_atual": "inicial123", "nova_senha": "novasenha1"})
        confere("trocar a propria senha -> 204", r.status_code == 204 and login(prof["email"], "novasenha1").status_code == 200)
        confere("admin nao remove o proprio acesso (409)", requests.put(f"{B}/professores/{admin.id}", headers=HA, json={
            "nome": admin.nome, "email": admin.email, "perfil": "professor"}).status_code == 409)
        requests.put(f"{B}/professores/{prof['id']}", headers=HA, json={"nome": "Prof Temp", "email": prof["email"], "ativo": False})
        r = login(prof["email"], "novasenha1")
        confere("conta desativada nao entra (401 com mensagem)", r.status_code == 401 and "desativada" in r.text, r.text)
        confere("token antigo de conta desativada perde acesso (401)", requests.get(f"{B}/turmas", headers=HP).status_code == 401)
        requests.put(f"{B}/professores/{prof['id']}", headers=HA, json={"nome": "Prof Temp", "email": prof["email"], "ativo": True})
        HP = {"Authorization": "Bearer " + login(prof["email"], "novasenha1").json()["access_token"]}

        # salas
        s1 = requests.post(f"{B}/salas", headers=HA, json={"nome": f"Sala T{sufixo}"}).json()
        s2 = requests.post(f"{B}/salas", headers=HA, json={"nome": f"Lab T{sufixo}"}).json()
        criados["salas"] += [s1["id"], s2["id"]]
        confere("sala com nome repetido -> 409",
                requests.post(f"{B}/salas", headers=HA, json={"nome": s1["nome"]}).status_code == 409)
        confere("professor lista salas", len(requests.get(f"{B}/salas", headers=HP).json()) >= 2)

        # turmas com sala padrao e chamada por sala
        t1 = requests.post(f"{B}/turmas", headers=HP, json={"nome": "Turma Temp 1", "sala_id": s1["id"]}).json()
        t2 = requests.post(f"{B}/turmas", headers=HP, json={"nome": "Turma Temp 2"}).json()
        criados["turmas"] += [t1["id"], t2["id"]]
        confere("turma com sala padrao", t1["sala_id"] == s1["id"] and t1["sala_nome"] == s1["nome"], t1)
        confere("sala inexistente -> 404",
                requests.post(f"{B}/turmas", headers=HP, json={"nome": "x", "sala_id": 999999}).status_code == 404)
        a1 = requests.post(f"{B}/turmas/{t1['id']}/alunos", headers=HP,
                           json={"nome": "Aluno Sala", "ra": f"S{sufixo}", "autorizou_biometria": True}).json()
        db.query(Aluno).filter(Aluno.id == a1["id"]).update({Aluno.embedding: [1.0] + [0.0] * 511})
        db.commit()

        confere("modulo da sala vazia: sem chamada",
                requests.get(f"{B}/ia/salas/{s1['id']}/sessao-ativa", headers=K).json()["sessao_id"] is None)
        sessao1 = requests.post(f"{B}/sessoes/{t1['id']}/abrir", headers=HP).json()
        confere("chamada abre na sala padrao", sessao1["sala_id"] == s1["id"] and sessao1["sala_nome"] == s1["nome"], sessao1)
        ativa = requests.get(f"{B}/ia/salas/{s1['id']}/sessao-ativa", headers=K).json()
        confere("modulo da sala ve a chamada e a galeria da turma",
                ativa["sessao_id"] == sessao1["id"] and ativa["turma_nome"] == "Turma Temp 1" and len(ativa["alunos"]) == 1, ativa)
        r = requests.post(f"{B}/sessoes/{t2['id']}/abrir?sala_id={s1['id']}", headers=HP)
        confere("RN-13: outra turma na mesma sala -> 409 com mensagem", r.status_code == 409 and "Turma Temp 1" in r.text, r.text)
        sessao2 = requests.post(f"{B}/sessoes/{t2['id']}/abrir?sala_id={s2['id']}", headers=HP).json()
        confere("outra turma em outra sala -> abre", sessao2["sala_id"] == s2["id"], sessao2)
        retomada = requests.post(f"{B}/sessoes/{t1['id']}/abrir", headers=HP).json()
        confere("reabrir a mesma turma retoma a chamada (RN-07)", retomada["retomada"] and retomada["id"] == sessao1["id"])
        salas = {s["id"]: s for s in requests.get(f"{B}/ia/salas", headers=K).json()}
        confere("/ia/salas indica salas em uso", salas[s1["id"]]["em_uso"] and salas[s2["id"]]["em_uso"])
        rel = requests.post(f"{B}/sessoes/{sessao1['id']}/encerrar", headers=HP).json()
        requests.post(f"{B}/sessoes/{sessao2['id']}/encerrar", headers=HP)
        confere("relatorio traz a sala", rel["sala_nome"] == s1["nome"], rel)
        csv = requests.get(f"{B}/sessoes/{sessao1['id']}/exportar?formato=csv", headers=HP).content.decode("utf-8-sig")
        confere("exportacao traz a sala", f"Sala;{s1['nome']}" in csv, csv[:200])
        confere("depois de encerrar, sala livre para o modulo",
                requests.get(f"{B}/ia/salas/{s1['id']}/sessao-ativa", headers=K).json()["sessao_id"] is None)
        confere("sala com aula nao pode ser excluida (409)",
                requests.delete(f"{B}/salas/{s1['id']}", headers=HA).status_code == 409)
        s3 = requests.post(f"{B}/salas", headers=HA, json={"nome": f"Vazia T{sufixo}"}).json()
        criados["salas"].append(s3["id"])
        confere("sala sem aula pode ser excluida (204)", requests.delete(f"{B}/salas/{s3['id']}", headers=HA).status_code == 204)
    finally:
        db.rollback()
        sessoes = [s.id for s in db.query(Sessao).filter(Sessao.turma_id.in_(criados["turmas"]))]
        db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id.in_(sessoes)).delete(synchronize_session=False)
        db.query(Sessao).filter(Sessao.id.in_(sessoes)).delete(synchronize_session=False)
        db.query(Aluno).filter(Aluno.turma_id.in_(criados["turmas"])).delete(synchronize_session=False)
        db.query(Turma).filter(Turma.id.in_(criados["turmas"])).delete(synchronize_session=False)
        db.query(Sala).filter(Sala.id.in_(criados["salas"])).delete(synchronize_session=False)
        db.query(Professor).filter(Professor.id.in_(criados["professores"])).delete(synchronize_session=False)
        db.commit()
        print("dados de teste removidos")


if __name__ == "__main__":
    parte1_primeiro_acesso()
    parte2_http()
    print("\nTODOS OS TESTES PASSARAM" if not falhas else f"\n{len(falhas)} FALHA(S)")
    sys.exit(1 if falhas else 0)
