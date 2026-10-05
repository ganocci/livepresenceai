"""
LivePresenceAI - Descoberta do servidor na rede local (para o app nao precisar do IP).

O app do celular envia, por broadcast UDP na porta 47800, a mensagem "LIVEPRESENCEAI_PROCURA". O servidor
responde direto ao celular com um JSON:
    {"projeto": "LivePresenceAI", "versao": 1, "nome": "<computador>",
     "url": "https://<IP desta maquina na rede do celular>:8443",
     "certificado_sha256": "<impressao digital do certificado HTTPS, ou null em HTTP>"}

Com a impressao digital, o app confia no certificado deste servidor sem que o usuario precise instalar a CA
no celular (pinning). Limitacao: outro computador na mesma rede pode responder no lugar do servidor; o
risco e aceito para uso em rede local da instituicao.

Configuracao (variaveis de ambiente, definidas pelo painel):
    LIVEPRESENCEAI_DESCOBERTA=0          desliga
    LIVEPRESENCEAI_PORTA_PUBLICA=8443    porta anunciada (padrao 8000)
    LIVEPRESENCEAI_HTTPS=1               anuncia https://
    LIVEPRESENCEAI_CERTIFICADO=<arquivo> certificado do servidor (PEM) para a impressao digital
"""
import hashlib
import json
import os
import socket
import ssl
import threading
from typing import Optional

PORTA_DESCOBERTA = 47800
PERGUNTA = b"LIVEPRESENCEAI_PROCURA"


def impressao_digital(caminho_pem: Optional[str]) -> Optional[str]:
    """SHA-256 (hex) do certificado em DER, como o app calcula."""
    if not caminho_pem or not os.path.exists(caminho_pem):
        return None
    with open(caminho_pem, encoding="ascii") as arquivo:
        der = ssl.PEM_cert_to_DER_cert(arquivo.read())
    return hashlib.sha256(der).hexdigest()


def ip_para(destino: str) -> str:
    """IP desta maquina na interface usada para falar com o celular (sem enviar nada)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((destino, 9))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def resposta_para(destino: str) -> bytes:
    https = os.getenv("LIVEPRESENCEAI_HTTPS", "0") == "1"
    porta = int(os.getenv("LIVEPRESENCEAI_PORTA_PUBLICA", "8000"))
    dados = {
        "projeto": "LivePresenceAI",
        "versao": 1,
        "nome": socket.gethostname(),
        "url": f"{'https' if https else 'http'}://{ip_para(destino)}:{porta}",
        "certificado_sha256": impressao_digital(os.getenv("LIVEPRESENCEAI_CERTIFICADO")) if https else None,
    }
    return json.dumps(dados).encode("utf-8")


def _atender(sock: socket.socket) -> None:
    while True:
        try:
            mensagem, (ip, porta) = sock.recvfrom(512)
        except OSError:
            return
        if mensagem.strip().startswith(PERGUNTA):
            try:
                sock.sendto(resposta_para(ip), (ip, porta))
            except OSError:
                pass


def iniciar() -> Optional[str]:
    """Liga o respondedor em segundo plano. Devolve um aviso se nao for possivel (porta ocupada etc.)."""
    if os.getenv("LIVEPRESENCEAI_DESCOBERTA", "1") == "0":
        return None
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("0.0.0.0", PORTA_DESCOBERTA))
    except OSError as erro:
        sock.close()
        return f"descoberta na rede indisponivel (porta UDP {PORTA_DESCOBERTA}: {erro})"
    threading.Thread(target=_atender, args=(sock,), daemon=True, name="descoberta").start()
    return None


def procurar(tempo: float = 3.0) -> list:
    """Lado cliente (instalador/painel do computador de sala): procura servidores na rede, como o app faz."""
    import time
    achados = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.3)
        fim = time.time() + tempo
        proximo_envio = 0.0
        while time.time() < fim:
            if time.time() >= proximo_envio:
                try:
                    sock.sendto(PERGUNTA, ("255.255.255.255", PORTA_DESCOBERTA))
                except OSError:
                    pass
                proximo_envio = time.time() + 1.0
            try:
                dados, _ = sock.recvfrom(4096)
                resposta = json.loads(dados.decode("utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(resposta, dict) and resposta.get("projeto") == "LivePresenceAI" and resposta.get("url"):
                achados[resposta["url"]] = resposta
    return list(achados.values())


if __name__ == "__main__":
    # python descoberta.py  ->  lista os servidores encontrados (uma linha JSON por servidor)
    for servidor in procurar():
        print(json.dumps(servidor))
