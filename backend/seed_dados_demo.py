from datetime import datetime

from passlib.context import CryptContext

import migracoes
from database import Base, engine, SessionLocal
from models import Professor, Turma, Aluno

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

migracoes.preparar_banco(engine, Base)
db = SessionLocal()

professor = db.query(Professor).filter(Professor.email == "professor@livepresenceai.com").first()
if not professor:
    professor = Professor(
        nome="Professor Teste",
        email="professor@livepresenceai.com",
        senha_hash=pwd_context.hash("senha123"),
    )
    db.add(professor)
    db.commit()
    db.refresh(professor)
    print(f"Professor criado: {professor.email} (senha: senha123)")
else:
    print("Professor de teste ja existe.")

# Aceita tambem o nome antigo sem acento, para nao duplicar a turma em bancos criados antes
turma = (
    db.query(Turma)
    .filter(Turma.nome.in_(["Turma A - Manhã", "Turma A - Manha"]), Turma.professor_id == professor.id)
    .first()
)
if not turma:
    turma = Turma(nome="Turma A - Manhã", professor_id=professor.id)
    db.add(turma)
    db.commit()
    db.refresh(turma)
    print(f"Turma criada: {turma.nome} (id={turma.id})")

# O ultimo aluno fica de fora do simulador --demo, para mostrar o caso "nunca detectado".
# RAs ficticios (prefixo DEMO); alunos ja existentes nao sao alterados.
nomes_alunos = ["Ana Souza", "Bruno Lima", "Carla Mendes", "Diego Alves", "Elisa Ramos", "Fábio Costa"]
alunos_existentes = {a.nome for a in db.query(Aluno).filter(Aluno.turma_id == turma.id).all()}

for numero, nome in enumerate(nomes_alunos, 1):
    if nome not in alunos_existentes:
        db.add(Aluno(nome=nome, ra=f"DEMO{numero:04d}", turma_id=turma.id, embedding=None,
                     criado_em=datetime.utcnow()))

db.commit()
print(f"{len(nomes_alunos)} alunos de teste garantidos na turma '{turma.nome}'.")
db.close()
