"""
LivePresenceAI - Liga, desliga e verifica o servidor (backend) e o modulo de IA da sala.

Os processos rodam sem janela de console; a saida de cada um vai para config/logs/<nome>.log.
"""
import os
import socket
import subprocess
import sys
import time
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

import configuracao as cfg

sys.path.insert(0, os.path.join(cfg.RAIZ, "backend"))
import descoberta  # noqa: E402  (procura o servidor na rede, sem digitar o IP)

SEM_JANELA = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


class Servico:
    """Um processo filho com registro em arquivo."""

    def __init__(self, nome: str):
        self.nome = nome
        self.processo: Optional[subprocess.Popen] = None
        self.log = os.path.join(cfg.PASTA_LOGS, f"{nome}.log")

    @property
    def rodando(self) -> bool:
        return self.processo is not None and self.processo.poll() is None

    def iniciar(self, comando: List[str], pasta: str, ambiente: Dict[str, str], janela: bool = False) -> None:
        if self.rodando:
            return
        os.makedirs(cfg.PASTA_LOGS, exist_ok=True)
        saida = open(self.log, "a", encoding="utf-8", errors="replace")
        saida.write(f"\n===== {time.strftime('%d/%m/%Y %H:%M:%S')} iniciando {self.nome} =====\n")
        saida.flush()
        self.processo = subprocess.Popen(
            comando, cwd=pasta, env={**os.environ, **ambiente, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
            stdout=saida, stderr=subprocess.STDOUT, creationflags=0 if janela else SEM_JANELA,
        )

    def parar(self) -> None:
        if self.rodando:
            self.processo.terminate()
            try:
                self.processo.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.processo.kill()
        self.processo = None

    def ultimas_linhas(self, quantidade: int = 300) -> str:
        if not os.path.exists(self.log):
            return ""
        with open(self.log, encoding="utf-8", errors="replace") as arquivo:
            return "".join(arquivo.readlines()[-quantidade:])


# ---------------------- SERVIDOR ----------------------

def preparar_certificado() -> Optional[str]:
    """Gera/atualiza o certificado HTTPS (IPs podem mudar). Devolve o erro, se houver."""
    sys.path.insert(0, os.path.join(cfg.RAIZ, "backend"))
    try:
        import certificado_local
        certificado_local.garantir_certificado_servidor(cfg.PASTA_CERTIFICADOS)
        return None
    except Exception as erro:  # cryptography ausente, pasta sem permissao etc.
        return str(erro)


def iniciar_servidor(servico: Servico, config: dict) -> Optional[str]:
    """Liga o backend (API + app web em /app/). Devolve uma mensagem de erro ou None."""
    python = cfg.python_do_ambiente("backend")
    if not python:
        return "Ambiente do servidor nao encontrado (backend/.venv). Rode o instalador."
    s = config["servidor"]
    comando = [python, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(s["porta"])]
    if s["https"]:
        erro = preparar_certificado()
        if erro:
            return f"Nao foi possivel preparar o certificado HTTPS: {erro}"
        comando += ["--ssl-certfile", os.path.join(cfg.PASTA_CERTIFICADOS, "servidor.crt"),
                    "--ssl-keyfile", os.path.join(cfg.PASTA_CERTIFICADOS, "servidor.key")]
    ambiente = {
        "DATABASE_URL": s["database_url"],
        "SECRET_KEY_JWT": s["secret_key_jwt"],
        "CHAVE_MODULO_IA": s["chave_modulo_ia"],
        "FREQUENCIA_MINIMA_AULA": str(s.get("frequencia_minima_aula", 40)),
        "FREQUENCIA_MINIMA_TURMA": str(s.get("frequencia_minima_turma", 75)),
        # Descoberta na rede (backend/descoberta.py): o que anunciar aos apps
        "LIVEPRESENCEAI_PORTA_PUBLICA": str(s["porta"]),
        "LIVEPRESENCEAI_HTTPS": "1" if s["https"] else "0",
        "LIVEPRESENCEAI_CERTIFICADO": os.path.join(cfg.PASTA_CERTIFICADOS, "servidor.crt"),
    }
    servico.iniciar(comando, os.path.join(cfg.RAIZ, "backend"), ambiente)
    return None


class _AdaptadorFixado(HTTPAdapter):
    """Confere a impressao digital do certificado (pinning), como o app do celular."""

    def __init__(self, certificado_sha256: str, **kwargs):
        self.certificado_sha256 = certificado_sha256
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["assert_fingerprint"] = self.certificado_sha256
        return super().init_poolmanager(*args, **kwargs)


def _sessao(config: dict) -> requests.Session:
    """Valida o HTTPS pela CA da instalacao (mesmo computador do servidor) ou pela impressao digital obtida
    na descoberta (computador so de sala)."""
    sessao = requests.Session()
    ca = os.path.join(cfg.PASTA_CERTIFICADOS, "ca.crt")
    if os.path.exists(ca):
        sessao.verify = ca
    elif config["sala"].get("certificado_sha256"):
        sessao.verify = False
        sessao.mount("https://", _AdaptadorFixado(config["sala"]["certificado_sha256"]))
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return sessao


def servidor_respondendo(config: dict, url: Optional[str] = None) -> bool:
    try:
        r = _sessao(config).get((url or cfg.endereco_local(config)) + "/", timeout=2,
                                headers={"Accept": "application/json"})
        return r.ok and r.json().get("projeto") == "LivePresenceAI"
    except (requests.RequestException, ValueError):
        return False


def localizar_servidor_da_sala(config: dict) -> bool:
    """Computador so de sala: se o servidor nao responde no endereco salvo (o roteador pode ter trocado o IP),
    procura na rede e, achando o mesmo servidor (mesma impressao digital) ou um unico, salva o novo endereco.
    Devolve True se o endereco mudou."""
    if config["servidor"]["ativo"] or servidor_respondendo(config, config["sala"]["servidor_url"]):
        return False
    achados = descoberta.procurar()
    pino = config["sala"].get("certificado_sha256")
    mesmos = [s for s in achados if pino and s.get("certificado_sha256") == pino]
    escolhido = mesmos[0] if mesmos else (achados[0] if len(achados) == 1 and not pino else None)
    if not escolhido or escolhido["url"] == config["sala"]["servidor_url"]:
        return False
    config["sala"]["servidor_url"] = escolhido["url"]
    config["sala"]["certificado_sha256"] = escolhido.get("certificado_sha256")
    cfg.salvar(config)
    return True


def banco_aceitando(config: dict) -> bool:
    """O PostgreSQL aceita conexoes na porta configurada?"""
    endereco = urlparse(config["servidor"]["database_url"].replace("postgresql+psycopg2", "postgresql"))
    try:
        with socket.create_connection((endereco.hostname or "localhost", endereco.port or 5432), timeout=1.5):
            return True
    except OSError:
        return False


# ---------------------- COPIA DE SEGURANCA (backup do banco) ----------------------

PASTA_BACKUPS = os.path.join(cfg.PASTA_CONFIG, "backups")
BACKUPS_GUARDADOS = 14  # as mais antigas sao apagadas


def _pg_dump() -> Optional[str]:
    """pg_dump do PostgreSQL instalado (a versao mais nova, que tambem le bancos de versoes anteriores)."""
    import glob
    import shutil

    candidatos = glob.glob(os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "PostgreSQL", "*",
                                        "bin", "pg_dump.exe"))
    candidatos.sort(key=lambda c: int("".join(ch for ch in os.path.basename(os.path.dirname(os.path.dirname(c)))
                                              if ch.isdigit()) or 0), reverse=True)
    return candidatos[0] if candidatos else shutil.which("pg_dump")


def ultimo_backup() -> Optional[str]:
    if not os.path.isdir(PASTA_BACKUPS):
        return None
    arquivos = sorted(f for f in os.listdir(PASTA_BACKUPS) if f.endswith(".dump"))
    return os.path.join(PASTA_BACKUPS, arquivos[-1]) if arquivos else None


def backup_vencido(horas: float = 24) -> bool:
    ultimo = ultimo_backup()
    return ultimo is None or time.time() - os.path.getmtime(ultimo) >= horas * 3600


def fazer_backup(config: dict) -> str:
    """
    Copia completa do banco (pg_dump, formato custom) em config/backups/livepresenceai_AAAAMMDD_HHMMSS.dump.
    Devolve o caminho; levanta RuntimeError com mensagem para o usuario se falhar. Restaurar: ver o
    PASSO_A_PASSO.md (secao 0).
    """
    pg_dump = _pg_dump()
    if not pg_dump:
        raise RuntimeError("pg_dump não encontrado (vem com o PostgreSQL).")
    endereco = urlparse(config["servidor"]["database_url"].replace("postgresql+psycopg2", "postgresql"))
    os.makedirs(PASTA_BACKUPS, exist_ok=True)
    destino = os.path.join(PASTA_BACKUPS, time.strftime("livepresenceai_%Y%m%d_%H%M%S.dump"))
    ambiente = dict(os.environ, PGPASSWORD=endereco.password or "")
    comando = [pg_dump, "-h", endereco.hostname or "localhost", "-p", str(endereco.port or 5432),
               "-U", endereco.username or "livepresenceai", "-Fc", "-f", destino, endereco.path.lstrip("/")]
    opcoes = dict(p.split("=", 1) for p in endereco.query.split("&") if "=" in p).get("options", "")
    if "search_path" in opcoes:  # banco num schema proprio (testes): copia so ele
        from urllib.parse import unquote
        comando[-1:-1] = ["-n", unquote(opcoes).split("search_path=")[-1].split()[0]]
    saida = subprocess.run(comando, env=ambiente, capture_output=True, text=True, timeout=600,
                           creationflags=SEM_JANELA)
    if saida.returncode != 0 or not os.path.exists(destino):
        if os.path.exists(destino):
            os.remove(destino)
        raise RuntimeError(f"A cópia de segurança falhou: {saida.stderr.strip()[:300]}")
    antigos = sorted(f for f in os.listdir(PASTA_BACKUPS) if f.endswith(".dump"))[:-BACKUPS_GUARDADOS]
    for nome in antigos:
        os.remove(os.path.join(PASTA_BACKUPS, nome))
    return destino


def enderecos_para_celulares(config: dict) -> List[str]:
    s = config["servidor"]
    sys.path.insert(0, os.path.join(cfg.RAIZ, "backend"))
    try:
        from certificado_local import ips_locais
        ips = [ip for ip in ips_locais() if not ip.startswith("127.")]
    except Exception:
        ips = []
    esquema = "https" if s["https"] else "http"
    return [f"{esquema}://{ip}:{s['porta']}" for ip in ips]


# ---------------------- MODULO DA SALA ----------------------

def _ambiente_sala(config: dict) -> Dict[str, str]:
    ambiente = {"LIVEPRESENCEAI_BACKEND": config["sala"]["servidor_url"], "CHAVE_MODULO_IA": cfg.chave_da_sala(config)}
    ca = os.path.join(cfg.PASTA_CERTIFICADOS, "ca.crt")
    if config["sala"]["servidor_url"].startswith("https") and os.path.exists(ca):
        ambiente["LIVEPRESENCEAI_CA"] = ca
    elif config["sala"].get("certificado_sha256"):
        ambiente["LIVEPRESENCEAI_CERTIFICADO_SHA256"] = config["sala"]["certificado_sha256"]
    return ambiente


def listar_salas(config: dict) -> List[dict]:
    """Salas cadastradas no servidor (GET /ia/salas, com a chave do modulo de IA)."""
    localizar_servidor_da_sala(config)
    r = _sessao(config).get(config["sala"]["servidor_url"].rstrip("/") + "/ia/salas",
                            headers={"X-API-Key": cfg.chave_da_sala(config)}, timeout=4)
    r.raise_for_status()
    return r.json()


def listar_cameras() -> List[int]:
    python = cfg.python_do_ambiente("ia")
    if not python:
        return []
    saida = subprocess.run([python, "modulo_reconhecimento.py", "--listar-cameras"], cwd=os.path.join(cfg.RAIZ, "ia"),
                           capture_output=True, text=True, timeout=90, creationflags=SEM_JANELA)
    for linha in reversed(saida.stdout.strip().splitlines()):
        if linha.startswith("["):
            return [int(i) for i in linha.strip("[]").split(",") if i.strip()]
    return []


def testar_camera(indice: int) -> None:
    python = cfg.python_do_ambiente("ia")
    if python:
        subprocess.Popen([python, "modulo_reconhecimento.py", "--testar-camera", str(indice)],
                         cwd=os.path.join(cfg.RAIZ, "ia"), creationflags=SEM_JANELA)


def iniciar_sala(servico: Servico, config: dict) -> Optional[str]:
    python = cfg.python_do_ambiente("ia")
    if not python:
        return "Ambiente do modulo de IA nao encontrado (ia/.venv). Rode o instalador com a opcao da sala."
    sala = config["sala"]
    if sala.get("sala_id") is None:
        return "Escolha a sala deste computador antes de ligar o reconhecimento."
    localizar_servidor_da_sala(config)
    comando = [python, "modulo_reconhecimento.py", "--sala", str(sala["sala_id"]), "--camera", str(sala["camera"])]
    if not sala.get("mostrar_video", True):
        comando.append("--sem-janela")
    servico.iniciar(comando, os.path.join(cfg.RAIZ, "ia"), _ambiente_sala(config), janela=False)
    return None
