"""Regras de negócio do backend (RN-01 a RN-16), com horários simulados onde o tempo importa."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import main
from conftest import CHAVE_IA, cabecalho, novo_professor
from models import RegistroPresenca, Sessao
from schemas import EventoReconhecimento

# Aulas simuladas no futuro: o relatório só inclui alunos cadastrados até o fim da aula (RN-11)
T0 = (datetime.utcnow() + timedelta(days=30)).replace(microsecond=0)


def _sessao(db, turma, inicio=T0):
    s = Sessao(turma_id=turma.id, professor_id=turma.professor_id, inicio=inicio, status="aberta")
    db.add(s)
    db.commit()
    return s


def _detectar(db, sessao, aluno, segundos, confianca=0.9):
    main._aplicar_deteccao(db, sessao.id, EventoReconhecimento(aluno_id=aluno.id, confianca=confianca),
                           T0 + timedelta(seconds=segundos))
    db.commit()


def _encerrar(db, sessao, segundos):
    registros = db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id == sessao.id).all()
    main._fechar_sessao(sessao, registros, T0 + timedelta(seconds=segundos))
    db.commit()
    return {r.aluno_id: r for r in registros}


# ----------------------------------------------------------------------------- permanência (RN-01 a RN-03)

def test_rn01_rn02_permanencia_desconta_ausencia_acima_do_limite(db, cenario):
    a = cenario["alunos"][0]
    s = _sessao(db, cenario["turma"])
    for t in range(0, 301, 30):            # visto a cada 30 s até 5 min
        _detectar(db, s, a, t)
    for t in range(600, 901, 30):          # some por 5 min (> 60 s: ausência) e volta até 15 min
        _detectar(db, s, a, t)
    r = _encerrar(db, s, 900)[a.id]
    assert r.entrada == T0                                    # RN-01: primeira detecção é a entrada
    assert r.tempo_total_presente == timedelta(seconds=600)   # 300 s + 300 s; os 300 s fora não contam
    assert float(r.percentual_presenca) == round(600 / 900 * 100, 2)


def test_rn02_intervalo_igual_ao_limite_conta_como_permanencia(db, cenario):
    a = cenario["alunos"][0]
    s = _sessao(db, cenario["turma"])
    _detectar(db, s, a, 0)
    _detectar(db, s, a, main.LIMITE_AUSENCIA.total_seconds())
    r = _encerrar(db, s, main.LIMITE_AUSENCIA.total_seconds())[a.id]
    assert r.tempo_total_presente == main.LIMITE_AUSENCIA


def test_encerramento_soma_o_restante_se_o_aluno_foi_visto_ha_pouco(db, cenario):
    a = cenario["alunos"][0]
    s = _sessao(db, cenario["turma"])
    for t in (0, 50, 100):
        _detectar(db, s, a, t)
    r = _encerrar(db, s, 130)[a.id]  # visto 30 s antes do fim (< 60 s): continua na sala até o fim
    assert r.tempo_total_presente == timedelta(seconds=130)


def test_rn03_presenca_a_partir_de_40_porcento_e_falta_abaixo(db, cenario):
    a, b, c = cenario["alunos"]
    s = _sessao(db, cenario["turma"])
    for t in range(0, 401, 20):      # a: 400 s de 1000 = 40%
        _detectar(db, s, a, t)
    for t in range(0, 381, 20):      # b: 380 s de 1000 = 38%
        _detectar(db, s, b, t)
    _encerrar(db, s, 1000)
    sessao = db.get(Sessao, s.id)
    rel = main._montar_relatorio(sessao, db.query(RegistroPresenca).filter_by(sessao_id=s.id).all(), db)
    situacao = {x.aluno_id: x.situacao for x in rel.alunos}
    assert situacao[a.id] == "presenca"
    assert situacao[b.id] == "falta"
    assert situacao[c.id] == "falta"  # não detectado


def test_rn03_minimo_configuravel(db, cenario, monkeypatch):
    a = cenario["alunos"][0]
    s = _sessao(db, cenario["turma"])
    for t in range(0, 501, 20):      # 50%
        _detectar(db, s, a, t)
    _encerrar(db, s, 1000)
    sessao = db.get(Sessao, s.id)
    registros = db.query(RegistroPresenca).filter_by(sessao_id=s.id).all()
    monkeypatch.setattr(main, "FREQUENCIA_MINIMA", 60.0)
    rel = main._montar_relatorio(sessao, registros, db)
    assert {x.aluno_id: x.situacao for x in rel.alunos}[a.id] == "falta"
    assert rel.frequencia_minima == 60.0


# ----------------------------------------------------------------------------- reconhecimento (RN-04, RN-08, RN-09)

def test_rn04_confianca_abaixo_do_minimo_e_descartada(cliente, cenario):
    s = cliente.post(f"/sessoes/{cenario['turma'].id}/abrir", headers=cenario["H"]).json()
    a = cenario["alunos"][0]
    r = cliente.post(f"/sessoes/{s['id']}/reconhecimento", headers=CHAVE_IA, json={"aluno_id": a.id, "confianca": 0.5})
    assert r.status_code == 200 and r.json()["registrado"] is False
    r = cliente.post(f"/sessoes/{s['id']}/reconhecimento", headers=CHAVE_IA, json={"aluno_id": a.id, "confianca": 0.9})
    assert r.json()["registrado"] is True


def test_rn09_reconhecimento_exige_chave(cliente, cenario):
    s = cliente.post(f"/sessoes/{cenario['turma'].id}/abrir", headers=cenario["H"]).json()
    r = cliente.post(f"/sessoes/{s['id']}/reconhecimento", headers={"X-API-Key": "errada"},
                     json={"aluno_id": cenario["alunos"][0].id, "confianca": 0.9})
    assert r.status_code in (401, 403)


def test_rn08_aluno_de_outra_turma_e_recusado(cliente, db, cenario):
    outro = novo_professor(db)
    H2 = cabecalho(cliente, outro.email)
    t2 = cliente.post("/turmas", headers=H2, json={"nome": "Outra"}).json()
    intruso = cliente.post(f"/turmas/{t2['id']}/alunos", headers=H2, json={"nome": "Intruso", "ra": "PYINTRUSO"}).json()
    s = cliente.post(f"/sessoes/{cenario['turma'].id}/abrir", headers=cenario["H"]).json()
    r = cliente.post(f"/sessoes/{s['id']}/reconhecimento", headers=CHAVE_IA, json={"aluno_id": intruso["id"], "confianca": 0.9})
    assert r.status_code >= 400


# ----------------------------------------------------------------------------- sessão (RN-05, RN-07, RN-13)

def test_rn07_chamada_aberta_e_retomada(cliente, cenario):
    url = f"/sessoes/{cenario['turma'].id}/abrir"
    s1 = cliente.post(url, headers=cenario["H"]).json()
    s2 = cliente.post(url, headers=cenario["H"]).json()
    assert s1["id"] == s2["id"] and s2["retomada"] is True


def test_rn13_sala_ocupada(cliente, db, cenario):
    cliente.post(f"/sessoes/{cenario['turma'].id}/abrir?sala_id={cenario['sala'].id}", headers=cenario["H"])
    t2 = cliente.post("/turmas", headers=cenario["H"], json={"nome": "Segunda"}).json()
    cliente.post(f"/turmas/{t2['id']}/alunos", headers=cenario["H"], json={"nome": "X", "ra": "PYSEG1"})
    r = cliente.post(f"/sessoes/{t2['id']}/abrir?sala_id={cenario['sala'].id}", headers=cenario["H"])
    assert r.status_code == 409


def test_rn05_outro_professor_nao_abre_a_chamada(cliente, db, cenario):
    outro = novo_professor(db)
    r = cliente.post(f"/sessoes/{cenario['turma'].id}/abrir", headers=cabecalho(cliente, outro.email))
    assert r.status_code == 404


# ----------------------------------------------------------------------------- biometria (RN-12) e LGPD

def test_rn12_galeria_so_com_autorizacao(cliente, cenario):
    cliente.post(f"/sessoes/{cenario['turma'].id}/abrir", headers=cenario["H"])
    g = cliente.get(f"/ia/turmas/{cenario['turma'].id}/sessao-ativa", headers=CHAVE_IA).json()
    ids = {a["aluno_id"] for a in g["alunos"]}
    assert ids == {cenario["alunos"][0].id, cenario["alunos"][1].id}


def test_rn12_revogar_autorizacao_apaga_o_vetor(cliente, db, cenario):
    a = cenario["alunos"][0]
    r = cliente.put(f"/alunos/{a.id}", headers=cenario["H"],
                    json={"nome": a.nome, "ra": a.ra, "autorizou_biometria": False})
    assert r.status_code == 200
    db.refresh(a)
    assert a.embedding is None and a.consentimento_biometrico_em is None


# ----------------------------------------------------------------------------- ajuste e frequência (RN-15, RN-16)

def test_rn15_ajuste_prevalece_e_o_calculo_fica_gravado(cliente, cenario):
    c = cenario["alunos"][2]  # sem biometria, nunca detectado
    s = cliente.post(f"/sessoes/{cenario['turma'].id}/abrir", headers=cenario["H"]).json()
    r = cliente.put(f"/sessoes/{s['id']}/ajustes/{c.id}", headers=cenario["H"],
                    json={"situacao": "presenca", "motivo": "Sem biometria (não autorizou)"})
    assert r.status_code == 200
    rel = cliente.post(f"/sessoes/{s['id']}/encerrar", headers=cenario["H"]).json()
    linha = next(x for x in rel["alunos"] if x["aluno_id"] == c.id)
    assert linha["situacao"] == "presenca" and linha["situacao_calculada"] == "falta" and linha["ajuste_manual"]


def test_rn16_frequencia_acumulada(cliente, db, cenario):
    a, b, c = cenario["alunos"]
    for i in range(4):  # 4 aulas: a em todas; b em 2 (uma por ajuste); c em nenhuma
        s = _sessao(db, cenario["turma"], inicio=T0 + timedelta(days=i))
        base = timedelta(days=i).total_seconds()
        for t in range(0, 601, 30):
            _detectar(db, s, a, base + t)
        if i == 0:
            for t in range(0, 601, 30):
                _detectar(db, s, b, base + t)
        _encerrar(db, s, base + 600)
        if i == 1:
            cliente.put(f"/sessoes/{s.id}/ajustes/{b.id}", headers=cenario["H"],
                        json={"situacao": "presenca", "motivo": "Atestado"})
    f = cliente.get(f"/turmas/{cenario['turma'].id}/frequencia", headers=cenario["H"]).json()
    por = {x["aluno_id"]: x for x in f["alunos"]}
    assert f["total_aulas"] == 4
    assert por[a.id]["percentual"] == 100 and not por[a.id]["abaixo_do_minimo"]
    assert por[b.id]["percentual"] == 50 and por[b.id]["abaixo_do_minimo"] and por[b.id]["ajustes_manuais"] == 1
    assert por[c.id]["percentual"] == 0 and por[c.id]["por_aula"] == ["F", "F", "F", "F"]


def test_rn10_turma_com_aula_nao_pode_ser_excluida(cliente, db, cenario):
    _sessao(db, cenario["turma"])
    assert cliente.delete(f"/turmas/{cenario['turma'].id}", headers=cenario["H"]).status_code == 409


# ----------------------------------------------------------------------------- câmera da sala

def test_situacao_da_camera():
    agora = datetime(2026, 10, 7, 10, 0, 0)
    sessao = SimpleNamespace(id=9, sala_id=5, turma_id=3, sala=SimpleNamespace(nome="Sala 101"),
                             inicio=agora - timedelta(minutes=10))
    assert main._situacao_camera(sessao, agora).situacao == "sem_sinal"
    main._contatos_ia[("sala", 5)] = (agora - timedelta(seconds=40), 9)
    assert main._situacao_camera(sessao, agora).situacao == "conectada"
    main._contatos_ia[("sala", 5)] = (agora - timedelta(seconds=90), 9)
    assert main._situacao_camera(sessao, agora).situacao == "sem_sinal"
