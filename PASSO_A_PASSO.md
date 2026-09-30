# LivePresenceAI — Passo a passo de execução e roteiro da demonstração

Versão: Protótipo Funcional Integrado v1.1 (30/09/2026).
Para detalhes técnicos (API, regras de negócio, banco), ver [docs/DOCUMENTACAO_TECNICA.md](docs/DOCUMENTACAO_TECNICA.md).

Os comandos abaixo são para **PowerShell no Windows**.

---

## 1. Pré-requisitos

| Programa | Observação |
|---|---|
| Python 3.14 | Projeto testado em 3.14.7 |
| PostgreSQL + pgAdmin | Neste computador roda na porta **5433** (o padrão costuma ser 5432) |
| Flutter SDK | Em pasta sem acentos/espaços, ex.: `C:\src\flutter`, com `C:\src\flutter\bin` no PATH |
| Google Chrome | Para rodar o app Flutter Web |

Conferir:

```powershell
python --version
flutter doctor
```

No `flutter doctor`, basta aparecer `[✓] Flutter` e `[✓] Chrome`. Avisos de Android e Visual Studio podem ser ignorados.

---

## 2. Primeira instalação (só uma vez por computador)

### 2.1 Banco de dados

No pgAdmin (Query Tool conectado como `postgres`):

```sql
CREATE USER livepresenceai WITH PASSWORD 'livepresenceai';
CREATE DATABASE livepresenceai OWNER livepresenceai;
```

Se o PostgreSQL **não** estiver na porta 5433, definir a conexão antes de subir o backend (em todo terminal do backend):

```powershell
$env:DATABASE_URL = "postgresql+psycopg2://livepresenceai:livepresenceai@localhost:5432/livepresenceai"
```

### 2.2 Backend

```powershell
cd E:\repositories\livepresenceai_projeto\backend
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python seed_dados_demo.py
```

O seed cria as tabelas, o professor de teste, a **Turma A - Manhã** e 6 alunos. Pode ser rodado mais de uma vez sem duplicar nada.

> **Banco criado antes de 30/09/2026?** Rodar uma vez o script
> `database\migracao_001_registro_unico_e_deteccoes.sql` no pgAdmin (Query Tool no banco `livepresenceai`).
> Sem isso o backend dá erro ao registrar presença. Rodar de novo não tem efeito.

### 2.3 App

```powershell
cd E:\repositories\livepresenceai_projeto\app
flutter pub get
```

---

## 3. Executar (todo dia)

São **3 terminais**. Nos terminais do backend, sempre ativar o ambiente virtual primeiro.

**Terminal 1 — backend**

```powershell
cd E:\repositories\livepresenceai_projeto\backend
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

Esperado: `Uvicorn running on http://127.0.0.1:8000`. Conferir em http://127.0.0.1:8000/docs.

> A cada login aparece no terminal `(trapped) error reading bcrypt version` seguido de um *Traceback*.
> **É só um aviso**, conhecido e inofensivo (combinação passlib + bcrypt 4.3). O login funciona normalmente.

**Terminal 2 — app**

```powershell
cd E:\repositories\livepresenceai_projeto\app
flutter run -d chrome
```

Login de teste: `professor@livepresenceai.com` / `senha123` (já vem preenchido).

**Terminal 3 — simulador** (deixar aberto, com o venv ativo, e rodar só na hora da demo)

```powershell
cd E:\repositories\livepresenceai_projeto\backend
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

---

## 4. Roteiro da demonstração (~5 minutos)

### Antes de começar
- [ ] Backend e app abertos; login feito e tela **"Selecione a turma"** aberta.
- [ ] Terminal 3 pronto no diretório `backend`, com o venv ativo.
- [ ] **Nenhuma chamada aberta de ensaio anterior** (ver "Cuidados" abaixo).
- [ ] Opcional: aba http://127.0.0.1:8000/docs aberta para mostrar a API.

### Passo a passo

| # | Ação | O que falar / mostrar |
|---|---|---|
| 1 | Mostrar o Swagger (`/docs`) | Backend FastAPI com API REST documentada; dados reais no PostgreSQL. |
| 2 | No app, tocar em **Turma A - Manhã** | A sessão é criada no banco (**Sessão #N** no topo); nuvem verde = tempo real conectado. |
| 3 | **Logo em seguida**, no terminal 3: `python simulador_eventos.py N --demo` (trocar N pelo número da sessão) | O simulador ocupa o lugar da câmera/IA e usa **o mesmo contrato** que o módulo de IA real vai usar, autenticado com a chave do módulo de IA. |
| 4 | Acompanhar a tela por **cerca de 3 minutos** | Alunos chegam e aparecem **"Na sala"** sem recarregar. Aos ~40 s, Carla e Diego saem: após ~1 min viram **"Fora da sala há…"** e o percentual fica vermelho. Aos ~2 min a Carla volta. Fábio nunca aparece. |
| 5 | Tocar em **Encerrar chamada** | O servidor calcula permanência e percentual e aplica a regra dos 40%. |
| 6 | Mostrar o relatório | ✅ presença (Ana, Bruno, Elisa, Carla) · ⚠️ falta por ficar abaixo de 40% (Diego) · ❌ falta, não detectado (Fábio). |
| 7 | Opcional: mostrar os dados no pgAdmin | Consultas da seção 6. |
| 8 | Parar o simulador (Ctrl+C no terminal 3) | — |

**Frase para posicionar o protótipo:** "Esta versão implementa o fluxo completo de presença: autenticação, turmas, sessão, acompanhamento em tempo real, cálculo de permanência, regra de frequência mínima e relatório. A origem dos eventos de reconhecimento ainda é simulada, mas usa o mesmo contrato que será ocupado pelo pipeline local de OpenCV, YOLOv8, Liveness Detection, InsightFace e DeepSORT."

### Cuidados

- **Encerrar a chamada ao fim de cada ensaio.** Se uma chamada ficar aberta, abrir a mesma turma em menos de 4 h **retoma a sessão do ensaio** (aparece o aviso "Chamada em andamento retomada"), com os tempos antigos. Se isso acontecer na hora, encerrar essa chamada e abrir a turma de novo.
- **Tempo no `--demo`:** rodar o simulador **logo depois** de abrir a turma e encerrar com **cerca de 3 minutos**. O percentual é calculado sobre a aula inteira, inclusive os segundos entre abrir a turma e iniciar o simulador; encerrando cedo (antes de ~2 min 30 s) a Carla, que saiu e voltou, pode ficar abaixo de 40% e sair como falta.
- **Ordem:** primeiro abrir a turma no app (para saber o N), depois rodar o simulador.
- **No início os percentuais aparecem baixos e em vermelho** (a aula acabou de começar); eles sobem com o tempo.
- Se a nuvem ficar laranja com a faixa "reconectando…", o app reconecta sozinho quando o backend voltar.
- O botão **"Simular reconhecimento"** do app marca manualmente o próximo aluno ainda não detectado (alternativa se o simulador falhar).

---

## 5. Opções do simulador

```powershell
python simulador_eventos.py N --demo                   # roteiro da apresentação
python simulador_eventos.py N                          # alunos 1 a 5 chegam e ficam
python simulador_eventos.py N --alunos 1,2,3           # só esses alunos aparecem
python simulador_eventos.py N --sai 4:40               # aluno 4 sai aos 40 s e não volta
python simulador_eventos.py N --pausa 3:40-120         # aluno 3 fica fora de 40 s a 120 s
python simulador_eventos.py N --intervalo 2 --chegada-max 10 --duracao 60
```

Uma saída só é descontada se passar de **60 s** sem detecção. Para ensaios mais rápidos, subir o backend com um limite menor (só para teste):

```powershell
$env:LIMITE_AUSENCIA_SEGUNDOS = "10"
uvicorn main:app --reload
```

---

## 6. Conferir os dados no banco (pgAdmin)

```sql
SELECT id, status, inicio, fim
FROM sessao
ORDER BY id DESC
LIMIT 5;

SELECT r.sessao_id, a.nome, r.entrada, r.ultima_visualizacao,
       r.tempo_total_presente, r.percentual_presenca,
       r.confianca_media, r.numero_deteccoes
FROM registro_presenca r
JOIN aluno a ON a.id = r.aluno_id
ORDER BY r.id DESC
LIMIT 20;
```

Os horários ficam gravados em **UTC** (3 h a mais que o horário de Brasília); o app converte para o horário local.

---

## 7. Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| App: "Não foi possível conectar ao servidor" | Backend parado | Subir o terminal 1 |
| Backend não sobe: erro de conexão com o banco | PostgreSQL parado ou porta diferente | Iniciar o serviço; ajustar `DATABASE_URL` (seção 2.1) |
| Erro 500 / "column numero_deteccoes does not exist" | Banco antigo sem a migração | Rodar `database\migracao_001_...sql` (seção 2.2) |
| Simulador: `[erro] ... 401` | Chave do módulo de IA diferente entre backend e simulador | Não definir `CHAVE_MODULO_IA`, ou definir o mesmo valor nos dois terminais |
| Simulador: `[erro] ... 404 Sessao nao encontrada ou ja encerrada` | Número de sessão errado ou chamada já encerrada | Conferir o N no topo da tela do app |
| Simulador: `[erro] ... 404 Aluno nao pertence a turma` | `--alunos` com IDs de outra turma | Usar os IDs da turma (seed: 1 a 6) |
| `Activate.ps1` bloqueado | Política de execução do PowerShell | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| Erro com bcrypt 5.x no login | Versão incompatível com passlib | `pip install bcrypt==4.3.0` |
| App em outro dispositivo da rede não conecta | App aponta para 127.0.0.1 e o backend só aceita conexões locais | Trocar `apiHost` em `app\lib\config.dart` pelo IP do computador do backend e subir com `uvicorn main:app --reload --host 0.0.0.0` (liberar a porta 8000 no firewall do Windows) |
