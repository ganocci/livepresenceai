# LivePresenceAI — Passo a passo de instalação, execução e demonstração

Versão: versão final do TCC (07/11/2026).

Os comandos abaixo são para **PowerShell no Windows**.

---

## 0. Instalação para o usuário final (recomendado)

Para uma escola ou faculdade, sem terminal no dia a dia. Precisa de Windows 10 ou 11, permissão de
administrador e internet durante a instalação.

1. Baixar o **Instalar-LivePresenceAI.exe** na página de *Releases* do repositório (ou gerá-lo, seção 9).
2. Dar dois cliques no arquivo. Se aparecer "O Windows protegeu o computador", clicar em **Mais informações →
   Executar assim mesmo** (o instalador não tem assinatura digital); no pedido de administrador, **Sim**.
3. Escolher **Este computador faz tudo** e clicar em **Instalar** (cerca de 10 min, com internet). O instalador
   instala o Python e o PostgreSQL, se faltarem, cria o banco com senha aleatória, prepara os ambientes, gera os
   segredos e o certificado HTTPS, libera o firewall para a rede local e cria os atalhos. Em computadores
   separados: **Só o servidor** num e **Só a câmera de uma sala** nos outros (este pede a chave do módulo de IA,
   copiada no painel do servidor em **Celulares e outras salas**).
4. Clicar em **Abrir o LivePresenceAI** (ou no atalho da área de trabalho) e em **Ligar tudo**.
5. Clicar em **Abrir o app** e criar a **conta do administrador** (só na primeira vez).
6. No app: **avatar (Minha conta) → Administração → Salas → + Sala**; na aba **Professores**, cadastrar os
   professores.
7. No painel, em **Esta sala**: escolher a sala e a câmera (**Testar imagem** para conferir; a janela fecha no X)
   e ligar o reconhecimento. Marcar **Iniciar com o Windows** para não precisar abrir o painel todo dia.
8. Celulares Android: no Chrome do celular, abrir `https://<IP do servidor>:8443/android` (endereço mostrado no
   painel; digitar o `https://`), aceitar o aviso do certificado (**Avançado → Continuar**), baixar o APK e
   permitir a instalação (**Instalar mesmo assim**, se o Play Protect avisar). No mesmo Wi-Fi, o app **encontra o
   servidor sozinho** na primeira abertura (ou em **Procurar servidor**) — não é preciso digitar o IP nem instalar certificado. Pelo
   navegador de outros aparelhos, instalar uma vez o `ca.crt` (painel → **Celulares e outras salas**).

A primeira chamada demora um pouco mais: o módulo de IA baixa os modelos de rosto e de prova de vida
(algumas centenas de MB) e precisa de internet nessa vez. A câmera é aberta em 1920 × 1080; outro valor pode ser
definido na variável `LIVEPRESENCEAI_RESOLUCAO` (ex.: `1280x720`).

**Desinstalar:** Configurações do Windows → Aplicativos → LivePresenceAI → Desinstalar. Os dados (banco e cópias de
segurança) são mantidos, a menos que a exclusão seja confirmada duas vezes.

**Restaurar uma cópia de segurança** (com o servidor desligado no painel; a senha do usuário `livepresenceai` está em `database_url` de `config\livepresenceai.json`):

```powershell
& "C:\Program Files\PostgreSQL\17\bin\pg_restore.exe" -h localhost -U livepresenceai -d livepresenceai --clean --if-exists <arquivo.dump>
```

As seções a seguir descrevem a execução em **modo de desenvolvimento**, a partir do código-fonte.

---

## 1. Pré-requisitos (desenvolvimento)

| Programa | Observação |
|---|---|
| Python 3.12 ou mais novo | Projeto testado em 3.14.7 |
| PostgreSQL | Neste projeto o banco de desenvolvimento usa a porta **5433** (o padrão costuma ser 5432) |
| Flutter SDK | Em pasta sem acentos/espaços, ex.: `C:\src\flutter`, com `C:\src\flutter\bin` no PATH |
| Google Chrome | Para rodar o app no navegador |
| Webcam USB | Para o reconhecimento (testado com a EMEET S600) |

Conferir:

```powershell
python --version
flutter doctor
```

No `flutter doctor`, basta aparecer `[✓] Flutter` e `[✓] Chrome`. Os avisos de Android e Visual Studio podem ser
ignorados (o Android só é necessário para gerar o APK, seção 9).

---

## 2. Primeira instalação (só uma vez por computador)

### 2.1 Banco de dados

No pgAdmin (Query Tool conectado como `postgres`):

```sql
CREATE USER livepresenceai WITH PASSWORD 'livepresenceai';
CREATE DATABASE livepresenceai OWNER livepresenceai;
```

Se o PostgreSQL **não** estiver na porta 5433, definir a conexão antes de subir o backend (em todo terminal do
backend):

```powershell
$env:DATABASE_URL = "postgresql+psycopg2://livepresenceai:livepresenceai@localhost:5432/livepresenceai"
```

### 2.2 Backend

```powershell
cd <pasta do projeto>\backend
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python seed_dados_demo.py
```

O seed cria as tabelas, o professor de demonstração (`professor@livepresenceai.com` / `senha123`), a
**Turma A - Manhã** e 6 alunos com RA fictício. Pode ser rodado mais de uma vez sem duplicar nada. Ao iniciar,
o backend aplica sozinho as migrações pendentes (`database\migracao_*.sql`), também em bancos antigos.

### 2.3 App

```powershell
cd <pasta do projeto>\app
flutter pub get
```

### 2.4 Módulo de IA (reconhecimento facial)

Ambiente separado do backend:

```powershell
cd <pasta do projeto>\ia
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Na primeira execução são baixados os modelos: InsightFace `buffalo_l` (~280 MB) e prova de vida (1,5 MB) para
`C:\Users\<usuário>\.insightface`, e YOLOv8 `yolov8n.pt` (6 MB) para a pasta `ia`. A instalação inclui o PyTorch e
demora alguns minutos.

---

## 3. Executar (todo dia, desenvolvimento)

São **3 terminais**, cada um com o seu ambiente virtual ativo.

**Terminal 1 — backend**

```powershell
cd <pasta do projeto>\backend
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

Esperado: `Uvicorn running on http://127.0.0.1:8000`. Documentação da API em http://127.0.0.1:8000/docs.

> A cada login pode aparecer no terminal `(trapped) error reading bcrypt version` seguido de um *Traceback*.
> **É só um aviso**, conhecido e inofensivo (combinação passlib + bcrypt 4.3). O login funciona normalmente.

**Terminal 2 — app**

```powershell
cd <pasta do projeto>\app
flutter run -d chrome
```

Entrar com o professor de demonstração. A tela **Minhas turmas** mostra as turmas, com o botão **Iniciar
chamada**; o menu de cada turma leva a **Alunos** (com busca por nome e RA, autorização de biometria e cadastro
do rosto), **Histórico** (aulas passadas e relatório de cada uma) e **Frequência** (percentual acumulado de cada
aluno, com destaque abaixo de 75%). No relatório e na frequência, o botão de exportar gera **PDF**, **Excel** ou
**CSV**.

**Terminal 3 — módulo de IA com a câmera** (seção 8) **ou** o simulador de reconhecimentos (seção 5), na pasta
`backend` com o ambiente ativo.

---

## 4. Roteiro da demonstração (~5 minutos)

### Antes de começar
- [ ] Sistema ligado (painel → **Ligar tudo**, ou os terminais da seção 3); login feito no app.
- [ ] Rosto do apresentador cadastrado numa turma de demonstração, com a autorização de biometria ligada.
- [ ] **Nenhuma chamada aberta de ensaio anterior** (ver "Cuidados").
- [ ] Opcional: aba `/docs` aberta para mostrar a API.

### Passo a passo

| # | Ação | O que falar / mostrar |
|---|---|---|
| 1 | Mostrar a arquitetura e a API (`/docs`) | Backend FastAPI com API REST documentada; dados no PostgreSQL; tudo na rede local. |
| 2 | No app, tocar em **Iniciar chamada** | A sessão é criada; o ícone da câmera fica verde quando o módulo da sala responde. |
| 3 | Ficar diante da câmera | Em poucos segundos o aluno aparece **na sala**, sem recarregar a tela (WebSocket). |
| 4 | Sair do campo da câmera por mais de 1 min e voltar | O app mostra **"Fora da sala há…"** e depois **na sala** de novo; o período fora é descontado. |
| 5 | Mostrar uma foto do rosto na tela do celular | A prova de vida recusa a foto (rosto vermelho na janela do módulo). |
| 6 | Marcar **Presente** para um aluno sem biometria | Ajuste manual com motivo; o cálculo continua gravado ao lado da decisão do professor. |
| 7 | Tocar em **Encerrar** e mostrar o relatório | Presença ou falta pela regra dos 40%; exportar em PDF. |
| 8 | Abrir **Frequência** da turma | Percentual acumulado e destaque de quem está abaixo de 75%. |

### Cuidados

- **Encerrar a chamada ao fim de cada ensaio.** Abrir a mesma turma em menos de 4 h **retoma a chamada do ensaio**
  ("Chamada em andamento retomada"), com os tempos antigos.
- **Uma janela de vídeo por câmera:** se o reconhecimento estiver ligado no painel, não abrir outro programa na
  mesma câmera (Teams, câmera do Windows, ferramentas dos experimentos).
- **Prova de vida:** rostos muito próximos da câmera podem ser recusados; para a demonstração, ficar a cerca de
  2 m. Se o aluno não for reconhecido, o professor marca a presença manualmente.
- Se a faixa "reconectando…" aparecer, o app reconecta sozinho quando o servidor voltar.

---

## 5. Simulador de reconhecimentos (testes sem câmera)

O simulador ocupa o lugar do módulo de IA e usa o mesmo contrato (`POST /sessoes/{id}/reconhecimento` com a chave
do módulo). O número da sessão aparece no histórico do app.

```powershell
python simulador_eventos.py N --demo                   # roteiro pronto (6 alunos do seed)
python simulador_eventos.py N                          # alunos 1 a 5 chegam e ficam
python simulador_eventos.py N --alunos 1,2,3           # só esses alunos aparecem
python simulador_eventos.py N --sai 4:40               # aluno 4 sai aos 40 s e não volta
python simulador_eventos.py N --pausa 3:40-120         # aluno 3 fica fora de 40 s a 120 s
python simulador_eventos.py N --intervalo 2 --chegada-max 10 --duracao 60
```

Uma saída só é descontada se passar de **60 s** sem detecção. Para ensaios mais rápidos, subir o backend com um
limite menor (só para teste):

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
| App: "Não foi possível conectar ao servidor" | Servidor desligado ou outro endereço | Ligar o servidor no painel; no app, **Procurar servidor** |
| Celular: `ERR_EMPTY_RESPONSE` ao baixar o APK | Endereço digitado com `http://` | Digitar o endereço inteiro com `https://` |
| Celular não encontra o servidor | Rede de visitantes isola os aparelhos, ou firewall | Usar a mesma rede do servidor; no app, **Digitar o endereço manualmente** |
| Backend não sobe: erro de conexão com o banco | PostgreSQL parado ou porta diferente | Iniciar o serviço; ajustar `DATABASE_URL` (seção 2.1) |
| Menu dos experimentos: "conexão recusada" em `localhost:8443` | Servidor desligado (fechar o painel desliga o servidor) | Abrir o painel e ligar o servidor |
| Simulador: `[erro] ... 401` | Chave do módulo de IA diferente entre backend e simulador | Não definir `CHAVE_MODULO_IA`, ou definir o mesmo valor nos dois terminais |
| Simulador: `[erro] ... 404 Sessão não encontrada ou já encerrada` | Número de sessão errado ou chamada já encerrada | Conferir o número no histórico do app |
| `Activate.ps1` bloqueado | Política de execução do PowerShell | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| Login bloqueado por 15 min | 5 senhas erradas seguidas para o mesmo e-mail | Aguardar 15 min ou reiniciar o servidor |
| Módulo de IA: "Nao foi possivel abrir a camera 0" | Webcam em uso por outro programa ou índice diferente | Fechar Teams/câmera do Windows; tentar outra câmera no painel (ou `--camera 1`) |
| Módulo de IA parado em "aguardando o professor" | Chamada aberta em outra turma/sala, ou outra chave | Conferir a sala no painel (ou `--turma`) |
| Aluno não reconhecido | Sem cadastro facial, rosto de lado, luz ruim ou recusado na prova de vida | Cadastrar o rosto; olhar para a câmera; ajuste manual pelo professor |

---

## 8. Reconhecimento facial com a câmera

### 8.1 Cadastro facial (uma vez por aluno)

**Pelo app (forma normal):** em **Alunos**, editar o aluno e ligar a **autorização de biometria** (só para quem
assinou a autorização na matrícula). Depois tocar no ícone de rosto do aluno, enquadrar o rosto na moldura e
**Capturar**: o app tira 5 fotos e mostra "Rosto cadastrado" ou o que corrigir. As fotos são processadas em
memória e descartadas; só o vetor facial é gravado. No computador, a câmera do navegador funciona em
`localhost`; num celular, use o app instalado.

**Pelo script (laboratório)**, no terminal do módulo de IA:

```powershell
python cadastro_facial.py --turma 1      # lista os alunos (ID, nome, se já tem cadastro)
python cadastro_facial.py --aluno 1      # cadastra o aluno de ID 1 pela webcam
```

Outras opções: `--camera 1`, `--imagem foto.jpg` (cadastro por foto) e `--remover 1` (exclui o cadastro facial).

### 8.2 Chamada com reconhecimento

1. Servidor e app ligados.
2. Ligar o reconhecimento no painel (**Esta sala**) ou, em desenvolvimento:
   ```powershell
   python modulo_reconhecimento.py --sala 1        # ou --turma 1
   ```
3. No app, **Iniciar chamada**. Em até 5 s o módulo mostra `Chamada aberta: sessao #N`.
4. Quem estiver cadastrado e aparecer na câmera é marcado no app como **na sala**. Na janela de vídeo:
   - rosto **verde** com nome e similaridade = reconhecido; **laranja** = não reconhecido;
     **vermelho** = recusado na prova de vida (foto ou tela);
   - pessoa com contorno **azul** e `#N Nome` = trilha identificada: o aluno continua contando mesmo de cabeça
     baixa ou de lado; **cinza** = pessoa ainda sem identificação.
5. Encerrar a chamada no app. O módulo volta a aguardar a próxima chamada. Fechar a janela de vídeo no X fecha
   só o vídeo; o reconhecimento continua (desliga-se pelo painel ou com `q` na janela).

Para testar sem câmera: `--imagem foto.jpg` ou `--video aula.mp4`. Opções dos experimentos:
`--sem-rastreamento`, `--sem-prova-de-vida` e `--medir arquivo.csv --duracao N` (desempenho).

### 8.3 Experimentos do TCC

As ferramentas dos experimentos ficam só no código-fonte (não vão no instalador). Com o servidor ligado e o
reconhecimento da sala desligado:

```powershell
powershell -ExecutionPolicy Bypass -File ia\experimentos.ps1
```

O menu lista as turmas e os números dos alunos, conduz o E1 e o E2 (tentativas guiadas, que podem ser
interrompidas e retomadas), a aula do E3 com o E5 e gera um `.zip` com os resultados. O protocolo completo está em
[docs/experimentos/PROTOCOLO.md](docs/experimentos/PROTOCOLO.md).

---

## 9. Gerar o instalador e o APK (equipe)

```powershell
powershell -ExecutionPolicy Bypass -File instalador\empacotar.ps1 -CompilarApp
```

Gera `dist\Instalar-LivePresenceAI.exe` com o sistema, o app web e o APK compilados (sem `-CompilarApp`, usa o app
já compilado em `app\build`). O APK sozinho: `powershell -ExecutionPolicy Bypass -File app\gerar_apk.ps1` (precisa
do Android SDK em `C:\Android\Sdk`).
