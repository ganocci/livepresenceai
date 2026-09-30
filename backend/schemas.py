from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel, field_serializer


class TurmaOut(BaseModel):
    id: int
    nome: str

    class Config:
        from_attributes = True


class AlunoOut(BaseModel):
    id: int
    nome: str
    turma_id: int

    class Config:
        from_attributes = True


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


class SessaoOut(BaseModel):
    id: int
    turma_id: int
    status: str
    inicio: datetime
    fim: Optional[datetime] = None
    # retomada: sessao aberta recente reaproveitada em vez de criar outra (RN-07)
    retomada: bool = False
    # alunos ja detectados na sessao (vazio em sessao nova)
    registros: List[RegistroPresencaOut] = []
    # Parametros das regras (RN-02/RN-03) para o app exibir o estado ao vivo sem duplicar valores
    frequencia_minima: Optional[float] = None
    limite_ausencia_segundos: Optional[float] = None

    class Config:
        from_attributes = True


class EventoReconhecimento(BaseModel):
    aluno_id: int
    confianca: float


class SituacaoAlunoOut(BaseModel):
    """Linha do relatorio final: todo aluno da turma, detectado ou nao (RN-03)."""
    aluno_id: int
    nome: str
    detectado: bool
    entrada: Optional[datetime] = None
    tempo_total_presente: float = 0.0  # segundos
    percentual_presenca: float = 0.0
    situacao: str  # 'presenca' | 'falta'


class RelatorioSessao(BaseModel):
    sessao_id: int
    status: str
    frequencia_minima: float
    total_presencas: int
    total_faltas: int
    alunos: List[SituacaoAlunoOut]
    registros: List[RegistroPresencaOut]
