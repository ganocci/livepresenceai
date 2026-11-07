# LivePresenceAI

Sistema de lista de presença automática com visão computacional, desenvolvido como Trabalho de Conclusão de
Curso de Ciência da Computação na UNIP (2026), por João Pedro Santos de Oliveira, Lucas Brandão Oliveira e
Filipe Félix da Silva, com orientação do Prof. Álvaro Nunes.

A câmera da sala reconhece os alunos e o sistema registra a entrada e o **tempo de permanência** de cada um, em vez
de só "presente ou ausente". O professor acompanha a chamada em tempo real pelo celular, ajusta presenças
manualmente e exporta relatórios. Todo o processamento é feito na rede local da instituição: as imagens não saem do
computador da sala, e só são guardados vetores faciais de alunos que autorizaram a biometria.

## Componentes

| Pasta | O que é | Tecnologias |
|---|---|---|
| `backend/` | API, regras de negócio, tempo real e relatórios | Python, FastAPI, PostgreSQL, WebSocket |
| `ia/` | Módulo do computador da sala: detecção, rastreamento, prova de vida e reconhecimento | OpenCV, YOLOv8, DeepSORT, InsightFace |
| `app/` | Aplicativo do professor (Android e navegador) | Flutter |
| `painel/` | Painel do computador: liga o servidor e o reconhecimento, escolhe sala e câmera, faz cópia de segurança | Python (Tkinter) |
| `instalador/`, `instalar.ps1` | Instalador único para Windows | PowerShell, IExpress |
| `database/` | Esquema de referência e migrações | SQL |
| `docs/` | Protocolo dos experimentos | — |

## Instalação rápida (recomendada)

Precisa de **Windows 10 ou 11**, permissão de administrador e internet durante a instalação.

1. Baixe o **`Instalar-LivePresenceAI.exe`** na página de [Releases](../../releases) do repositório.
2. Dê dois cliques, aceite o pedido de administrador, escolha **Este computador faz tudo** e clique em **Instalar**
   (cerca de 10 min). O instalador instala o Python e o PostgreSQL, se faltarem, e já traz o app web e o APK
   compilados.
3. No painel que abre, clique em **Ligar tudo** e depois em **Abrir o app**; no primeiro acesso, crie a conta do
   administrador.
4. No celular Android, abra no Chrome o endereço mostrado no painel com `/android` no final para baixar o app.

## A partir do código-fonte

Clonar o repositório **não basta** para o sistema funcionar: o app web e o APK não ficam no Git (são gerados), e a
configuração, as senhas e o certificado são criados na instalação. Duas formas:

- **Instalação pelo código:** em um PowerShell como administrador, na pasta do projeto,
  `powershell -ExecutionPolicy Bypass -File instalar.ps1`. Para ter o app web, é preciso ter o
  [Flutter](https://docs.flutter.dev/get-started/install) instalado (o script compila o app se encontrar o
  Flutter).
- **Modo de desenvolvimento:** três terminais (backend, app e módulo de IA), descritos no
  [PASSO_A_PASSO.md](PASSO_A_PASSO.md), com Python 3.12 ou mais novo, PostgreSQL e Flutter.

Em qualquer caso, a primeira chamada baixa os modelos de reconhecimento (algumas centenas de MB) e precisa de
internet.

## Testes

```powershell
cd backend
pip install -r requirements-dev.txt
python -m pytest          # 23 casos das regras de negócio, num schema temporário do PostgreSQL
cd ..\app
flutter test              # 10 casos
```

## Documentação

- [PASSO_A_PASSO.md](PASSO_A_PASSO.md): instalação, execução, demonstração e problemas comuns.
- [docs/experimentos/PROTOCOLO.md](docs/experimentos/PROTOCOLO.md): protocolo dos experimentos do TCC.

## Licenças de terceiros

Os modelos pré-treinados do InsightFace são licenciados apenas para pesquisa não comercial, e o Ultralytics YOLOv8 é
distribuído sob a AGPL-3.0. O projeto tem fins acadêmicos; um uso institucional exigiria licenciar ou substituir esses
componentes.
