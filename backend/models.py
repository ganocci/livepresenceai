from sqlalchemy import (
    Boolean, CheckConstraint, Column, Integer, String, ForeignKey, TIMESTAMP, Numeric, Interval, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Professor(Base):
    """Usuario do app: professor ou administrador (cadastra professores e salas)."""
    __tablename__ = "professor"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    senha_hash = Column(String(255), nullable=False)
    perfil = Column(String(20), nullable=False, default="professor", server_default="professor")
    ativo = Column(Boolean, nullable=False, default=True, server_default="true")
    criado_em = Column(TIMESTAMP, server_default=func.now())

    turmas = relationship("Turma", back_populates="professor")


class Sala(Base):
    """Sala de aula com um computador e uma camera; o modulo de IA da sala atende a chamada aberta nela."""
    __tablename__ = "sala"
    __table_args__ = (UniqueConstraint("nome", name="uq_sala_nome"),)

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(60), nullable=False)
    criado_em = Column(TIMESTAMP)


class Turma(Base):
    __tablename__ = "turma"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    professor_id = Column(Integer, ForeignKey("professor.id"), nullable=False)
    sala_id = Column(Integer, ForeignKey("sala.id"), nullable=True)  # sala padrao das chamadas
    criado_em = Column(TIMESTAMP, server_default=func.now())

    professor = relationship("Professor", back_populates="turmas")
    sala = relationship("Sala")
    alunos = relationship("Aluno", back_populates="turma")
    sessoes = relationship("Sessao", back_populates="turma")


class Aluno(Base):
    __tablename__ = "aluno"
    # Cada aluno pertence a um curso e a uma turma: o RA e unico no sistema
    __table_args__ = (UniqueConstraint("ra", name="uq_aluno_ra"),)

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(150), nullable=False)
    ra = Column(String(20), nullable=True)  # alunos anteriores a migracao 002 podem nao ter RA
    turma_id = Column(Integer, ForeignKey("turma.id"), nullable=False)
    # none_as_null: sem cadastro facial grava NULL do SQL (e nao o valor JSON 'null')
    embedding = Column(JSON(none_as_null=True), nullable=True)
    # LGPD: quando o aluno consentiu com o cadastro facial (UTC); NULL sem cadastro
    consentimento_biometrico_em = Column(TIMESTAMP, nullable=True)
    # Alunos criados pela API gravam em UTC (como as sessoes), para o historico saber
    # quem ja era da turma em cada aula
    criado_em = Column(TIMESTAMP, server_default=func.now())

    turma = relationship("Turma", back_populates="alunos")


class Sessao(Base):
    __tablename__ = "sessao"

    id = Column(Integer, primary_key=True, index=True)
    turma_id = Column(Integer, ForeignKey("turma.id"), nullable=False)
    professor_id = Column(Integer, ForeignKey("professor.id"), nullable=False)
    inicio = Column(TIMESTAMP, server_default=func.now())
    fim = Column(TIMESTAMP, nullable=True)
    status = Column(String(20), nullable=False, default="aberta")
    sala_id = Column(Integer, ForeignKey("sala.id"), nullable=True)  # sala onde a chamada acontece

    turma = relationship("Turma", back_populates="sessoes")
    sala = relationship("Sala")
    registros = relationship("RegistroPresenca", back_populates="sessao")


class RegistroPresenca(Base):
    __tablename__ = "registro_presenca"
    # Um unico registro por aluno em cada sessao
    __table_args__ = (UniqueConstraint("sessao_id", "aluno_id", name="uq_registro_sessao_aluno"),)

    id = Column(Integer, primary_key=True, index=True)
    sessao_id = Column(Integer, ForeignKey("sessao.id"), nullable=False)
    aluno_id = Column(Integer, ForeignKey("aluno.id"), nullable=False)
    entrada = Column(TIMESTAMP, nullable=False)
    ultima_visualizacao = Column(TIMESTAMP, nullable=False)
    tempo_total_presente = Column(Interval, nullable=True)
    confianca_media = Column(Numeric(5, 2), nullable=True)
    numero_deteccoes = Column(Integer, nullable=False, default=1, server_default="1")
    percentual_presenca = Column(Numeric(5, 2), nullable=True)

    sessao = relationship("Sessao", back_populates="registros")
    aluno = relationship("Aluno")


class AjustePresenca(Base):
    """
    RN-15: ajuste manual da chamada. Prevalece sobre a situacao calculada (RN-03), que continua em
    registro_presenca para auditoria. Um ajuste por aluno em cada aula.
    """
    __tablename__ = "ajuste_presenca"
    __table_args__ = (
        UniqueConstraint("sessao_id", "aluno_id", name="uq_ajuste_sessao_aluno"),
        CheckConstraint("situacao IN ('presenca', 'falta')", name="ck_ajuste_situacao"),
    )

    id = Column(Integer, primary_key=True, index=True)
    sessao_id = Column(Integer, ForeignKey("sessao.id"), nullable=False)
    aluno_id = Column(Integer, ForeignKey("aluno.id"), nullable=False)
    situacao = Column(String(10), nullable=False)  # 'presenca' | 'falta'
    motivo = Column(String(200), nullable=False)
    professor_id = Column(Integer, ForeignKey("professor.id"), nullable=False)
    criado_em = Column(TIMESTAMP, nullable=False)  # UTC

    professor = relationship("Professor")
