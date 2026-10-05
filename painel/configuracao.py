"""
LivePresenceAI - Configuracao da instalacao (config/livepresenceai.json).

Um unico arquivo guarda tudo o que o painel precisa para ligar o servidor e o modulo da sala. Ele e criado
pelo instalador com segredos aleatorios (chave do JWT, chave do modulo de IA, senha do banco) e nunca vai
para o Git (pasta config/ no .gitignore).
"""
import json
import os
import secrets
from typing import Any, Dict, Optional

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA_CONFIG = os.path.join(RAIZ, "config")
ARQUIVO = os.path.join(PASTA_CONFIG, "livepresenceai.json")
PASTA_CERTIFICADOS = os.path.join(PASTA_CONFIG, "certificados")
PASTA_LOGS = os.path.join(PASTA_CONFIG, "logs")


def python_do_ambiente(pasta: str, janela: bool = False) -> Optional[str]:
    """Python do ambiente virtual da pasta (.venv ou venv); pythonw.exe abre sem console no Windows."""
    nome = "pythonw.exe" if janela else "python.exe"
    for venv in (".venv", "venv"):
        caminho = os.path.join(RAIZ, pasta, venv, "Scripts", nome)
        if os.path.exists(caminho):
            return caminho
    return None


def padrao() -> Dict[str, Any]:
    return {
        "versao": 1,
        "servidor": {
            "ativo": True,
            "porta": 8443,
            "https": True,
            "database_url": "postgresql+psycopg2://livepresenceai:livepresenceai@localhost:5432/livepresenceai",
            "secret_key_jwt": secrets.token_urlsafe(48),
            "chave_modulo_ia": secrets.token_urlsafe(32),
        },
        "sala": {
            "ativo": False,
            "servidor_url": "https://localhost:8443",
            "chave_modulo_ia": None,  # None = a mesma do servidor (servidor e sala no mesmo computador)
            "certificado_sha256": None,  # impressao digital do servidor (descoberta na rede), quando sem a CA
            "sala_id": None,
            "sala_nome": None,
            "camera": 0,
            "mostrar_video": True,
        },
        "iniciar_com_windows": False,
    }


def carregar() -> Dict[str, Any]:
    if not os.path.exists(ARQUIVO):
        return padrao()
    with open(ARQUIVO, encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    base = padrao()  # completa chaves novas de versoes futuras
    for secao in ("servidor", "sala"):
        base[secao].update(dados.get(secao, {}))
    base["iniciar_com_windows"] = dados.get("iniciar_com_windows", False)
    return base


def salvar(config: Dict[str, Any]) -> None:
    os.makedirs(PASTA_CONFIG, exist_ok=True)
    temporario = ARQUIVO + ".tmp"
    with open(temporario, "w", encoding="utf-8") as arquivo:
        json.dump(config, arquivo, indent=2, ensure_ascii=False)
    os.replace(temporario, ARQUIVO)


def chave_da_sala(config: Dict[str, Any]) -> str:
    return config["sala"].get("chave_modulo_ia") or config["servidor"]["chave_modulo_ia"]


def endereco_local(config: Dict[str, Any]) -> str:
    servidor = config["servidor"]
    return f"{'https' if servidor['https'] else 'http'}://localhost:{servidor['porta']}"
