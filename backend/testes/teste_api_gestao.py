"""
LivePresenceAI - Teste da API de gestao de turmas/alunos, historico e exportacao.

Requisicoes HTTP reais ao backend em execucao (uvicorn main:app). Cria um professor, turmas, alunos e
aulas temporarios e apaga tudo ao final, mesmo em caso de falha.

Uso (backend ligado, venv do backend ativo, na pasta backend):
    python testes/teste_api_gestao.py [pasta_para_salvar_os_arquivos_exportados]
"""
import io
import os
import secrets
import sys
import time
from datetime import datetime

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal  # noqa: E402
from main import pwd_context  # noqa: E402
from models import Aluno, Professor, RegistroPresenca, Sessao, Turma  # noqa: E402

B = os.getenv("LIVEPRESENCEAI_BACKEND", "http://127.0.0.1:8000")
CHAVE_IA = {"X-API-Key": os.getenv("CHAVE_MODULO_IA", "livepresenceai-ia-dev")}
SUFIXO = secrets.token_hex(3).upper()  # evita colidir com RAs reais do banco
falhas = []


def confere(descricao: str, condicao: bool, detalhe="") -> None:
    print(f"[{'ok' if condicao else 'FALHOU'}] {descricao}{'' if condicao else f' -> {detalhe}'}")
    if not condicao:
        falhas.append(descricao)


def login(email: str, senha: str) -> dict:
    token = requests.post(f"{B}/login", data={"username": email, "password": senha}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    pasta = sys.argv[1] if len(sys.argv) > 1 else None
    db = SessionLocal()
    senha = secrets.token_urlsafe(12)
    outro = Professor(nome="Professor Temporario", email=f"temp_{SUFIXO.lower()}@teste.local",
                      senha_hash=pwd_context.hash(senha))
    db.add(outro)
    db.commit()
    principal = db.query(Professor).filter(Professor.email == "professor@livepresenceai.com").one()
    turmas_criadas = []
    try:
        H = login(principal.email, "senha123")
        H2 = login(outro.email, senha)

        # ---- Turmas ----
        r = requests.post(f"{B}/turmas", headers=H, json={"nome": "  Teste   Gestao  "})
        confere("criar turma (201, nome normalizado)", r.status_code == 201 and r.json()["nome"] == "Teste Gestao", r.text)
        turma = r.json()
        turmas_criadas.append(turma["id"])
        r = requests.put(f"{B}/turmas/{turma['id']}", headers=H, json={"nome": "Teste Gestao CC7"})
        confere("renomear turma", r.status_code == 200 and r.json()["nome"] == "Teste Gestao CC7", r.text)
        confere("nome vazio -> 422", requests.post(f"{B}/turmas", headers=H, json={"nome": "   "}).status_code == 422)
        confere("outro professor nao ve a turma (404)",
                requests.get(f"{B}/turmas/{turma['id']}/alunos", headers=H2).status_code == 404)
        confere("outro professor nao renomeia (404)",
                requests.put(f"{B}/turmas/{turma['id']}", headers=H2, json={"nome": "x"}).status_code == 404)
        confere("turma nao aparece na lista do outro professor",
                all(t["id"] != turma["id"] for t in requests.get(f"{B}/turmas", headers=H2).json()))

        # ---- Alunos ----
        ras = [f"T{SUFIXO}{i}" for i in range(1, 4)]
        alunos = []
        for i, ra in enumerate(ras, 1):
            r = requests.post(f"{B}/turmas/{turma['id']}/alunos", headers=H,
                              json={"nome": f"Aluno Teste {i}", "ra": f" {ra.lower()} "})
            alunos.append(r.json())
        confere("criar 3 alunos (RA em maiusculas, sem espacos)",
                [a.get("ra") for a in alunos] == ras, alunos)
        r = requests.post(f"{B}/turmas/{turma['id']}/alunos", headers=H, json={"nome": "Repetido", "ra": ras[0]})
        confere("RA repetido -> 409", r.status_code == 409, r.text)
        r = requests.post(f"{B}/turmas/{turma['id']}/alunos", headers=H, json={"nome": "Invalido", "ra": "R@ 1"})
        confere("RA invalido -> 422", r.status_code == 422, r.text)
        r = requests.put(f"{B}/alunos/{alunos[0]['id']}", headers=H, json={"nome": "Aluno Teste Um", "ra": ras[0]})
        confere("editar aluno", r.status_code == 200 and r.json()["nome"] == "Aluno Teste Um", r.text)
        r = requests.put(f"{B}/alunos/{alunos[1]['id']}", headers=H, json={"nome": "Aluno Teste 2", "ra": ras[0]})
        confere("editar para RA de outro aluno -> 409", r.status_code == 409, r.text)
        confere("outro professor nao edita aluno (404)",
                requests.put(f"{B}/alunos/{alunos[0]['id']}", headers=H2,
                             json={"nome": "x", "ra": "X1"}).status_code == 404)
        lista = requests.get(f"{B}/turmas/{turma['id']}/alunos", headers=H).json()
        confere("lista com nome, RA e cadastro facial",
                len(lista) == 3 and all({"nome", "ra", "cadastro_facial"} <= set(a) for a in lista), lista)

        # ---- Aula: 2 alunos detectados, 1 nao ----
        sessao = requests.post(f"{B}/sessoes/{turma['id']}/abrir", headers=H).json()
        confere("relatorio de aula aberta -> 409",
                requests.get(f"{B}/sessoes/{sessao['id']}/relatorio", headers=H).status_code == 409)
        confere("exportar aula aberta -> 409",
                requests.get(f"{B}/sessoes/{sessao['id']}/exportar?formato=csv", headers=H).status_code == 409)
        for _ in range(3):
            for aluno in alunos[:2]:
                requests.post(f"{B}/sessoes/{sessao['id']}/reconhecimento", headers=CHAVE_IA,
                              json={"aluno_id": aluno["id"], "confianca": 0.9})
            time.sleep(1)
        encerrado = requests.post(f"{B}/sessoes/{sessao['id']}/encerrar", headers=H).json()
        confere("encerrar: relatorio com turma, professor, inicio/fim e RA",
                encerrado["turma_nome"] == "Teste Gestao CC7" and encerrado["professor_nome"]
                and encerrado["inicio"] and encerrado["fim"] and encerrado["alunos"][0]["ra"], encerrado)

        # Aluno incluido depois da aula nao deve aparecer nela
        novo = requests.post(f"{B}/turmas/{turma['id']}/alunos", headers=H,
                             json={"nome": "Aluno Novo", "ra": f"T{SUFIXO}9"}).json()

        historico = requests.get(f"{B}/turmas/{turma['id']}/sessoes", headers=H).json()
        confere("historico com 1 aula, 2 presencas e 1 falta",
                len(historico) == 1 and historico[0]["total_presencas"] == 2 and historico[0]["total_faltas"] == 1
                and historico[0]["duracao_segundos"] > 0, historico)
        relatorio = requests.get(f"{B}/sessoes/{sessao['id']}/relatorio", headers=H).json()
        confere("relatorio do historico igual ao do encerramento",
                [a["situacao"] for a in relatorio["alunos"]] == [a["situacao"] for a in encerrado["alunos"]])
        confere("aluno incluido depois da aula fica fora do relatorio dela",
                all(a["aluno_id"] != novo["id"] for a in relatorio["alunos"]), relatorio["alunos"])
        confere("outro professor nao ve o relatorio (404)",
                requests.get(f"{B}/sessoes/{sessao['id']}/relatorio", headers=H2).status_code == 404)
        confere("outro professor nao ve o historico (404)",
                requests.get(f"{B}/turmas/{turma['id']}/sessoes", headers=H2).status_code == 404)
        turmas = {t["id"]: t for t in requests.get(f"{B}/turmas", headers=H).json()}
        confere("lista de turmas com 4 alunos e 1 aula",
                turmas[turma["id"]]["total_alunos"] == 4 and turmas[turma["id"]]["total_aulas"] == 1, turmas[turma["id"]])

        # ---- Exportacao ----
        tipos = {"csv": "text/csv", "xlsx": "spreadsheetml", "pdf": "application/pdf"}
        for formato, tipo in tipos.items():
            r = requests.get(f"{B}/sessoes/{sessao['id']}/exportar?formato={formato}", headers=H)
            nome = r.headers.get("content-disposition", "")
            confere(f"exportar {formato} (tipo, nome do arquivo, {len(r.content)} bytes)",
                    r.status_code == 200 and tipo in r.headers.get("content-type", "")
                    and f"aula{sessao['id']}.{formato}" in nome, (r.status_code, r.headers, r.text[:200]))
            if pasta and r.status_code == 200:
                with open(os.path.join(pasta, f"exemplo.{formato}"), "wb") as arquivo:
                    arquivo.write(r.content)
            if formato == "csv":
                texto = r.content.decode("utf-8-sig")
                confere("CSV: BOM, separador ';', acentos e RA",
                        r.content.startswith(b"\xef\xbb\xbf") and "Situação;" in texto and ras[0] in texto, texto[:300])
            elif formato == "xlsx":
                from openpyxl import load_workbook
                folha = load_workbook(io.BytesIO(r.content)).active
                valores = [c for linha in folha.iter_rows(values_only=True) for c in linha if c is not None]
                confere("XLSX: abre no openpyxl, com cabecalho, RA e percentual numerico",
                        "Permanência" in valores and ras[0] in valores
                        and any(isinstance(v, float) for v in valores), valores[:30])
            else:
                confere("PDF: assinatura %PDF", r.content.startswith(b"%PDF"))
        confere("formato invalido -> 422",
                requests.get(f"{B}/sessoes/{sessao['id']}/exportar?formato=doc", headers=H).status_code == 422)
        confere("exportar sem login -> 401",
                requests.get(f"{B}/sessoes/{sessao['id']}/exportar?formato=csv").status_code == 401)

        # ---- Exclusoes protegidas ----
        r = requests.delete(f"{B}/alunos/{alunos[0]['id']}", headers=H)
        confere("excluir aluno com presenca -> 409", r.status_code == 409, r.text)
        r = requests.delete(f"{B}/alunos/{alunos[2]['id']}", headers=H)
        confere("excluir aluno sem presenca -> 204", r.status_code == 204, r.text)
        r = requests.delete(f"{B}/turmas/{turma['id']}", headers=H)
        confere("excluir turma com aula -> 409", r.status_code == 409, r.text)
        vazia = requests.post(f"{B}/turmas", headers=H, json={"nome": "Teste Vazia"}).json()
        turmas_criadas.append(vazia["id"])
        requests.post(f"{B}/turmas/{vazia['id']}/alunos", headers=H, json={"nome": "Sem Aula", "ra": f"T{SUFIXO}8"})
        r = requests.delete(f"{B}/turmas/{vazia['id']}", headers=H)
        confere("excluir turma sem aula (com aluno) -> 204", r.status_code == 204, r.text)
        confere("aluno da turma excluida tambem saiu",
                db.query(Aluno).filter(Aluno.ra == f"T{SUFIXO}8").count() == 0)
    finally:
        db.rollback()
        sessoes = [s.id for s in db.query(Sessao).filter(Sessao.turma_id.in_(turmas_criadas))]
        db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id.in_(sessoes)).delete(synchronize_session=False)
        db.query(Sessao).filter(Sessao.id.in_(sessoes)).delete(synchronize_session=False)
        db.query(Aluno).filter(Aluno.turma_id.in_(turmas_criadas)).delete(synchronize_session=False)
        db.query(Turma).filter(Turma.id.in_(turmas_criadas)).delete(synchronize_session=False)
        db.query(Professor).filter(Professor.id == outro.id).delete(synchronize_session=False)
        db.commit()
        print("dados de teste removidos")
    print(f"\n{'TODOS OS TESTES PASSARAM' if not falhas else f'{len(falhas)} FALHA(S)'} ({datetime.now():%d/%m/%Y %H:%M})")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
