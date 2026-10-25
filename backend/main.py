"""
LivePresenceAI - Backend (FastAPI)
Etapa 5: sessão em UTC, encerramento idempotente e tempo de permanência gravado.
Inclui CORS para o app Flutter rodando no navegador (protótipo local).
"""
import os
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import (FastAPI, HTTPException, Depends, File, Header, Query, Request, Response, UploadFile,
                     WebSocket, WebSocketDisconnect)
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine, get_db
from models import AjustePresenca, Professor, Sala, Turma, Aluno, Sessao, RegistroPresenca
from schemas import (
    TurmaOut, AlunoOut, SessaoOut, EventoReconhecimento, RelatorioSessao,
    RegistroPresencaOut, SituacaoAlunoOut,
    AlunoCadastroIA, CadastroFacialIn, AlunoGaleriaIA, SessaoAtivaIA,
    AulaFrequenciaOut, FrequenciaAlunoOut, FrequenciaTurmaOut,
    TurmaIn, AlunoIn, SessaoResumoOut,
    ProfessorOut, PrimeiroAcessoIn, ProfessorIn, TrocaSenhaIn, SalaOut, SalaIn, AjusteIn, AjusteOut, CameraSalaOut,
)
import biometria
import descoberta
import exportacao
import migracoes

app = FastAPI(title="LivePresenceAI Backend")

# Origens do app autorizadas (separadas por virgula); "*" so para desenvolvimento
ORIGENS_CORS = [o.strip() for o in os.getenv("CORS_ORIGENS", "*").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGENS_CORS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # nome do arquivo exportado, lido pelo app
)

# Cria tabelas que faltam e aplica as migracoes pendentes (database/migracao_*.sql)
migracoes.preparar_banco(engine, Base)

# Responde aos apps que procuram o servidor na rede local (UDP 47800), para nao precisarem do IP
_aviso_descoberta = descoberta.iniciar()
if _aviso_descoberta:
    print("AVISO:", _aviso_descoberta)

# Chave de assinatura do JWT: em uso real vem do ambiente (o instalador gera uma aleatoria)
SECRET_KEY = os.getenv("SECRET_KEY_JWT") or "troque-esta-chave-antes-de-usar-em-producao"
if SECRET_KEY == "troque-esta-chave-antes-de-usar-em-producao":
    print("AVISO: SECRET_KEY_JWT nao definida; usando a chave de desenvolvimento (nao use em producao).")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 120
# RN-04: com a IA real, a confianca enviada e a similaridade do rosto com o cadastro do aluno;
# o limite sera calibrado no experimento E1 (variavel de ambiente CONFIANCA_MINIMA).
CONFIANCA_MINIMA = float(os.getenv("CONFIANCA_MINIMA", "0.6"))
# Intervalo maximo entre duas deteccoes para considerar que o aluno continuou na sala.
# Acima disso, o periodo sem deteccao e tratado como ausencia (saiu e voltou).
LIMITE_AUSENCIA = timedelta(seconds=float(os.getenv("LIMITE_AUSENCIA_SEGUNDOS", "60")))
# RN-03: percentual minimo de permanencia para contar presenca; abaixo disso e falta. Politica de cada
# instituicao: ajustavel pela variavel de ambiente (o painel a define a partir da configuracao).
FREQUENCIA_MINIMA = float(os.getenv("FREQUENCIA_MINIMA_AULA", "40"))
# RN-16: frequencia minima no periodo (% das aulas com presenca). 75% e um valor comum no ensino superior;
# cada instituicao ajusta a sua regra por variavel de ambiente
FREQUENCIA_MINIMA_TURMA = float(os.getenv("FREQUENCIA_MINIMA_TURMA", "75"))
# Sessao aberta ha mais tempo que isso e considerada abandonada (nao e retomada).
DURACAO_MAXIMA_SESSAO = timedelta(hours=4)

# RN-09: credencial do modulo de IA (e do simulador) para enviar reconhecimentos.
# O valor padrao serve apenas ao prototipo; em uso real, definir a variavel de ambiente.
CHAVE_MODULO_IA = os.getenv("CHAVE_MODULO_IA", "livepresenceai-ia-dev")
# Tamanho do vetor de caracteristicas do modelo de reconhecimento (ArcFace do InsightFace)
TAMANHO_EMBEDDING = 512

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
# Mesma autenticacao, mas opcional: usada onde o JWT e uma de duas credenciais aceitas
oauth2_opcional = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)

CONEXOES_WEBSOCKET: Dict[int, List[WebSocket]] = {}


def criar_token(email: str) -> str:
    expira = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": email, "exp": expira}, SECRET_KEY, algorithm=ALGORITHM)


def _professor_do_token(token: Optional[str], db: Session) -> Optional[Professor]:
    """Professor dono de um JWT valido, ou None (token ausente, invalido, expirado ou de conta inexistente)."""
    if not token:
        return None
    try:
        email = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]).get("sub")
    except JWTError:
        return None
    professor = db.query(Professor).filter(Professor.email == email).first()
    return professor if professor is not None and professor.ativo else None


def obter_professor_atual(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Professor:
    professor = _professor_do_token(token, db)
    if not professor:
        raise HTTPException(status_code=401, detail="Sessão expirada ou inválida")
    return professor


def _chave_ia_valida(x_api_key: Optional[str]) -> bool:
    return x_api_key is not None and secrets.compare_digest(x_api_key, CHAVE_MODULO_IA)


def exigir_chave_ia(x_api_key: Optional[str] = Header(default=None, description="Chave do modulo de IA")):
    """Rotas /ia/*: usadas so pelo modulo de visao computacional (RN-09)."""
    if not _chave_ia_valida(x_api_key):
        raise HTTPException(status_code=401, detail="Credencial do módulo de IA ausente ou inválida")


# App web do professor (Flutter compilado com --base-href /app/), entregue pelo proprio backend: um unico
# endereco para o app e a API, sem CORS. Pasta configuravel por APP_WEB_DIR.
APP_WEB_DIR = os.getenv("APP_WEB_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                    "app", "build", "web"))
APP_WEB_DISPONIVEL = os.path.isfile(os.path.join(APP_WEB_DIR, "index.html"))
class _ArquivosSemCacheVelho(StaticFiles):
    """Pede ao navegador para revalidar (ETag) a cada uso: depois de uma atualizacao, o app novo aparece logo,
    em vez de uma copia antiga guardada pelo cache heuristico do navegador. Sem mudanca, a resposta e um 304."""

    async def get_response(self, path, scope):
        resposta = await super().get_response(path, scope)
        resposta.headers["Cache-Control"] = "no-cache"
        return resposta


if APP_WEB_DISPONIVEL:
    app.mount("/app", _ArquivosSemCacheVelho(directory=APP_WEB_DIR, html=True), name="app_web")


# APK do app Android, para os celulares baixarem pelo navegador em /android (gerado por app/gerar_apk.ps1)
APK_ANDROID = os.getenv("APK_ANDROID", os.path.join(os.path.dirname(APP_WEB_DIR), "app", "outputs", "flutter-apk",
                                                    "app-release.apk"))


@app.get("/android", include_in_schema=False)
def baixar_apk():
    if not os.path.isfile(APK_ANDROID):
        raise HTTPException(status_code=404, detail="O app Android ainda não foi gerado neste servidor")
    return FileResponse(APK_ANDROID, media_type="application/vnd.android.package-archive",
                        filename="LivePresenceAI.apk")


@app.get("/")
def inicio(request: Request):
    """Status do servico; um navegador (que pede HTML) e levado ao app web, se ele estiver compilado."""
    if APP_WEB_DISPONIVEL and "text/html" in request.headers.get("accept", ""):
        return RedirectResponse("/app/")
    return {"projeto": "LivePresenceAI", "status": "online", "documentacao": "/docs",
            "app_web": "/app/" if APP_WEB_DISPONIVEL else None}


# Protecao contra tentativa de senhas (forca bruta): apos LOGIN_TENTATIVAS_MAX erros para o mesmo e-mail (ou 4 vezes
# isso a partir do mesmo endereco de rede, para nao travar um laboratorio inteiro), o login fica bloqueado ate
# LOGIN_BLOQUEIO_MINUTOS depois do primeiro erro da sequencia (em memoria; reiniciar o servidor zera).
LOGIN_TENTATIVAS_MAX = int(os.getenv("LOGIN_TENTATIVAS_MAX", "5"))
LOGIN_BLOQUEIO = timedelta(minutes=float(os.getenv("LOGIN_BLOQUEIO_MINUTOS", "15")))
_erros_login: Dict[str, List[datetime]] = {}


def _chaves_login(email: str, request: Request) -> List[str]:
    return [f"email:{email}", f"ip:{request.client.host if request.client else '?'}"]


def _verificar_bloqueio_login(chaves: List[str], agora: datetime) -> None:
    for chave in chaves:
        erros = [t for t in _erros_login.get(chave, []) if agora - t < LOGIN_BLOQUEIO]
        _erros_login[chave] = erros
        limite = LOGIN_TENTATIVAS_MAX if chave.startswith("email:") else 4 * LOGIN_TENTATIVAS_MAX
        if len(erros) >= limite:
            minutos = max(1, int((erros[0] + LOGIN_BLOQUEIO - agora).total_seconds() // 60) + 1)
            raise HTTPException(status_code=429, detail=f"Muitas tentativas de login. Aguarde {minutos} min e "
                                                        "tente de novo, ou peça ao administrador para redefinir a senha.")


@app.post("/login")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form_data.username.strip().lower()
    chaves, agora = _chaves_login(email, request), datetime.utcnow()
    _verificar_bloqueio_login(chaves, agora)
    professor = db.query(Professor).filter(Professor.email == email).first()
    if not professor or not pwd_context.verify(form_data.password, professor.senha_hash):
        for chave in chaves:
            _erros_login.setdefault(chave, []).append(agora)
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos")
    _erros_login.pop(chaves[0], None)  # acerto zera so o e-mail: o contador do endereco de rede continua
    if not professor.ativo:
        raise HTTPException(status_code=401, detail="Conta desativada. Procure o administrador.")
    token = criar_token(professor.email)
    return {"access_token": token, "token_type": "bearer"}


def exigir_administrador(professor: Professor = Depends(obter_professor_atual)) -> Professor:
    """Rotas de administracao (professores e salas): so para o perfil administrador."""
    if professor.perfil != "administrador":
        raise HTTPException(status_code=403, detail="Somente o administrador pode fazer isso")
    return professor


# ---------------------------------------------------------------------------
# Primeiro acesso, conta do usuario e administracao de professores
# ---------------------------------------------------------------------------

def _sistema_configurado(db: Session) -> bool:
    return db.query(Professor).filter(Professor.perfil == "administrador").count() > 0


@app.get("/configuracao/estado")
def estado_configuracao(db: Session = Depends(get_db)):
    """Publico: o app mostra a configuracao inicial enquanto nao houver administrador."""
    return {"configurado": _sistema_configurado(db)}


@app.post("/configuracao/inicial", status_code=201)
def configuracao_inicial(dados: PrimeiroAcessoIn, db: Session = Depends(get_db)):
    """Cria o primeiro administrador. So funciona uma vez (409 depois que o sistema esta configurado)."""
    if _sistema_configurado(db):
        raise HTTPException(status_code=409, detail="O sistema já foi configurado")
    if db.query(Professor).filter(Professor.email == dados.email).first():
        raise HTTPException(status_code=409, detail="Já existe uma conta com este e-mail")
    admin = Professor(nome=dados.nome, email=dados.email, senha_hash=pwd_context.hash(dados.senha),
                      perfil="administrador", ativo=True)
    db.add(admin)
    db.commit()
    return {"access_token": criar_token(admin.email), "token_type": "bearer"}


@app.get("/eu", response_model=ProfessorOut)
def quem_sou(professor: Professor = Depends(obter_professor_atual)):
    return professor


@app.put("/eu/senha", status_code=204)
def trocar_senha(dados: TrocaSenhaIn, professor: Professor = Depends(obter_professor_atual),
                 db: Session = Depends(get_db)):
    if not pwd_context.verify(dados.senha_atual, professor.senha_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta")
    professor.senha_hash = pwd_context.hash(dados.nova_senha)
    db.commit()
    return Response(status_code=204)


@app.get("/professores", response_model=List[ProfessorOut])
def listar_professores(_: Professor = Depends(exigir_administrador), db: Session = Depends(get_db)):
    return db.query(Professor).order_by(Professor.nome).all()


@app.post("/professores", response_model=ProfessorOut, status_code=201)
def criar_professor(dados: ProfessorIn, _: Professor = Depends(exigir_administrador), db: Session = Depends(get_db)):
    if not dados.senha:
        raise HTTPException(status_code=422, detail="Informe uma senha inicial (mínimo de 8 caracteres)")
    if db.query(Professor).filter(Professor.email == dados.email).first():
        raise HTTPException(status_code=409, detail="Já existe uma conta com este e-mail")
    professor = Professor(nome=dados.nome, email=dados.email, senha_hash=pwd_context.hash(dados.senha),
                          perfil=dados.perfil, ativo=dados.ativo)
    db.add(professor)
    db.commit()
    return professor


@app.put("/professores/{professor_id}", response_model=ProfessorOut)
def editar_professor(professor_id: int, dados: ProfessorIn, admin: Professor = Depends(exigir_administrador),
                     db: Session = Depends(get_db)):
    professor = db.query(Professor).filter(Professor.id == professor_id).first()
    if not professor:
        raise HTTPException(status_code=404, detail="Professor não encontrado")
    if professor.id == admin.id and (dados.perfil != "administrador" or not dados.ativo):
        raise HTTPException(status_code=409, detail="Você não pode remover o seu próprio acesso de administrador")
    outro = db.query(Professor).filter(Professor.email == dados.email, Professor.id != professor.id).first()
    if outro:
        raise HTTPException(status_code=409, detail="Já existe uma conta com este e-mail")
    professor.nome, professor.email, professor.perfil, professor.ativo = dados.nome, dados.email, dados.perfil, dados.ativo
    if dados.senha:
        professor.senha_hash = pwd_context.hash(dados.senha)
    db.commit()
    return professor


# ---------------------------------------------------------------------------
# Salas
# ---------------------------------------------------------------------------

def _sessao_aberta_na_sala(sala_id: int, db: Session) -> Optional[Sessao]:
    """Chamada aberta (e nao abandonada, RN-07) na sala, se houver."""
    return (
        db.query(Sessao)
        .filter(Sessao.sala_id == sala_id, Sessao.status == "aberta",
                Sessao.inicio >= datetime.utcnow() - DURACAO_MAXIMA_SESSAO)
        .order_by(Sessao.inicio.desc())
        .first()
    )


def _sala_out(sala: Sala, db: Session) -> SalaOut:
    return SalaOut(id=sala.id, nome=sala.nome, em_uso=_sessao_aberta_na_sala(sala.id, db) is not None)


def _gravar_sala(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe uma sala com este nome")


@app.get("/salas", response_model=List[SalaOut])
def listar_salas(_: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    return [_sala_out(s, db) for s in db.query(Sala).order_by(Sala.nome).all()]


@app.post("/salas", response_model=SalaOut, status_code=201)
def criar_sala(dados: SalaIn, _: Professor = Depends(exigir_administrador), db: Session = Depends(get_db)):
    sala = Sala(nome=dados.nome, criado_em=datetime.utcnow())
    db.add(sala)
    _gravar_sala(db)
    return _sala_out(sala, db)


@app.put("/salas/{sala_id}", response_model=SalaOut)
def renomear_sala(sala_id: int, dados: SalaIn, _: Professor = Depends(exigir_administrador),
                  db: Session = Depends(get_db)):
    sala = db.query(Sala).filter(Sala.id == sala_id).first()
    if not sala:
        raise HTTPException(status_code=404, detail="Sala não encontrada")
    sala.nome = dados.nome
    _gravar_sala(db)
    return _sala_out(sala, db)


@app.delete("/salas/{sala_id}", status_code=204)
def excluir_sala(sala_id: int, _: Professor = Depends(exigir_administrador), db: Session = Depends(get_db)):
    """So exclui sala sem nenhuma aula registrada; turmas que a usavam como padrao ficam sem sala padrao."""
    sala = db.query(Sala).filter(Sala.id == sala_id).first()
    if not sala:
        raise HTTPException(status_code=404, detail="Sala não encontrada")
    if db.query(Sessao).filter(Sessao.sala_id == sala.id).count():
        raise HTTPException(status_code=409, detail="Sala com aulas registradas não pode ser excluída")
    db.query(Turma).filter(Turma.sala_id == sala.id).update({Turma.sala_id: None}, synchronize_session=False)
    db.delete(sala)
    db.commit()
    return Response(status_code=204)


def _sala_existente(sala_id: Optional[int], db: Session) -> Optional[Sala]:
    if sala_id is None:
        return None
    sala = db.query(Sala).filter(Sala.id == sala_id).first()
    if not sala:
        raise HTTPException(status_code=404, detail="Sala não encontrada")
    return sala


def _turma_do_professor(turma_id: int, professor: Professor, db: Session) -> Turma:
    """RN-05: cada professor so acessa as proprias turmas (404 para as demais)."""
    turma = db.query(Turma).filter(Turma.id == turma_id, Turma.professor_id == professor.id).first()
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    return turma


def _aluno_do_professor(aluno_id: int, professor: Professor, db: Session) -> Aluno:
    aluno = (
        db.query(Aluno).join(Turma, Aluno.turma_id == Turma.id)
        .filter(Aluno.id == aluno_id, Turma.professor_id == professor.id)
        .first()
    )
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    return aluno


def _turma_out(turma: Turma, db: Session) -> TurmaOut:
    return TurmaOut(
        id=turma.id,
        nome=turma.nome,
        sala_id=turma.sala_id,
        sala_nome=turma.sala.nome if turma.sala else None,
        total_alunos=db.query(Aluno).filter(Aluno.turma_id == turma.id).count(),
        total_aulas=db.query(Sessao).filter(Sessao.turma_id == turma.id, Sessao.status == "encerrada").count(),
    )


def _aluno_out(aluno: Aluno) -> AlunoOut:
    return AlunoOut(id=aluno.id, nome=aluno.nome, ra=aluno.ra, turma_id=aluno.turma_id,
                    cadastro_facial=bool(aluno.embedding),
                    autorizacao_biometrica=aluno.consentimento_biometrico_em is not None,
                    autorizacao_biometrica_em=aluno.consentimento_biometrico_em)


def _aplicar_autorizacao(aluno: Aluno, autorizou: Optional[bool]) -> None:
    """RN-12: registra a autorizacao assinada na matricula; a revogacao apaga o cadastro facial."""
    if autorizou is True and aluno.consentimento_biometrico_em is None:
        aluno.consentimento_biometrico_em = datetime.utcnow()
    elif autorizou is False:
        aluno.consentimento_biometrico_em = None
        aluno.embedding = None


def _gravar_aluno(db: Session) -> None:
    """Commit tratando RA repetido (restricao uq_aluno_ra) como 409."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um aluno com este RA")


@app.get("/turmas", response_model=List[TurmaOut])
def listar_turmas(professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    turmas = db.query(Turma).filter(Turma.professor_id == professor.id).order_by(Turma.nome).all()
    return [_turma_out(t, db) for t in turmas]


@app.post("/turmas", response_model=TurmaOut, status_code=201)
def criar_turma(dados: TurmaIn, professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    _sala_existente(dados.sala_id, db)
    turma = Turma(nome=dados.nome, professor_id=professor.id, sala_id=dados.sala_id)
    db.add(turma)
    db.commit()
    return _turma_out(turma, db)


@app.put("/turmas/{turma_id}", response_model=TurmaOut)
def renomear_turma(turma_id: int, dados: TurmaIn, professor: Professor = Depends(obter_professor_atual),
                   db: Session = Depends(get_db)):
    turma = _turma_do_professor(turma_id, professor, db)
    _sala_existente(dados.sala_id, db)
    turma.nome, turma.sala_id = dados.nome, dados.sala_id
    db.commit()
    return _turma_out(turma, db)


@app.delete("/turmas/{turma_id}", status_code=204)
def excluir_turma(turma_id: int, professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    """So exclui turma sem nenhuma aula (o historico de presenca nunca e apagado); os alunos vao junto."""
    turma = _turma_do_professor(turma_id, professor, db)
    if db.query(Sessao).filter(Sessao.turma_id == turma.id).count():
        raise HTTPException(status_code=409, detail="Turma com aulas registradas não pode ser excluída")
    db.query(Aluno).filter(Aluno.turma_id == turma.id).delete(synchronize_session=False)
    db.delete(turma)
    db.commit()
    return Response(status_code=204)


@app.get("/turmas/{turma_id}/alunos", response_model=List[AlunoOut])
def listar_alunos(turma_id: int, professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    _turma_do_professor(turma_id, professor, db)
    alunos = db.query(Aluno).filter(Aluno.turma_id == turma_id).order_by(Aluno.nome).all()
    return [_aluno_out(a) for a in alunos]


@app.post("/turmas/{turma_id}/alunos", response_model=AlunoOut, status_code=201)
def criar_aluno(turma_id: int, dados: AlunoIn, professor: Professor = Depends(obter_professor_atual),
                db: Session = Depends(get_db)):
    _turma_do_professor(turma_id, professor, db)
    aluno = Aluno(nome=dados.nome, ra=dados.ra, turma_id=turma_id, criado_em=datetime.utcnow())
    _aplicar_autorizacao(aluno, dados.autorizou_biometria)
    db.add(aluno)
    _gravar_aluno(db)
    return _aluno_out(aluno)


@app.put("/alunos/{aluno_id}", response_model=AlunoOut)
def editar_aluno(aluno_id: int, dados: AlunoIn, professor: Professor = Depends(obter_professor_atual),
                 db: Session = Depends(get_db)):
    aluno = _aluno_do_professor(aluno_id, professor, db)
    aluno.nome, aluno.ra = dados.nome, dados.ra
    _aplicar_autorizacao(aluno, dados.autorizou_biometria)
    _gravar_aluno(db)
    return _aluno_out(aluno)


@app.post("/alunos/{aluno_id}/rosto", response_model=AlunoOut)
def cadastrar_rosto(
    aluno_id: int,
    fotos: List[UploadFile] = File(..., description="3 a 5 fotos do rosto do aluno (JPEG ou PNG)"),
    professor: Professor = Depends(obter_professor_atual),
    db: Session = Depends(get_db),
):
    """
    Cadastro facial pelo app: o professor fotografa o aluno com o celular. As fotos viram o vetor de
    caracteristicas em memoria e sao descartadas; so o vetor e gravado. Exige a autorizacao (RN-12).
    """
    aluno = _aluno_do_professor(aluno_id, professor, db)
    if aluno.consentimento_biometrico_em is None:
        raise HTTPException(status_code=409,
                            detail="Aluno sem autorização de biometria registrada (assinada na matrícula)")
    try:
        vetor, _ = biometria.gerar_vetor([foto.file.read() for foto in fotos])
    except biometria.FotoRecusada as erro:
        raise HTTPException(status_code=422, detail=str(erro))
    aluno.embedding = vetor
    db.commit()
    return _aluno_out(aluno)


@app.delete("/alunos/{aluno_id}/rosto", response_model=AlunoOut)
def excluir_rosto(aluno_id: int, professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    """Apaga o cadastro facial (o aluno continua autorizado e pode ser cadastrado de novo)."""
    aluno = _aluno_do_professor(aluno_id, professor, db)
    aluno.embedding = None
    db.commit()
    return _aluno_out(aluno)


@app.delete("/alunos/{aluno_id}", status_code=204)
def excluir_aluno(aluno_id: int, professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    """Aluno com presenca registrada nao pode ser excluido (preserva o historico das aulas)."""
    aluno = _aluno_do_professor(aluno_id, professor, db)
    if (db.query(RegistroPresenca).filter(RegistroPresenca.aluno_id == aluno.id).count()
            or db.query(AjustePresenca).filter(AjustePresenca.aluno_id == aluno.id).count()):
        raise HTTPException(status_code=409, detail="Aluno com presenças registradas não pode ser excluído")
    db.delete(aluno)  # o cadastro facial (embedding) e apagado junto
    db.commit()
    return Response(status_code=204)


@app.post("/sessoes/{turma_id}/abrir", response_model=SessaoOut)
def abrir_sessao(turma_id: int, sala_id: Optional[int] = None, professor: Professor = Depends(obter_professor_atual),
                 db: Session = Depends(get_db)):
    """
    Abre (ou retoma, RN-07) a chamada da turma na sala informada em ?sala_id= ou, sem ela, na sala padrao
    da turma. RN-13: uma sala so pode ter uma chamada aberta por vez (409 se outra turma ja estiver nela).
    """
    turma = db.query(Turma).filter(Turma.id == turma_id, Turma.professor_id == professor.id).first()
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    sala = _sala_existente(sala_id if sala_id is not None else turma.sala_id, db)

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

    if sala is not None:
        ocupada = _sessao_aberta_na_sala(sala.id, db)
        if ocupada is not None:
            raise HTTPException(status_code=409,
                                detail=f"A {sala.nome} já está com a chamada da turma {ocupada.turma.nome} aberta")

    # inicio em UTC, no mesmo padrao de entrada/ultima_visualizacao/fim
    sessao = Sessao(
        turma_id=turma_id,
        professor_id=professor.id,
        inicio=agora,
        status="aberta",
        sala_id=sala.id if sala else None,
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
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return _sessao_out(sessao, db)


def _sessao_out(sessao: Sessao, db: Session, retomada: bool = False) -> SessaoOut:
    """Sessao com os registros ja feitos e os parametros das regras, para o app exibir o estado ao vivo."""
    registros = db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id == sessao.id).all()
    return SessaoOut.model_validate(sessao).model_copy(update={
        "retomada": retomada,
        "sala_nome": sessao.sala.nome if sessao.sala else None,
        "registros": [RegistroPresencaOut.model_validate(r) for r in registros],
        "frequencia_minima": FREQUENCIA_MINIMA,
        "limite_ausencia_segundos": LIMITE_AUSENCIA.total_seconds(),
        "ajustes": [_ajuste_out(a) for a in db.query(AjustePresenca).filter(AjustePresenca.sessao_id == sessao.id)],
    })


def _ajuste_out(ajuste: AjustePresenca) -> AjusteOut:
    return AjusteOut(aluno_id=ajuste.aluno_id, situacao=ajuste.situacao, motivo=ajuste.motivo,
                     professor_nome=ajuste.professor.nome if ajuste.professor else None, criado_em=ajuste.criado_em)


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
    professor = None
    if not _chave_ia_valida(x_api_key):
        if not token:
            raise HTTPException(status_code=401, detail="Credencial do módulo de IA ausente ou inválida")
        professor = obter_professor_atual(token, db)

    sessao = db.query(Sessao).filter(Sessao.id == sessao_id, Sessao.status == "aberta").first()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada ou já encerrada")
    if professor is not None and sessao.professor_id != professor.id:
        raise HTTPException(status_code=403, detail="Sessão pertence a outro professor")

    if not 0 <= evento.confianca <= 1:
        raise HTTPException(status_code=422, detail="Confiança deve estar entre 0 e 1")

    # RN-08: so aceita alunos da turma da sessao (evita presenca em turma errada e erro de FK)
    aluno = db.query(Aluno).filter(Aluno.id == evento.aluno_id, Aluno.turma_id == sessao.turma_id).first()
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não pertence à turma desta sessão")

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
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    registros = db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id == sessao_id).all()

    # Idempotente: o fechamento (fim, tempo final e percentual) so e calculado uma vez
    if sessao.status != "encerrada":
        _fechar_sessao(sessao, registros, datetime.utcnow())
        db.commit()

    return _montar_relatorio(sessao, registros, db)


def _alunos_da_aula(sessao: Sessao, registros: List[RegistroPresenca], db: Session) -> List[Aluno]:
    """
    Alunos que fazem parte do relatorio de uma aula: os da turma que ja existiam ate o fim dela
    (quem foi incluido depois nao aparece como falta em aulas antigas) e todos os que tem registro.
    """
    fim = sessao.fim or datetime.utcnow()
    com_registro = {r.aluno_id for r in registros}
    alunos = db.query(Aluno).filter(Aluno.turma_id == sessao.turma_id).order_by(Aluno.nome).all()
    return [a for a in alunos if a.id in com_registro or a.criado_em is None or a.criado_em <= fim]


def _montar_relatorio(sessao: Sessao, registros: List[RegistroPresenca], db: Session) -> RelatorioSessao:
    # RN-03: situacao calculada para todos os alunos da turma; o percentual e o tempo
    # continuam guardados em registro_presenca para auditoria, mesmo quando e falta.
    registro_por_aluno = {r.aluno_id: r for r in registros}
    ajustes = {a.aluno_id: a for a in db.query(AjustePresenca).filter(AjustePresenca.sessao_id == sessao.id)}
    situacoes = []
    for aluno in _alunos_da_aula(sessao, registros, db):
        registro = registro_por_aluno.get(aluno.id)
        percentual = float(registro.percentual_presenca or 0) if registro else 0.0
        calculada = "presenca" if percentual >= FREQUENCIA_MINIMA else "falta"
        ajuste = ajustes.get(aluno.id)  # RN-15: o ajuste manual prevalece sobre o calculo
        situacoes.append(SituacaoAlunoOut(
            aluno_id=aluno.id,
            nome=aluno.nome,
            ra=aluno.ra,
            detectado=registro is not None,
            entrada=registro.entrada if registro else None,
            tempo_total_presente=(
                registro.tempo_total_presente.total_seconds()
                if registro and registro.tempo_total_presente else 0.0
            ),
            percentual_presenca=percentual,
            situacao=ajuste.situacao if ajuste else calculada,
            situacao_calculada=calculada,
            ajuste_manual=ajuste is not None,
            motivo_ajuste=ajuste.motivo if ajuste else None,
        ))

    total_presencas = sum(1 for s in situacoes if s.situacao == "presenca")
    turma = db.query(Turma).filter(Turma.id == sessao.turma_id).first()
    professor = db.query(Professor).filter(Professor.id == sessao.professor_id).first()
    return RelatorioSessao(
        sessao_id=sessao.id,
        status=sessao.status,
        turma_id=sessao.turma_id,
        turma_nome=turma.nome if turma else None,
        professor_nome=professor.nome if professor else None,
        sala_nome=sessao.sala.nome if sessao.sala else None,
        inicio=sessao.inicio,
        fim=sessao.fim,
        frequencia_minima=FREQUENCIA_MINIMA,
        total_presencas=total_presencas,
        total_faltas=len(situacoes) - total_presencas,
        alunos=situacoes,
        registros=[RegistroPresencaOut.model_validate(r) for r in registros],
    )


def _relatorio_de_aula_encerrada(sessao_id: int, professor: Professor, db: Session) -> RelatorioSessao:
    sessao = db.query(Sessao).filter(Sessao.id == sessao_id, Sessao.professor_id == professor.id).first()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if sessao.status != "encerrada":
        raise HTTPException(status_code=409, detail="A chamada ainda está aberta; encerre-a para ver o relatório")
    registros = db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id == sessao.id).all()
    return _montar_relatorio(sessao, registros, db)


@app.put("/sessoes/{sessao_id}/ajustes/{aluno_id}", response_model=AjusteOut)
def ajustar_chamada(sessao_id: int, aluno_id: int, dados: AjusteIn,
                    professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    """
    RN-15: o professor dono da aula marca presenca ou falta de um aluno, com motivo (aluno sem autorizacao
    de biometria, camera nao reconheceu, falta justificada...). Vale com a chamada aberta ou ja encerrada;
    refazer substitui o ajuste anterior.
    """
    sessao = db.query(Sessao).filter(Sessao.id == sessao_id, Sessao.professor_id == professor.id).first()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if not db.query(Aluno).filter(Aluno.id == aluno_id, Aluno.turma_id == sessao.turma_id).first():
        raise HTTPException(status_code=404, detail="Aluno não pertence à turma desta sessão")
    ajuste = db.query(AjustePresenca).filter(AjustePresenca.sessao_id == sessao_id,
                                             AjustePresenca.aluno_id == aluno_id).first()
    if ajuste is None:
        ajuste = AjustePresenca(sessao_id=sessao_id, aluno_id=aluno_id)
        db.add(ajuste)
    ajuste.situacao, ajuste.motivo = dados.situacao, dados.motivo
    ajuste.professor_id, ajuste.criado_em = professor.id, datetime.utcnow()
    db.commit()
    db.refresh(ajuste)
    return _ajuste_out(ajuste)


@app.delete("/sessoes/{sessao_id}/ajustes/{aluno_id}", status_code=204)
def remover_ajuste(sessao_id: int, aluno_id: int, professor: Professor = Depends(obter_professor_atual),
                   db: Session = Depends(get_db)):
    """Desfaz o ajuste manual: volta a valer a situacao calculada."""
    sessao = db.query(Sessao).filter(Sessao.id == sessao_id, Sessao.professor_id == professor.id).first()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    db.query(AjustePresenca).filter(AjustePresenca.sessao_id == sessao_id,
                                    AjustePresenca.aluno_id == aluno_id).delete(synchronize_session=False)
    db.commit()
    return Response(status_code=204)


@app.get("/turmas/{turma_id}/sessoes", response_model=List[SessaoResumoOut])
def historico_turma(turma_id: int, professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    """Aulas da turma, da mais recente para a mais antiga, com os totais de cada uma."""
    _turma_do_professor(turma_id, professor, db)
    sessoes = db.query(Sessao).filter(Sessao.turma_id == turma_id).order_by(Sessao.inicio.desc()).all()
    resumo = []
    for sessao in sessoes:
        item = SessaoResumoOut(id=sessao.id, status=sessao.status, inicio=sessao.inicio, fim=sessao.fim)
        if sessao.status == "encerrada":
            registros = db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id == sessao.id).all()
            relatorio = _montar_relatorio(sessao, registros, db)
            item.total_presencas, item.total_faltas = relatorio.total_presencas, relatorio.total_faltas
            if sessao.fim:
                item.duracao_segundos = (sessao.fim - sessao.inicio).total_seconds()
        resumo.append(item)
    return resumo


def _frequencia_turma(turma_id: int, professor: Professor, db: Session) -> FrequenciaTurmaOut:
    """
    RN-16: frequencia acumulada de cada aluno nas aulas ENCERRADAS da turma, contando a situacao final de cada
    aula (com os ajustes manuais da RN-15). Um aluno incluido no meio do periodo so conta as aulas a partir
    da inclusao, como no relatorio de cada aula.
    """
    turma = _turma_do_professor(turma_id, professor, db)
    sessoes = (db.query(Sessao).filter(Sessao.turma_id == turma.id, Sessao.status == "encerrada")
               .order_by(Sessao.inicio).all())
    situacoes: Dict[int, Dict[int, SituacaoAlunoOut]] = {}  # sessao_id -> aluno_id -> situacao
    for sessao in sessoes:
        registros = db.query(RegistroPresenca).filter(RegistroPresenca.sessao_id == sessao.id).all()
        situacoes[sessao.id] = {a.aluno_id: a for a in _montar_relatorio(sessao, registros, db).alunos}

    alunos = {a.id: (a.nome, a.ra) for a in db.query(Aluno).filter(Aluno.turma_id == turma.id)}
    for por_aluno in situacoes.values():  # quem tem registro antigo e saiu da turma continua no historico
        for aluno_id, sit in por_aluno.items():
            alunos.setdefault(aluno_id, (sit.nome, sit.ra))

    linhas = []
    for aluno_id, (nome, ra) in alunos.items():
        por_aula = []
        for sessao in sessoes:
            sit = situacoes[sessao.id].get(aluno_id)
            por_aula.append(None if sit is None else ("P" if sit.situacao == "presenca" else "F"))
        aulas = sum(1 for p in por_aula if p)
        presencas = por_aula.count("P")
        ajustes = sum(1 for s in sessoes if (sit := situacoes[s.id].get(aluno_id)) and sit.ajuste_manual)
        percentual = round(100 * presencas / aulas, 2) if aulas else None
        linhas.append(FrequenciaAlunoOut(
            aluno_id=aluno_id, nome=nome, ra=ra, aulas=aulas, presencas=presencas, faltas=aulas - presencas,
            ajustes_manuais=ajustes, percentual=percentual,
            abaixo_do_minimo=percentual is not None and percentual < FREQUENCIA_MINIMA_TURMA, por_aula=por_aula))
    linhas.sort(key=lambda l: l.nome.lower())
    dono = db.query(Professor).filter(Professor.id == turma.professor_id).first()
    return FrequenciaTurmaOut(
        turma_id=turma.id, turma_nome=turma.nome, professor_nome=dono.nome if dono else None,
        frequencia_minima=FREQUENCIA_MINIMA_TURMA, frequencia_minima_aula=FREQUENCIA_MINIMA,
        total_aulas=len(sessoes),
        aulas=[AulaFrequenciaOut(sessao_id=s.id, inicio=s.inicio, fim=s.fim) for s in sessoes],
        alunos=linhas, alunos_abaixo_do_minimo=sum(1 for l in linhas if l.abaixo_do_minimo))


@app.get("/turmas/{turma_id}/frequencia", response_model=FrequenciaTurmaOut)
def frequencia_turma(turma_id: int, professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    """Frequencia acumulada de cada aluno nas aulas encerradas da turma (RN-16)."""
    return _frequencia_turma(turma_id, professor, db)


@app.get("/turmas/{turma_id}/frequencia/exportar")
def exportar_frequencia(
    turma_id: int,
    formato: str = Query(..., pattern="^(csv|xlsx|pdf)$", description="csv, xlsx ou pdf"),
    professor: Professor = Depends(obter_professor_atual),
    db: Session = Depends(get_db),
):
    """Frequencia acumulada como arquivo (XLSX com a grade aluno x aula)."""
    conteudo, tipo, nome = exportacao.gerar_frequencia(_frequencia_turma(turma_id, professor, db), formato)
    return Response(content=conteudo, media_type=tipo,
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@app.get("/sessoes/{sessao_id}/relatorio", response_model=RelatorioSessao)
def relatorio_sessao(sessao_id: int, professor: Professor = Depends(obter_professor_atual), db: Session = Depends(get_db)):
    """Relatorio de uma aula ja encerrada (historico); nao altera nada."""
    return _relatorio_de_aula_encerrada(sessao_id, professor, db)


@app.get("/sessoes/{sessao_id}/exportar")
def exportar_sessao(
    sessao_id: int,
    formato: str = Query(..., pattern="^(csv|xlsx|pdf)$", description="csv, xlsx ou pdf"),
    professor: Professor = Depends(obter_professor_atual),
    db: Session = Depends(get_db),
):
    """Relatorio de uma aula encerrada como arquivo para download."""
    relatorio = _relatorio_de_aula_encerrada(sessao_id, professor, db)
    conteudo, tipo, nome = exportacao.gerar(relatorio, formato)
    return Response(content=conteudo, media_type=tipo,
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


# ---------------------------------------------------------------------------
# Rotas do modulo de IA (cadastro facial e reconhecimento). Todas exigem X-API-Key.
# ---------------------------------------------------------------------------

@app.get("/ia/turmas/{turma_id}/alunos", response_model=List[AlunoCadastroIA], dependencies=[Depends(exigir_chave_ia)])
def ia_listar_alunos(turma_id: int, db: Session = Depends(get_db)):
    """Lista os alunos da turma e se cada um ja tem cadastro facial (usado pelo script de cadastro)."""
    if not db.query(Turma).filter(Turma.id == turma_id).first():
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    alunos = db.query(Aluno).filter(Aluno.turma_id == turma_id).order_by(Aluno.nome).all()
    return [AlunoCadastroIA(aluno_id=a.id, nome=a.nome, cadastrado=bool(a.embedding)) for a in alunos]


@app.put("/ia/alunos/{aluno_id}/embedding", response_model=AlunoCadastroIA, dependencies=[Depends(exigir_chave_ia)])
def ia_cadastrar_embedding(aluno_id: int, cadastro: CadastroFacialIn, db: Session = Depends(get_db)):
    """
    Cadastro facial: grava somente o vetor de caracteristicas (embedding), nunca a foto.
    LGPD (art. 11): exige o consentimento explicito do aluno.
    """
    if not cadastro.consentimento:
        raise HTTPException(status_code=422, detail="Cadastro facial exige o consentimento do aluno")
    if len(cadastro.embedding) != TAMANHO_EMBEDDING:
        raise HTTPException(status_code=422, detail=f"Embedding deve ter {TAMANHO_EMBEDDING} posições")
    norma = sum(v * v for v in cadastro.embedding) ** 0.5
    if norma == 0:
        raise HTTPException(status_code=422, detail="Embedding inválido")

    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    # Guardado normalizado: a similaridade passa a ser um produto escalar
    aluno.embedding = [v / norma for v in cadastro.embedding]
    aluno.consentimento_biometrico_em = datetime.utcnow()
    db.commit()
    return AlunoCadastroIA(aluno_id=aluno.id, nome=aluno.nome, cadastrado=True)


@app.delete("/ia/alunos/{aluno_id}/embedding", response_model=AlunoCadastroIA, dependencies=[Depends(exigir_chave_ia)])
def ia_remover_embedding(aluno_id: int, db: Session = Depends(get_db)):
    """Exclusao do dado biometrico a pedido do aluno (LGPD, art. 18)."""
    aluno = db.query(Aluno).filter(Aluno.id == aluno_id).first()
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado")
    aluno.embedding = None
    db.commit()
    return AlunoCadastroIA(aluno_id=aluno.id, nome=aluno.nome, cadastrado=False)


@app.get("/ia/turmas/{turma_id}/sessao-ativa", response_model=SessaoAtivaIA, dependencies=[Depends(exigir_chave_ia)])
def ia_sessao_ativa(turma_id: int, db: Session = Depends(get_db)):
    """
    Consultado periodicamente pelo modulo de IA da sala: informa a chamada aberta da turma
    (se houver) e os embeddings dos alunos cadastrados, para o reconhecimento local.
    Sessoes abertas ha mais de DURACAO_MAXIMA_SESSAO sao ignoradas (RN-07).
    """
    if not db.query(Turma).filter(Turma.id == turma_id).first():
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    sessao = (
        db.query(Sessao)
        .filter(
            Sessao.turma_id == turma_id,
            Sessao.status == "aberta",
            Sessao.inicio >= datetime.utcnow() - DURACAO_MAXIMA_SESSAO,
        )
        .order_by(Sessao.inicio.desc())
        .first()
    )
    _registrar_contato_ia("turma", turma_id, sessao)
    return _sessao_ativa_ia(sessao, db)


@app.get("/ia/turmas/{turma_id}/galeria", response_model=SessaoAtivaIA, dependencies=[Depends(exigir_chave_ia)])
def ia_galeria_turma(turma_id: int, db: Session = Depends(get_db)):
    """
    Galeria de vetores da turma sem chamada aberta (sessao_id sempre nulo): usada pelos experimentos E1/E2
    (ia/experimentos.py), que medem o reconhecimento sem registrar presenca.
    """
    turma = db.query(Turma).filter(Turma.id == turma_id).first()
    if not turma:
        raise HTTPException(status_code=404, detail="Turma não encontrada")
    alunos = db.query(Aluno).filter(Aluno.turma_id == turma_id).order_by(Aluno.nome).all()
    return SessaoAtivaIA(
        sessao_id=None,
        turma_nome=turma.nome,
        confianca_minima=CONFIANCA_MINIMA,
        alunos=[AlunoGaleriaIA(aluno_id=a.id, nome=a.nome, embedding=a.embedding) for a in alunos if a.embedding and a.consentimento_biometrico_em],
    )


def _sessao_ativa_ia(sessao: Optional[Sessao], db: Session) -> SessaoAtivaIA:
    """Chamada aberta e a galeria de vetores dos alunos cadastrados da turma dela."""
    if not sessao:
        return SessaoAtivaIA(sessao_id=None, confianca_minima=CONFIANCA_MINIMA, alunos=[])
    alunos = db.query(Aluno).filter(Aluno.turma_id == sessao.turma_id).order_by(Aluno.nome).all()
    # Filtrado em Python: registros antigos guardam "sem cadastro" como JSON 'null', que IS NOT NULL nao exclui.
    # So entra quem tem a autorizacao registrada (RN-12), mesmo que um vetor tenha ficado gravado sem ela
    return SessaoAtivaIA(
        sessao_id=sessao.id,
        turma_nome=sessao.turma.nome,
        confianca_minima=CONFIANCA_MINIMA,
        alunos=[AlunoGaleriaIA(aluno_id=a.id, nome=a.nome, embedding=a.embedding) for a in alunos if a.embedding and a.consentimento_biometrico_em],
    )


@app.get("/ia/salas", response_model=List[SalaOut], dependencies=[Depends(exigir_chave_ia)])
def ia_listar_salas(db: Session = Depends(get_db)):
    """Usado pelo assistente de configuracao do computador da sala."""
    return [_sala_out(s, db) for s in db.query(Sala).order_by(Sala.nome).all()]


@app.get("/ia/salas/{sala_id}/sessao-ativa", response_model=SessaoAtivaIA, dependencies=[Depends(exigir_chave_ia)])
def ia_sessao_ativa_da_sala(sala_id: int, db: Session = Depends(get_db)):
    """Consultado pelo modulo de IA da sala: a chamada aberta nela (de qualquer turma) e a galeria."""
    _sala_existente(sala_id, db)
    sessao = _sessao_aberta_na_sala(sala_id, db)
    _registrar_contato_ia("sala", sala_id, sessao)
    return _sessao_ativa_ia(sessao, db)


# ---------------------------------------------------------------------------
# Situacao da camera da sala: o modulo de IA consulta a chamada ativa periodicamente (a cada 5 s sem
# chamada e a cada 30 s com chamada); o ultimo contato de cada sala/turma fica em memoria. Reiniciar o
# servidor zera esses contatos, que voltam na proxima consulta do modulo.
# ---------------------------------------------------------------------------

CAMERA_SEM_SINAL_APOS = timedelta(seconds=75)   # 2,5 consultas de 30 s sem contato
CAMERA_TOLERANCIA_INICIO = timedelta(seconds=20)  # tempo para o modulo perceber uma chamada recem-aberta
_contatos_ia: Dict[tuple, tuple] = {}  # ("sala"|"turma", id) -> (momento, sessao_id informada ao modulo)


def _registrar_contato_ia(tipo: str, ident: int, sessao: Optional[Sessao]) -> None:
    _contatos_ia[(tipo, ident)] = (datetime.utcnow(), sessao.id if sessao else None)


def _situacao_camera(sessao: Sessao, agora: Optional[datetime] = None) -> CameraSalaOut:
    agora = agora or datetime.utcnow()
    contatos = [c for c in (_contatos_ia.get(("sala", sessao.sala_id)) if sessao.sala_id else None,
                            _contatos_ia.get(("turma", sessao.turma_id))) if c]
    if not sessao.sala_id and not contatos:
        return CameraSalaOut(situacao="sem_camera")  # chamada sem sala e nenhum modulo acompanhando a turma
    sala = sessao.sala.nome if sessao.sala else "da sala"
    ultimo = max(contatos, key=lambda c: c[0]) if contatos else None
    visto = (agora - ultimo[0]).total_seconds() if ultimo else None
    if ultimo and agora - ultimo[0] <= CAMERA_SEM_SINAL_APOS:
        if any(c[1] == sessao.id for c in contatos):
            return CameraSalaOut(situacao="conectada", visto_ha_segundos=visto)
        return CameraSalaOut(situacao="aguardando", visto_ha_segundos=visto,
                             mensagem="A câmera está iniciando o reconhecimento desta chamada…")
    if agora - sessao.inicio <= CAMERA_TOLERANCIA_INICIO:
        return CameraSalaOut(situacao="aguardando", visto_ha_segundos=visto,
                             mensagem="Conectando à câmera da sala…")
    return CameraSalaOut(
        situacao="sem_sinal", visto_ha_segundos=visto,
        mensagem=(f"A câmera {'da ' + sala if sessao.sala else sala} não está respondendo. Confira se o computador "
                  "da sala está ligado e com o reconhecimento ligado no painel. Enquanto isso, ninguém é marcado "
                  "automaticamente; use o ajuste manual se precisar."))


@app.get("/sessoes/{sessao_id}/camera", response_model=CameraSalaOut)
def camera_da_sessao(sessao_id: int, professor: Professor = Depends(obter_professor_atual),
                     db: Session = Depends(get_db)):
    """O app consulta durante a chamada para avisar o professor se a camera da sala parou de responder."""
    sessao = db.query(Sessao).filter(Sessao.id == sessao_id, Sessao.professor_id == professor.id).first()
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if sessao.status != "aberta":
        return CameraSalaOut(situacao="sem_camera")
    return _situacao_camera(sessao)


@app.websocket("/ws/sessoes/{sessao_id}")
async def websocket_sessao(websocket: WebSocket, sessao_id: int, token: Optional[str] = None):
    """
    Eventos ao vivo da chamada. Exige o JWT do professor dono da sessao em ?token= (o navegador nao envia
    cabecalhos no WebSocket); sem ele a conexao e recusada (codigo 4401). A conferencia usa uma sessao de
    banco curta, para nao prender uma conexao do pool enquanto o WebSocket fica aberto.
    """
    with SessionLocal() as db:
        professor = _professor_do_token(token, db)
        dono = professor is not None and db.query(Sessao).filter(
            Sessao.id == sessao_id, Sessao.professor_id == professor.id).first() is not None
    if not dono:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    CONEXOES_WEBSOCKET.setdefault(sessao_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in CONEXOES_WEBSOCKET.get(sessao_id, []):
            CONEXOES_WEBSOCKET[sessao_id].remove(websocket)
