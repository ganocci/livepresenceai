# LivePresenceAI — Passo a passo de execução e roteiro da demonstração

Versão: versão final em desenvolvimento (04/10/2026).
Para detalhes técnicos (API, regras de negócio, banco), ver [docs/DOCUMENTACAO_TECNICA.md](docs/DOCUMENTACAO_TECNICA.md).

Os comandos abaixo são para **PowerShell no Windows**.

---

## 0. Instalação para o usuário final (recomendado)

Para uma escola ou faculdade, sem terminal no dia a dia:

1. Dar dois cliques em **Instalar-LivePresenceAI.exe** (gerado pela equipe com
   `powershell -ExecutionPolicy Bypass -File instalador\empacotar.ps1`), clicar em **Sim** no aviso do
   Windows, escolher **Este computador faz tudo** e clicar em **Instalar** (10 a 30 minutos, com internet).
   Em computadores separados: **Só o servidor** num e **Só a câmera de uma sala** nos outros (este pede a
   chave do módulo de IA, copiada no painel do servidor em **Celulares e outras salas**).
   Alternativa pela linha de comando: `powershell -ExecutionPolicy Bypass -File instalar.ps1` como
   administrador (`-Papel Servidor`/`-Papel Sala`; `-Simular` mostra o que seria feito).
2. Clicar em **Abrir o LivePresenceAI** (ou no atalho da área de trabalho) e em **Ligar tudo**.
3. Clicar em **Abrir o app** e criar a **conta do administrador** (só na primeira vez).
4. No app: **Minha conta (avatar) → Administração** → cadastrar professores e salas.
5. No painel, em **Esta sala**: escolher a sala e a câmera (**Testar imagem** para conferir) e ligar o
   reconhecimento. Marcar **Iniciar com o Windows** para não precisar abrir o painel todo dia.
6. Celulares Android: baixar o app em `https://<IP do servidor>:8443/android` (endereço mostrado no painel)
   e permitir a instalação. Com o celular no mesmo Wi-Fi, o app **encontra o servidor sozinho** — não é
   preciso digitar o IP nem instalar certificado. Pelo navegador (outros aparelhos), instalar uma vez o
   `ca.crt` (painel → **Celulares e outras salas** → Abrir a pasta do certificado).

Para gerar o APK de novo (equipe): `powershell -ExecutionPolicy Bypass -File app\gerar_apk.ps1`
(precisa do Android SDK em `C:\Android\Sdk`; ver documentação técnica, seção 11).

As seções a seguir descrevem a execução em **modo de desenvolvimento** (três terminais), usada pela equipe.

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

> **Banco criado antes?** Não é preciso fazer nada: ao iniciar, o backend aplica sozinho as migrações
> pendentes (`database\migracao_*.sql`) e mostra no terminal quais aplicou. Os alunos antigos ficam sem RA:
> preencher pela tela **Alunos** do app.

### 2.3 App

```powershell
cd E:\repositories\livepresenceai_projeto\app
flutter pub get
```

### 2.4 Módulo de IA (reconhecimento facial)

Ambiente separado do backend:

```powershell
cd E:\repositories\livepresenceai_projeto\ia
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Na primeira execução são baixados os modelos: InsightFace `buffalo_l` (~280 MB) e prova de vida
(1,5 MB) para `C:\Users\<usuário>\.insightface`, e YOLOv8 `yolov8n.pt` (6 MB) para a pasta `ia`.
Precisa de internet só nessa vez. A instalação inclui o PyTorch e demora alguns minutos.

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

Depois do login, a tela **Minhas turmas** mostra um cartão por turma com três botões:
**Chamada** (chamada ao vivo), **Alunos** (incluir, editar e excluir alunos com nome e RA) e
**Histórico** (aulas passadas; tocar numa aula abre o relatório). No relatório, o botão de download
(canto superior direito) exporta em **PDF**, **Excel** ou **CSV**: no navegador o arquivo é baixado; no
celular abre a opção de salvar ou compartilhar.

**Terminal 3 — origem dos reconhecimentos**: o **módulo de IA com a câmera** (seção 8) **ou** o simulador.

Para o simulador (deixar aberto, com o venv ativo, e rodar só na hora da demo):

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
| Módulo de IA: "Nao foi possivel abrir a camera 0" | Webcam em uso por outro programa ou índice diferente | Fechar Teams/Zoom/câmera do Windows; tentar `--camera 1` |
| Módulo de IA parado em "aguardando o professor" | Chamada aberta em outra turma ou backend com outra chave | Conferir `--turma`; não definir `CHAVE_MODULO_IA`, ou usar o mesmo valor nos dois terminais |
| Aluno aparece como "desconhecido" na janela | Sem cadastro facial, luz ruim, rosto de lado ou muito longe | Cadastrar (seção 8.1); melhorar a iluminação; olhar para a câmera |

---

## 8. Reconhecimento facial com a câmera

Terminal com o ambiente do módulo de IA ativo:

```powershell
cd E:\repositories\livepresenceai_projeto\ia
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 8.1 Cadastro facial (uma vez por aluno, com o backend ligado)

**Pelo app (forma normal):** em **Alunos**, editar o aluno e ligar **"Autorizou o reconhecimento facial"**
(só para quem assinou a autorização na matrícula). Depois tocar no ícone de rosto do aluno → enquadrar o
rosto na moldura → **Capturar**. O app conta 3 s, tira 5 fotos e mostra "Rosto cadastrado" ou o que
corrigir (aproximar, iluminar, deixar só o aluno). As fotos não ficam no celular nem no servidor.
No navegador do computador a câmera funciona com `flutter run -d chrome` (endereço `localhost`); num
celular, use o app instalado.

**Pelo script (laboratório e experimentos)**, no terminal do módulo de IA:

```powershell
python cadastro_facial.py --turma 1      # lista os alunos (ID, nome, se já tem cadastro)
python cadastro_facial.py --aluno 1      # cadastra a Ana Souza (ID 1) pela webcam
```

O script mostra o termo de consentimento e pergunta se o aluno concorda. Depois abre a janela da câmera:
o aluno olha para a câmera, **sozinho na imagem**, até completar 10 amostras (ESC cancela). Só um vetor
numérico é gravado no banco; a foto não é salva.

Outras opções: `--camera 1` (outra câmera), `--imagem foto.jpg` (cadastro por foto),
`--remover 1` (exclui o cadastro facial do aluno).

### 8.2 Chamada com reconhecimento real

1. Backend e app ligados (terminais 1 e 2).
2. Iniciar o módulo da sala **antes ou depois** de abrir a chamada (ele espera sozinho):
   ```powershell
   python modulo_reconhecimento.py --turma 1
   ```
3. No app, abrir a **Turma A - Manhã**. Em até 5 s o terminal mostra `Chamada aberta: sessao #N`.
4. Quem estiver cadastrado e aparecer na câmera é marcado no app como **Na sala**. Na janela:
   - rosto **verde** com nome e similaridade = reconhecido; **laranja** = não reconhecido;
     **vermelho** = recusado na prova de vida (foto ou tela);
   - pessoa com contorno **azul** e `#N Nome` = trilha identificada: o aluno continua contando mesmo de
     cabeça baixa ou de lado; **cinza** = pessoa ainda sem identificação.
5. Encerrar a chamada no app normalmente. O módulo volta a aguardar a próxima chamada; `q` na janela o fecha.

O primeiro carregamento dos modelos leva alguns segundos. Para testar sem câmera:
`python modulo_reconhecimento.py --turma 1 --imagem foto.jpg` ou `--video aula.mp4`.

Opções para os experimentos: `--sem-rastreamento` (só rostos visíveis, sem YOLOv8/DeepSORT) e
`--sem-prova-de-vida`. Para mostrar a prova de vida, aponte para a câmera uma foto do aluno no celular:
o rosto deve ficar vermelho e não ser registrado (ainda não testado com ataques reais; ver experimento E2).
