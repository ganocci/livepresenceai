"""
LivePresenceAI - Backend (FastAPI)
Etapa 5: sessão em UTC, encerramento idempotente e tempo de permanência gravado.
Inclui CORS para o app Flutter rodando no navegador (protótipo local).
"""
import os
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import Base, engine, get_db
from models import Professor, Turma, Aluno, Sessao, RegistroPresenca
from schemas import (
    TurmaOut, AlunoOut, SessaoOut, EventoReconhecimento, RelatorioSessao,
    RegistroPresencaOut, SituacaoAlunoOut,
)

app = FastAPI(title="LivePresenceAI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # somente para o protótipo local
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

SECRET_KEY = "troque-esta-chave-antes-de-usar-em-producao"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120
CONFIANCA_MINIMA = 0.6
# Intervalo maximo entre duas deteccoes para considerar que o aluno continuou na sala.
# Acima disso, o periodo sem deteccao e tratado como ausencia (saiu e voltou).
LIMITE_AUSENCIA = timedelta(seconds=float(os.getenv("LIMITE_AUSENCIA_SEGUNDOS", "60")))
# RN-03: percentual minimo de permanencia para contar presenca; abaixo disso e falta.
FREQUENCIA_MINIMA = 40.0
# Sessao aberta ha mais tempo que isso e considerada abandonada (nao e retomada).
DURACAO_MAXIMA_SESSAO = timedelta(hours=4)

# RN-09: credencial do modulo de IA (e do simulador) para enviar reconhecimentos.
# O valor padrao serve apenas ao prototipo; em uso real, definir a variavel de ambiente.
CHAVE_MODULO_IA = os.getenv("CHAVE_MODULO_IA", "livepresenceai-ia-dev")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
# Mesma autenticacao, mas opcional: usada onde o JWT e uma de duas credenciais aceitas
oauth2_opcional = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

CONEXOES_WEBSOCKET: Dict[int, List[WebSocket]] = {}


def criar_token(email: str) -> str:
    expira = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": email, "exp": expira}, SECRET_KEY, algorithm=ALGORITHM)


def obter_professor_atual(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Professor:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalido")

    professor = db.query(Professor).filter(Professor.email == email).first()
    if not professor:
        raise HTTPException(status_code=401, detail="Professor nao encontrado")
    return professor


@app.get("/")
def inicio():
    return {"projeto": "LivePresenceAI", "status": "online", "documentacao": "/docs"}


@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    professor = db.query(Professor).filter(Professor.email == form_data.username).first()
    if not professor or not pwd_context.verify(form_data.password, professor.senha_hash):
        raise HTTPException(status_code=401, detail="Credenciais invalidas")
    token = criar_token(professor.email)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/turmas", response_model=List[TurmaOut])
def listar_turmas(professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    return db.query(Turma).filter(Turma.professor_id == professor.id).all()


@app.get("/turmas/{turma_id}/alunos", response_model=List[AlunoOut])
def listar_alunos(turma_id: int, professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    turma = db.query(Turma).filter(Turma.id == turma_id, Turma.professor_id == professor.id).first()
    if not turma:
        raise HTTPException(status_code=404, detail="Turma nao encontrada")
    return db.query(Aluno).filter(Aluno.turma_id == turma_id).all()


@app.post("/sessoes/{turma_id}/abrir", response_model=SessaoOut)
def abrir_sessao(turma_id: int, professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    turma = db.query(Turma).filter(Turma.id == turma_id, Turma.professor_id == professor.id).first()
    if not turma:
        raise HTTPException(status_code=404, detail="Turma nao encontrada")

    # RN-07: retoma a sessao aberta recente da turma (ex.: professor saiu da tela sem encerrar)
    # e encerra automaticamente as abandonadas, para nao acumular sessoes orfas.
    agora = datetime.utcnow()
    abertas = (
        db.query(Sessao)
        .filter(Sessao.turma_id == turma_id, Sessao.professor_id == professor.id, Sessao.status == "aberta")
        .order_by(Sessao.inicio.desc())
        .all()
    )
    retomada = None
    for aberta in abertas:
        if retomada is None and agora - aberta.inicio <= DURACAO_MAXIMA_SESSAO:
            retomada = aberta
        else:
            _encerrar_abandonada(aberta, db)
    db.commit()

    if retomada is not None:
        return _sessao_out(retomada, db, retomada=True)

    # inicio em UTC, no mesmo padrao de entrada/ultima_visualizacao/fim
    sessao = Sessao(
        turma_id=turma_id,
        professor_id=professor.id,
        inicio=agora,
        status="aberta",
    )
    db.add(sessao)
    db.commit()
    db.refresh(sessao)
    CONEXOES_WEBSOCKET[sessao.id] = []
    return _sessao_out(sessao, db)


@app.get("/sessoes/{sessao_id}", response_model=SessaoOut)
def consultar_sessao(sessao_id: int, professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    """Estado atual da sessao; o app usa para se ressincronizar apos reconectar o WebSocket."""
    sessao = db.query(Sessao).filter(Sessao.id == sessao_id, Sessao.professor_id == professor.id).first()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada")
    return _sessao_out(sessao, db)


def _sessao_out(sessao: Sessao, db: Session, retomada: bool = False) -> SessaoOut:
    """Sessao com os registros ja feitos e os parametros das regras, para o app exibir o estado ao vivo."""
    registros = db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id == sessao.id).all()
    return SessaoOut.model_validate(sessao).model_copy(update={
        "retomada": retomada,
        "registros": [RegistroPresencaOut.model_validate(r) for r in registros],
        "frequencia_minima": FREQUENCIA_MINIMA,
        "limite_ausencia_segundos": LIMITE_AUSENCIA.total_seconds(),
    })


def _fechar_sessao(sessao: Sessao, registros: List[RegistroPresenca], fim: datetime) -> None:
    """Marca a sessao como encerrada e grava o tempo final e o percentual de cada registro."""
    sessao.status = "encerrada"
    sessao.fim = fim
    duracao_total = max((sessao.fim - sessao.inicio).total_seconds(), 1)

    for registro in registros:
        permanencia = registro.tempo_total_presente or timedelta(0)
        # Aluno visto pouco antes do encerramento continuou na sala ate o fim
        restante = sessao.fim - registro.ultima_visualizacao
        if timedelta(0) <= restante <= LIMITE_AUSENCIA:
            permanencia += restante
        registro.tempo_total_presente = permanencia
        registro.percentual_presenca = round(
            min(100.0, (permanencia.total_seconds() / duracao_total) * 100), 2
        )


def _encerrar_abandonada(sessao: Sessao, db: Session) -> None:
    """Sessao esquecida aberta: o fim e a ultima atividade registrada (ou o proprio inicio)."""
    registros = db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id == sessao.id).all()
    ultima_atividade = max((r.ultima_visualizacao for r in registros), default=sessao.inicio)
    _fechar_sessao(sessao, registros, max(ultima_atividade, sessao.inicio))
    CONEXOES_WEBSOCKET.pop(sessao.id, None)


def _aplicar_deteccao(db: Session, sessao_id: int, evento: EventoReconhecimento, agora: datetime) -> RegistroPresenca:
    """RN-01/RN-02: cria o registro na primeira deteccao ou acumula tempo nas seguintes."""
    registro = (
        db.query(RegistroPresenca)
        .filter(RegistroPresenca.sessao_id == sessao_id, RegistroPresenca.aluno_id == evento.aluno_id)
        .first()
    )
    if registro is None:
        registro = RegistroPresenca(
            sessao_id=sessao_id,
            aluno_id=evento.aluno_id,
            entrada=agora,
            ultima_visualizacao=agora,
            tempo_total_presente=timedelta(0),
            confianca_media=evento.confianca,
            numero_deteccoes=1,
        )
        db.add(registro)
        db.flush()
        return registro

    intervalo = agora - registro.ultima_visualizacao
    if intervalo <= LIMITE_AUSENCIA:
        registro.tempo_total_presente = (registro.tempo_total_presente or timedelta(0)) + intervalo
    registro.ultima_visualizacao = agora

    # Media aritmetica incremental de todas as deteccoes aceitas
    n = registro.numero_deteccoes or 1
    registro.confianca_media = (float(registro.confianca_media or 0) * n + evento.confianca) / (n + 1)
    registro.numero_deteccoes = n + 1
    return registro


@app.post("/sessoes/{sessao_id}/reconhecimento")
async def registrar_reconhecimento(
    sessao_id: int,
    evento: EventoReconhecimento,
    x_api_key: Optional[str] = Header(default=None, description="Chave do modulo de IA"),
    token: Optional[str] = Depends(oauth2_opcional),
    db: Session = Depends(get_db),
):
    """
    Chamado pela IA (ou pelo simulador). Regra de negocio do TCC:
    primeira deteccao = entrada; seguintes = atualiza ultima visualizacao e
    acumula o tempo presente (intervalos maiores que LIMITE_AUSENCIA nao contam);
    confianca abaixo do limite nao conta como presenca.

    RN-09: exige a chave do modulo de IA (cabecalho X-API-Key) ou o JWT do
    professor dono da sessao (botao de simulacao do app).
    """
    chave_valida = x_api_key is not None and secrets.compare_digest(x_api_key, CHAVE_MODULO_IA)
    professor = None
    if not chave_valida:
        if not token:
            raise HTTPException(status_code=401, detail="Credencial do modulo de IA ausente ou invalida")
        professor = obter_professor_atual(token, db)

    sessao = db.query(Sessao).filter(Sessao.id == sessao_id, Sessao.status == "aberta").first()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada ou ja encerrada")
    if professor is not None and sessao.professor_id != professor.id:
        raise HTTPException(status_code=403, detail="Sessao pertence a outro professor")

    if not 0 <= evento.confianca <= 1:
        raise HTTPException(status_code=422, detail="Confianca deve estar entre 0 e 1")

    # RN-08: so aceita alunos da turma da sessao (evita presenca em turma errada e erro de FK)
    aluno = db.query(Aluno).filter(Aluno.id == evento.aluno_id, Aluno.turma_id == sessao.turma_id).first()
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno nao pertence a turma desta sessao")

    if evento.confianca < CONFIANCA_MINIMA:
        return {"registrado": False, "motivo": "confianca abaixo do limite"}

    agora = datetime.utcnow()
    try:
        registro = _aplicar_deteccao(db, sessao_id, evento, agora)
        db.commit()
    except IntegrityError:
        # Duas deteccoes simultaneas do mesmo aluno tentaram criar o registro;
        # a restricao UNIQUE barrou a segunda, que e reaplicada como atualizacao.
        db.rollback()
        registro = _aplicar_deteccao(db, sessao_id, evento, agora)
        db.commit()

    mensagem = {
        "aluno_id": evento.aluno_id,
        "horario": agora.isoformat(),
        "entrada": registro.entrada.isoformat(),
        "tempo_total_presente": registro.tempo_total_presente.total_seconds(),
    }

    for ws in list(CONEXOES_WEBSOCKET.get(sessao_id, [])):
        try:
            await ws.send_json(mensagem)
        except Exception:
            CONEXOES_WEBSOCKET[sessao_id].remove(ws)

    return {"registrado": True}


@app.post("/sessoes/{sessao_id}/encerrar", response_model=RelatorioSessao)
def encerrar_sessao(sessao_id: int, professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    sessao = db.query(Sessao).filter(Sessao.id == sessao_id, Sessao.professor_id == professor.id).first()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada")

    registros = db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id == sessao_id).all()

    # Idempotente: o fechamento (fim, tempo final e percentual) so e calculado uma vez
    if sessao.status != "encerrada":
        _fechar_sessao(sessao, registros, datetime.utcnow())
        db.commit()

    # RN-03: situacao calculada para todos os alunos da turma; o percentual e o tempo
    # continuam guardados em registro_presenca para auditoria, mesmo quando e falta.
    registro_por_aluno = {r.aluno_id: r for r in registros}
    alunos = db.query(Aluno).filter(Aluno.turma_id == sessao.turma_id).order_by(Aluno.nome).all()
    situacoes = []
    for aluno in alunos:
        registro = registro_por_aluno.get(aluno.id)
        percentual = float(registro.percentual_presenca or 0) if registro else 0.0
        situacoes.append(SituacaoAlunoOut(
            aluno_id=aluno.id,
            nome=aluno.nome,
            detectado=registro is not None,
            entrada=registro.entrada if registro else None,
            tempo_total_presente=(
                registro.tempo_total_presente.total_seconds()
                if registro and registro.tempo_total_presente else 0.0
            ),
            percentual_presenca=percentual,
            situacao="presenca" if percentual >= FREQUENCIA_MINIMA else "falta",
        ))

    total_presencas = sum(1 for s in situacoes if s.situacao == "presenca")
    return RelatorioSessao(
        sessao_id=sessao.id,
        status=sessao.status,
        frequencia_minima=FREQUENCIA_MINIMA,
        total_presencas=total_presencas,
        total_faltas=len(situacoes) - total_presencas,
        alunos=situacoes,
        registros=[RegistroPresencaOut.model_validate(r) for r in registros],
    )


@app.websocket("/ws/sessoes/{sessao_id}")
async def websocket_sessao(websocket: WebSocket, sessao_id: int):
    await websocket.accept()
    CONEXOES_WEBSOCKET.setdefault(sessao_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in CONEXOES_WEBSOCKET.get(sessao_id, []):
            CONEXOES_WEBSOCKET[sessao_id].remove(websocket)
