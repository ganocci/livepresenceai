from sqlalchemy import (
    Column, Integer, String, ForeignKey, TIMESTAMP, Numeric, Interval, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base


class Professor(Base):
    __tablename__ = "professor"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    senha_hash = Column(String(255), nullable=False)
    criado_em = Column(TIMESTAMP, server_default=func.now())

    turmas = relationship("Turma", back_populates="professor")


class Turma(Base):
    __tablename__ = "turma"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    professor_id = Column(Integer, ForeignKey("professor.id"), nullable=False)
    criado_em = Column(TIMESTAMP, server_default=func.now())

    professor = relationship("Professor", back_populates="turmas")
    alunos = relationship("Aluno", back_populates="turma")
    sessoes = relationship("Sessao", back_populates="turma")


class Aluno(Base):
    __tablename__ = "aluno"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(150), nullable=False)
    turma_id = Column(Integer, ForeignKey("turma.id"), nullable=False)
    embedding = Column(JSON, nullable=True)
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

    turma = relationship("Turma", back_populates="sessoes")
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
