from datetime import datetime, timedelta
from typing import Optional, List
import re

from pydantic import BaseModel, field_serializer, field_validator


class TurmaOut(BaseModel):
    id: int
    nome: str
    total_alunos: int = 0
    total_aulas: int = 0  # sessoes encerradas
    sala_id: Optional[int] = None  # sala padrao das chamadas
    sala_nome: Optional[str] = None

    class Config:
        from_attributes = True


class TurmaIn(BaseModel):
    nome: str
    sala_id: Optional[int] = None

    @field_validator("nome")
    @classmethod
    def _nome(cls, valor: str) -> str:
        valor = " ".join(valor.split())
        if not 1 <= len(valor) <= 100:
            raise ValueError("O nome da turma deve ter de 1 a 100 caracteres")
        return valor


class AlunoOut(BaseModel):
    id: int
    nome: str
    ra: Optional[str] = None
    turma_id: int
    cadastro_facial: bool = False
    # Autorizacao do uso de biometria, assinada pelo aluno na matricula (LGPD, art. 11)
    autorizacao_biometrica: bool = False
    autorizacao_biometrica_em: Optional[datetime] = None

    class Config:
        from_attributes = True


RA_VALIDO = re.compile(r"^[A-Z0-9-]{1,20}$")


class AlunoIn(BaseModel):
    nome: str
    ra: str
    # True: o aluno autorizou o reconhecimento facial na matricula; False: nao autorizou ou revogou
    # (o cadastro facial e apagado); ausente: mantem o que estava
    autorizou_biometria: Optional[bool] = None

    @field_validator("nome")
    @classmethod
    def _nome(cls, valor: str) -> str:
        valor = " ".join(valor.split())
        if not 1 <= len(valor) <= 150:
            raise ValueError("Nome do aluno deve ter de 1 a 150 caracteres")
        return valor

    @field_validator("ra")
    @classmethod
    def _ra(cls, valor: str) -> str:
        # RA guardado em maiusculas e sem espacos (ex.: N0532D0, G801AA-9)
        valor = valor.strip().upper()
        if not RA_VALIDO.match(valor):
            raise ValueError("O RA deve ter de 1 a 20 caracteres: letras, números ou hífen")
        return valor


class RegistroPresencaOut(BaseModel):
    aluno_id: int
    entrada: datetime
    ultima_visualizacao: datetime
    tempo_total_presente: Optional[timedelta] = None
    percentual_presenca: Optional[float] = None

    class Config:
        from_attributes = True

    @field_serializer("tempo_total_presente")
    def _tempo_em_segundos(self, valor: Optional[timedelta]) -> float:
        """Enviado ao app em segundos (mais simples que o formato ISO 8601 de duracao)."""
        return valor.total_seconds() if valor else 0.0


class AjusteIn(BaseModel):
    """RN-15: ajuste manual da chamada de um aluno."""
    situacao: str
    motivo: str

    @field_validator("situacao")
    @classmethod
    def _situacao(cls, valor: str) -> str:
        if valor not in ("presenca", "falta"):
            raise ValueError("A situação deve ser presenca ou falta")
        return valor

    @field_validator("motivo")
    @classmethod
    def _motivo(cls, valor: str) -> str:
        valor = " ".join(valor.split())
        if not 3 <= len(valor) <= 200:
            raise ValueError("Informe o motivo do ajuste (de 3 a 200 caracteres)")
        return valor


class AjusteOut(BaseModel):
    aluno_id: int
    situacao: str
    motivo: str
    professor_nome: Optional[str] = None
    criado_em: datetime


class SessaoOut(BaseModel):
    id: int
    turma_id: int
    status: str
    sala_id: Optional[int] = None
    sala_nome: Optional[str] = None
    inicio: datetime
    fim: Optional[datetime] = None
    # retomada: sessao aberta recente reaproveitada em vez de criar outra (RN-07)
    retomada: bool = False
    # alunos ja detectados na sessao (vazio em sessao nova)
    registros: List[RegistroPresencaOut] = []
    # Parametros das regras (RN-02/RN-03) para o app exibir o estado ao vivo sem duplicar valores
    frequencia_minima: Optional[float] = None
    limite_ausencia_segundos: Optional[float] = None
    # Ajustes manuais ja feitos na chamada (RN-15)
    ajustes: List[AjusteOut] = []

    class Config:
        from_attributes = True


class EventoReconhecimento(BaseModel):
    aluno_id: int
    confianca: float


class SituacaoAlunoOut(BaseModel):
    """Linha do relatorio final: todo aluno da turma, detectado ou nao (RN-03)."""
    aluno_id: int
    nome: str
    ra: Optional[str] = None
    detectado: bool
    entrada: Optional[datetime] = None
    tempo_total_presente: float = 0.0  # segundos
    percentual_presenca: float = 0.0
    situacao: str  # 'presenca' | 'falta' (final: com o ajuste manual, se houver)
    situacao_calculada: Optional[str] = None  # pela regra dos 40% (RN-03), antes do ajuste
    ajuste_manual: bool = False
    motivo_ajuste: Optional[str] = None


class RelatorioSessao(BaseModel):
    sessao_id: int
    status: str
    turma_id: Optional[int] = None
    turma_nome: Optional[str] = None
    professor_nome: Optional[str] = None
    sala_nome: Optional[str] = None
    inicio: Optional[datetime] = None
    fim: Optional[datetime] = None
    frequencia_minima: float
    total_presencas: int
    total_faltas: int
    alunos: List[SituacaoAlunoOut]
    registros: List[RegistroPresencaOut]


class SessaoResumoOut(BaseModel):
    """Linha do historico de aulas de uma turma."""
    id: int
    status: str
    inicio: datetime
    fim: Optional[datetime] = None
    duracao_segundos: Optional[float] = None
    total_presencas: int = 0
    total_faltas: int = 0


# --- Modulo de IA ---

class AlunoCadastroIA(BaseModel):
    aluno_id: int
    nome: str
    cadastrado: bool


class CadastroFacialIn(BaseModel):
    embedding: List[float]
    # LGPD: o cadastro so e aceito com consentimento explicito do aluno
    consentimento: bool = False


class AlunoGaleriaIA(BaseModel):
    aluno_id: int
    nome: str
    embedding: List[float]


class SessaoAtivaIA(BaseModel):
    sessao_id: Optional[int] = None
    turma_nome: Optional[str] = None
    confianca_minima: float
    alunos: List[AlunoGaleriaIA] = []


# --- Usuarios, primeiro acesso e salas ---

PERFIS = ("administrador", "professor")


def _validar_senha(valor: str) -> str:
    if len(valor) < 8:
        raise ValueError("A senha deve ter pelo menos 8 caracteres")
    return valor


def _validar_email(valor: str) -> str:
    valor = valor.strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", valor):
        raise ValueError("E-mail inválido")
    return valor


class ProfessorOut(BaseModel):
    id: int
    nome: str
    email: str
    perfil: str
    ativo: bool

    class Config:
        from_attributes = True


class PrimeiroAcessoIn(BaseModel):
    """Conta do primeiro administrador, criada na configuracao inicial do sistema."""
    nome: str
    email: str
    senha: str

    @field_validator("nome")
    @classmethod
    def _nome(cls, valor: str) -> str:
        valor = " ".join(valor.split())
        if not 1 <= len(valor) <= 150:
            raise ValueError("Nome deve ter de 1 a 150 caracteres")
        return valor

    @field_validator("email")
    @classmethod
    def _email(cls, valor: str) -> str:
        return _validar_email(valor)

    @field_validator("senha")
    @classmethod
    def _senha(cls, valor: str) -> str:
        return _validar_senha(valor)


class ProfessorIn(BaseModel):
    nome: str
    email: str
    perfil: str = "professor"
    ativo: bool = True
    senha: Optional[str] = None  # obrigatoria ao criar; ao editar, so se for trocar

    @field_validator("nome")
    @classmethod
    def _nome(cls, valor: str) -> str:
        valor = " ".join(valor.split())
        if not 1 <= len(valor) <= 150:
            raise ValueError("Nome deve ter de 1 a 150 caracteres")
        return valor

    @field_validator("email")
    @classmethod
    def _email(cls, valor: str) -> str:
        return _validar_email(valor)

    @field_validator("perfil")
    @classmethod
    def _perfil(cls, valor: str) -> str:
        if valor not in PERFIS:
            raise ValueError("O perfil deve ser administrador ou professor")
        return valor

    @field_validator("senha")
    @classmethod
    def _senha(cls, valor: Optional[str]) -> Optional[str]:
        return None if valor is None else _validar_senha(valor)


class TrocaSenhaIn(BaseModel):
    senha_atual: str
    nova_senha: str

    @field_validator("nova_senha")
    @classmethod
    def _nova(cls, valor: str) -> str:
        return _validar_senha(valor)


class SalaOut(BaseModel):
    id: int
    nome: str
    em_uso: bool = False  # ha chamada aberta nesta sala agora

    class Config:
        from_attributes = True


class SalaIn(BaseModel):
    nome: str

    @field_validator("nome")
    @classmethod
    def _nome(cls, valor: str) -> str:
        valor = " ".join(valor.split())
        if not 1 <= len(valor) <= 60:
            raise ValueError("Nome da sala deve ter de 1 a 60 caracteres")
        return valor
