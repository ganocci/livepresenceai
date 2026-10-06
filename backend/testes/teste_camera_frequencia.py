"""
LivePresenceAI - Teste da situacao da camera da sala e da frequencia acumulada da turma (RN-16).

Parte 1 (funcao _situacao_camera, sem servidor): conectada, aguardando, sem sinal e sem camera, com o
relogio simulado. Parte 2 (HTTP real ao backend em execucao): contato do modulo de IA, 3 aulas com
presencas, falta e ajuste manual, frequencia acumulada, aluno incluido depois e exportacao. Turma, alunos,
aulas, sala e um segundo professor temporarios, apagados ao final.

Uso (na pasta backend, venv ativo, backend ligado): python testes/teste_camera_frequencia.py
"""
import io
import os
import secrets
import sys
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main  # noqa: E402
from database import SessionLocal  # noqa: E402
from models import AjustePresenca, Aluno, Professor, RegistroPresenca, Sala, Sessao, Turma  # noqa: E402

B = os.getenv("LIVEPRESENCEAI_BACKEND", "http://127.0.0.1:8000")
K = {"X-API-Key": main.CHAVE_MODULO_IA}
falhas = []


def confere(descricao, condicao, detalhe=""):
    print(f"[{'ok' if condicao else 'FALHOU'}] {descricao}{'' if condicao else f' -> {detalhe}'}")
    if not condicao:
        falhas.append(descricao)


def parte1_situacao_camera():
    agora = datetime(2026, 10, 7, 10, 0, 0)
    sala = SimpleNamespace(nome="Sala 101")
    sessao = SimpleNamespace(id=9, sala_id=5, turma_id=3, sala=sala, inicio=agora - timedelta(minutes=10))
    main._contatos_ia.clear()
    s = main._situacao_camera(sessao, agora)
    confere("sala sem nenhum contato do módulo -> sem sinal, citando a sala",
            s.situacao == "sem_sinal" and "Sala 101" in s.mensagem and s.visto_ha_segundos is None, s)
    recem = SimpleNamespace(id=9, sala_id=5, turma_id=3, sala=sala, inicio=agora - timedelta(seconds=8))
    confere("chamada recém-aberta sem contato -> aguardando", main._situacao_camera(recem, agora).situacao == "aguardando")
    main._contatos_ia[("sala", 5)] = (agora - timedelta(seconds=3), None)
    confere("módulo vivo que ainda não pegou esta chamada -> aguardando",
            main._situacao_camera(sessao, agora).situacao == "aguardando")
    main._contatos_ia[("sala", 5)] = (agora - timedelta(seconds=40), 9)
    s = main._situacao_camera(sessao, agora)
    confere("módulo com esta chamada há 40 s -> conectada", s.situacao == "conectada" and s.visto_ha_segundos == 40, s)
    main._contatos_ia[("sala", 5)] = (agora - timedelta(seconds=90), 9)
    confere("último contato há 90 s -> sem sinal", main._situacao_camera(sessao, agora).situacao == "sem_sinal")
    main._contatos_ia[("turma", 3)] = (agora - timedelta(seconds=5), 9)
    confere("módulo acompanhando a turma (--turma) também conta",
            main._situacao_camera(sessao, agora).situacao == "conectada")
    main._contatos_ia.clear()
    sem_sala = SimpleNamespace(id=9, sala_id=None, turma_id=3, sala=None, inicio=agora - timedelta(minutes=10))
    confere("chamada sem sala e sem módulo -> sem câmera", main._situacao_camera(sem_sala, agora).situacao == "sem_camera")


def parte2_http():
    db = SessionLocal()
    sufixo = secrets.token_hex(3).upper()
    senha = secrets.token_urlsafe(10)
    outro = Professor(nome="Outro", email=f"cf_{sufixo.lower()}@teste.local", senha_hash=main.pwd_context.hash(senha))
    sala = Sala(nome=f"Sala Teste {sufixo}")
    db.add_all([outro, sala])
    db.commit()
    turmas = []
    try:
        login = lambda e, s: {"Authorization": "Bearer " + requests.post(  # noqa: E731
            f"{B}/login", data={"username": e, "password": s}).json()["access_token"]}
        H, H2 = login("professor@livepresenceai.com", "senha123"), login(outro.email, senha)
        t = requests.post(f"{B}/turmas", headers=H, json={"nome": "Teste Frequência"}).json()
        turmas.append(t["id"])
        novo = lambda nome, n: requests.post(f"{B}/turmas/{t['id']}/alunos", headers=H,  # noqa: E731
                                             json={"nome": nome, "ra": f"CF{sufixo}{n}"}).json()
        ana, bia, caio = novo("Ana Sempre", 1), novo("Bia Às Vezes", 2), novo("Caio Nunca", 3)

        # Camera: chamada na sala, antes e depois do modulo consultar
        s = requests.post(f"{B}/sessoes/{t['id']}/abrir?sala_id={sala.id}", headers=H).json()
        r = requests.get(f"{B}/sessoes/{s['id']}/camera", headers=H).json()
        confere("chamada recém-aberta, módulo ainda não consultou -> aguardando", r["situacao"] == "aguardando", r)
        requests.get(f"{B}/ia/salas/{sala.id}/sessao-ativa", headers=K)
        r = requests.get(f"{B}/sessoes/{s['id']}/camera", headers=H).json()
        confere("depois da consulta do módulo da sala -> conectada", r["situacao"] == "conectada", r)
        confere("outro professor não vê a câmera da chamada (404)",
                requests.get(f"{B}/sessoes/{s['id']}/camera", headers=H2).status_code == 404)

        # 3 aulas: Ana presente em todas; Bia em 1 e com presenca manual em outra; Caio nunca
        sessoes = [s["id"]]
        for i in range(3):
            if i:
                sessoes.append(requests.post(f"{B}/sessoes/{t['id']}/abrir", headers=H).json()["id"])
            sid = sessoes[-1]
            presentes = [ana["id"]] + ([bia["id"]] if i == 0 else [])
            for _ in range(2):  # duas deteccoes com 1 s entre elas: permanencia acima de 40% da aula curta
                for aluno_id in presentes:
                    requests.post(f"{B}/sessoes/{sid}/reconhecimento", headers=K, json={"aluno_id": aluno_id, "confianca": 0.9})
                time.sleep(1)
            if i == 2:
                requests.put(f"{B}/sessoes/{sid}/ajustes/{bia['id']}", headers=H,
                             json={"situacao": "presenca", "motivo": "Atestado de presença"})
            requests.post(f"{B}/sessoes/{sid}/encerrar", headers=H)
        r = requests.get(f"{B}/sessoes/{sessoes[0]}/camera", headers=H).json()
        confere("chamada encerrada -> sem câmera (nada a avisar)", r["situacao"] == "sem_camera", r)

        # Aluno incluido depois das aulas e uma aula ainda aberta (nao conta)
        davi = novo("Davi Novo", 4)
        aberta = requests.post(f"{B}/sessoes/{t['id']}/abrir", headers=H).json()["id"]
        sessoes.append(aberta)

        f = requests.get(f"{B}/turmas/{t['id']}/frequencia", headers=H)
        confere("frequência da turma (200)", f.status_code == 200, f.text)
        f = f.json()
        por = {a["aluno_id"]: a for a in f["alunos"]}
        confere("só aulas encerradas contam (3)", f["total_aulas"] == 3 and len(f["aulas"]) == 3, f["total_aulas"])
        confere("mínimo padrão de 75% informado", f["frequencia_minima"] == 75 and f["frequencia_minima_aula"] == 40)
        a = por[ana["id"]]
        confere("Ana: 3 de 3, 100%, regular", (a["aulas"], a["presencas"], a["percentual"], a["abaixo_do_minimo"]) == (3, 3, 100, False), a)
        b = por[bia["id"]]
        confere("Bia: 2 de 3 com 1 ajuste manual, 66,67%, abaixo do mínimo",
                (b["presencas"], b["faltas"], b["ajustes_manuais"], b["percentual"], b["abaixo_do_minimo"])
                == (2, 1, 1, 66.67, True) and b["por_aula"] == ["P", "F", "P"], b)
        c = por[caio["id"]]
        confere("Caio: 0 de 3, abaixo do mínimo", (c["presencas"], c["percentual"], c["abaixo_do_minimo"]) == (0, 0, True), c)
        d = por[davi["id"]]
        confere("Davi (incluído depois): sem aulas, sem percentual, não marcado",
                d["aulas"] == 0 and d["percentual"] is None and not d["abaixo_do_minimo"] and d["por_aula"] == [None] * 3, d)
        confere("2 alunos abaixo do mínimo", f["alunos_abaixo_do_minimo"] == 2, f["alunos_abaixo_do_minimo"])
        confere("outro professor não vê a frequência (404)",
                requests.get(f"{B}/turmas/{t['id']}/frequencia", headers=H2).status_code == 404)

        csv_ = requests.get(f"{B}/turmas/{t['id']}/frequencia/exportar?formato=csv", headers=H)
        texto = csv_.content.decode("utf-8-sig")
        confere("CSV com a grade por aula e vírgula decimal",
                csv_.status_code == 200 and "Bia Às Vezes" in texto and "66,67" in texto and ";P;F;P" in texto, texto[:300])
        xlsx = requests.get(f"{B}/turmas/{t['id']}/frequencia/exportar?formato=xlsx", headers=H)
        from openpyxl import load_workbook
        livro = load_workbook(io.BytesIO(xlsx.content))
        grade = livro["Por aula"]
        linhas = {row[0]: row[2:5] for row in grade.iter_rows(min_row=2, values_only=True) if row and row[0]}
        confere("XLSX com as abas Frequência e Por aula", livro.sheetnames == ["Frequência", "Por aula"], livro.sheetnames)
        confere("grade do XLSX: Bia P/F/P e Davi vazio",
                linhas.get("Bia Às Vezes") == ("P", "F", "P") and linhas.get("Davi Novo") == (None, None, None), linhas)
        pdf = requests.get(f"{B}/turmas/{t['id']}/frequencia/exportar?formato=pdf", headers=H)
        confere("PDF gerado", pdf.status_code == 200 and pdf.content.startswith(b"%PDF"))
        confere("formato inválido -> 422",
                requests.get(f"{B}/turmas/{t['id']}/frequencia/exportar?formato=doc", headers=H).status_code == 422)
        requests.post(f"{B}/sessoes/{aberta}/encerrar", headers=H)
    finally:
        db.rollback()
        sessoes = [x.id for x in db.query(Sessao).filter(Sessao.turma_id.in_(turmas))]
        db.query(AjustePresenca).filter(AjustePresenca.sessao_id.in_(sessoes)).delete(synchronize_session=False)
        db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id.in_(sessoes)).delete(synchronize_session=False)
        db.query(Sessao).filter(Sessao.id.in_(sessoes)).delete(synchronize_session=False)
        db.query(Aluno).filter(Aluno.turma_id.in_(turmas)).delete(synchronize_session=False)
        db.query(Turma).filter(Turma.id.in_(turmas)).delete(synchronize_session=False)
        db.query(Sala).filter(Sala.id == sala.id).delete(synchronize_session=False)
        db.query(Professor).filter(Professor.id == outro.id).delete(synchronize_session=False)
        db.commit()
        print("dados de teste removidos")


if __name__ == "__main__":
    parte1_situacao_camera()
    parte2_http()
    print("\nTODOS OS TESTES PASSARAM" if not falhas else f"\n{len(falhas)} FALHA(S)")
    sys.exit(1 if falhas else 0)
