"""
LivePresenceAI - Teste do ajuste manual da chamada (RN-15), inclusive para aluno sem biometria.

HTTP real ao backend em execucao; turma, alunos, aula e um segundo professor temporarios, apagados ao final.
Uso (na pasta backend, venv ativo, backend ligado): python testes/teste_ajuste_manual.py
"""
import os
import secrets
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import AjustePresenca, Aluno, Professor, RegistroPresenca, Sessao, Turma  # noqa: E402

B = "http://127.0.0.1:8000"
K = {"X-API-Key": main.CHAVE_MODULO_IA}
falhas = []


def confere(descricao, condicao, detalhe=""):
    print(f"[{'ok' if condicao else 'FALHOU'}] {descricao}{'' if condicao else f' -> {detalhe}'}")
    if not condicao:
        falhas.append(descricao)


def principal():
    db = SessionLocal()
    sufixo = secrets.token_hex(3).upper()
    senha = secrets.token_urlsafe(10)
    outro = Professor(nome="Outro", email=f"aj_{sufixo.lower()}@teste.local", senha_hash=main.pwd_context.hash(senha))
    db.add(outro)
    db.commit()
    turmas = []
    try:
        login = lambda e, s: {"Authorization": "Bearer " + requests.post(  # noqa: E731
            f"{B}/login", data={"username": e, "password": s}).json()["access_token"]}
        H, H2 = login("professor@livepresenceai.com", "senha123"), login(outro.email, senha)
        t = requests.post(f"{B}/turmas", headers=H, json={"nome": "Teste Ajuste"}).json()
        t2 = requests.post(f"{B}/turmas", headers=H, json={"nome": "Teste Ajuste Outra"}).json()
        turmas += [t["id"], t2["id"]]
        visto = requests.post(f"{B}/turmas/{t['id']}/alunos", headers=H, json={"nome": "Visto Pouco", "ra": f"AJ{sufixo}1"}).json()
        sem_bio = requests.post(f"{B}/turmas/{t['id']}/alunos", headers=H, json={"nome": "Sem Biometria", "ra": f"AJ{sufixo}2"}).json()
        terceiro = requests.post(f"{B}/turmas/{t['id']}/alunos", headers=H, json={"nome": "Terceiro", "ra": f"AJ{sufixo}3"}).json()
        de_fora = requests.post(f"{B}/turmas/{t2['id']}/alunos", headers=H, json={"nome": "De Fora", "ra": f"AJ{sufixo}4"}).json()

        s = requests.post(f"{B}/sessoes/{t['id']}/abrir", headers=H).json()
        url = f"{B}/sessoes/{s['id']}/ajustes"
        requests.post(f"{B}/sessoes/{s['id']}/reconhecimento", headers=K, json={"aluno_id": visto["id"], "confianca": 0.9})

        r = requests.put(f"{url}/{sem_bio['id']}", headers=H, json={"situacao": "presenca", "motivo": "  Sem   biometria (não autorizou)  "})
        confere("presença manual com a chamada aberta", r.status_code == 200 and r.json()["motivo"] == "Sem biometria (não autorizou)"
                and r.json()["professor_nome"], r.text)
        confere("situação inválida -> 422",
                requests.put(f"{url}/{terceiro['id']}", headers=H, json={"situacao": "talvez", "motivo": "xxx"}).status_code == 422)
        confere("motivo curto -> 422",
                requests.put(f"{url}/{terceiro['id']}", headers=H, json={"situacao": "presenca", "motivo": "x"}).status_code == 422)
        confere("aluno de outra turma -> 404",
                requests.put(f"{url}/{de_fora['id']}", headers=H, json={"situacao": "presenca", "motivo": "teste"}).status_code == 404)
        confere("outro professor -> 404",
                requests.put(f"{url}/{terceiro['id']}", headers=H2, json={"situacao": "presenca", "motivo": "teste"}).status_code == 404)
        sessao = requests.get(f"{B}/sessoes/{s['id']}", headers=H).json()
        confere("chamada ao vivo traz os ajustes", [a["aluno_id"] for a in sessao["ajustes"]] == [sem_bio["id"]], sessao.get("ajustes"))

        time.sleep(1)
        rel = requests.post(f"{B}/sessoes/{s['id']}/encerrar", headers=H).json()
        por_id = {a["aluno_id"]: a for a in rel["alunos"]}
        confere("sem biometria: presença manual no relatório",
                por_id[sem_bio["id"]]["situacao"] == "presenca" and por_id[sem_bio["id"]]["ajuste_manual"]
                and por_id[sem_bio["id"]]["situacao_calculada"] == "falta", por_id[sem_bio["id"]])
        confere("sem ajuste: situação calculada", not por_id[terceiro["id"]]["ajuste_manual"]
                and por_id[terceiro["id"]]["situacao"] == "falta")

        # depois de encerrada: falta justificada sobre um aluno detectado
        r = requests.put(f"{url}/{visto['id']}", headers=H, json={"situacao": "falta", "motivo": "Saiu no início da aula"})
        confere("ajuste depois de encerrar", r.status_code == 200, r.text)
        rel = requests.get(f"{B}/sessoes/{s['id']}/relatorio", headers=H).json()
        por_id = {a["aluno_id"]: a for a in rel["alunos"]}
        confere("ajuste prevalece sobre o cálculo (detectado -> falta manual)",
                por_id[visto["id"]]["situacao"] == "falta" and por_id[visto["id"]]["ajuste_manual"], por_id[visto["id"]])
        confere("totais com os ajustes (1 presença, 2 faltas)", rel["total_presencas"] == 1 and rel["total_faltas"] == 2, rel)
        r = requests.put(f"{url}/{visto['id']}", headers=H, json={"situacao": "presenca", "motivo": "Atestado apresentado"})
        confere("refazer o ajuste substitui o anterior (sem duplicar)",
                db.query(AjustePresenca).filter(AjustePresenca.sessao_id == s["id"], AjustePresenca.aluno_id == visto["id"]).count() == 1
                and r.json()["situacao"] == "presenca")
        historico = requests.get(f"{B}/turmas/{t['id']}/sessoes", headers=H).json()
        confere("histórico com os ajustes (2 presenças, 1 falta)",
                historico[0]["total_presencas"] == 2 and historico[0]["total_faltas"] == 1, historico)
        csv = requests.get(f"{B}/sessoes/{s['id']}/exportar?formato=csv", headers=H).content.decode("utf-8-sig")
        confere("CSV com 'Presença (manual)' e o motivo",
                "Presença (manual)" in csv and "Sem biometria (não autorizou)" in csv and "Observação" in csv, csv)
        pdf = requests.get(f"{B}/sessoes/{s['id']}/exportar?formato=pdf", headers=H)
        xlsx = requests.get(f"{B}/sessoes/{s['id']}/exportar?formato=xlsx", headers=H)
        confere("PDF e XLSX gerados com a coluna nova", pdf.content.startswith(b"%PDF") and xlsx.status_code == 200)
        confere("aluno com ajuste não pode ser excluído (409)",
                requests.delete(f"{B}/alunos/{sem_bio['id']}", headers=H).status_code == 409)
        r = requests.delete(f"{url}/{visto['id']}", headers=H)
        rel = requests.get(f"{B}/sessoes/{s['id']}/relatorio", headers=H).json()
        por_id = {a["aluno_id"]: a for a in rel["alunos"]}
        confere("remover o ajuste volta ao cálculo", r.status_code == 204 and not por_id[visto["id"]]["ajuste_manual"])
    finally:
        db.rollback()
        sessoes = [x.id for x in db.query(Sessao).filter(Sessao.turma_id.in_(turmas))]
        db.query(AjustePresenca).filter(AjustePresenca.sessao_id.in_(sessoes)).delete(synchronize_session=False)
        db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id.in_(sessoes)).delete(synchronize_session=False)
        db.query(Sessao).filter(Sessao.id.in_(sessoes)).delete(synchronize_session=False)
        db.query(Aluno).filter(Aluno.turma_id.in_(turmas)).delete(synchronize_session=False)
        db.query(Turma).filter(Turma.id.in_(turmas)).delete(synchronize_session=False)
        db.query(Professor).filter(Professor.id == outro.id).delete(synchronize_session=False)
        db.commit()
        print("dados de teste removidos")
    print("\nTODOS OS TESTES PASSARAM" if not falhas else f"\n{len(falhas)} FALHA(S)")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    principal()
