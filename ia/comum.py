"""
LivePresenceAI - Modulo de IA: partes comuns ao cadastro facial e ao reconhecimento.

- Configuracao (backend, chave do modulo, camera) por variaveis de ambiente.
- Reconhecedor: InsightFace com deteccao (SCRFD) e reconhecimento (ArcFace) do pacote buffalo_l.
- Fontes de imagem: webcam/camera USB, arquivo de video ou imagem fixa (para testes).
"""
import os
import time
import unicodedata
from typing import Iterator, List, Optional, Tuple

import cv2
import numpy as np
import requests
from requests.adapters import HTTPAdapter

URL_BACKEND = os.getenv("LIVEPRESENCEAI_BACKEND", "http://127.0.0.1:8000").rstrip("/")
CHAVE_MODULO_IA = os.getenv("CHAVE_MODULO_IA", "livepresenceai-ia-dev")
# HTTPS da rede local: certificado da CA da instalacao (gerada pelo painel/instalador) para validar o servidor
CA_LOCAL = os.getenv("LIVEPRESENCEAI_CA") or None
# Computador de sala sem a CA: aceita o certificado cuja impressao digital (SHA-256) veio da descoberta na rede
CERTIFICADO_SHA256 = os.getenv("LIVEPRESENCEAI_CERTIFICADO_SHA256") or None
MODELO = os.getenv("MODELO_INSIGHTFACE", "buffalo_l")
TAMANHO_DETECCAO = 640
# Escore minimo da prova de vida (0 a 1); 0,8 e o padrao do InsightFace, a calibrar no experimento E2
LIMIAR_PROVA_VIDA = float(os.getenv("LIMIAR_PROVA_VIDA", "0.8"))
# Rostos mais estreitos que isto (px) dispensam a prova de vida, que tende a recusar rostos pequenos e distantes
# genuinos. 0 = nunca dispensa (padrao). Aumenta o risco de ataque com foto pequena: decidir com os dados do E2.
PROVA_VIDA_DISPENSAR_ABAIXO_PX = int(os.getenv("PROVA_VIDA_DISPENSAR_ABAIXO_PX", "0"))
# Resolucao pedida a camera (largura x altura). Sem pedir, o OpenCV usa a resolucao padrao do driver (em geral
# 640x480), e os rostos a 2-3 m ficam com 25-30 px; a camera usa a maior resolucao suportada ate este valor.
RESOLUCAO_CAMERA = os.getenv("LIVEPRESENCEAI_RESOLUCAO", "1920x1080")


def cabecalhos() -> dict:
    return {"X-API-Key": CHAVE_MODULO_IA}


class _AdaptadorFixado(HTTPAdapter):
    """Confere a impressao digital do certificado do servidor no lugar da cadeia de CAs (pinning)."""

    def __init__(self, certificado_sha256: str, **kwargs):
        self.certificado_sha256 = certificado_sha256
        super().__init__(**kwargs)

    def init_poolmanager(self, *args, **kwargs):
        kwargs["assert_fingerprint"] = self.certificado_sha256
        return super().init_poolmanager(*args, **kwargs)


def _criar_sessao() -> requests.Session:
    sessao = requests.Session()
    if CA_LOCAL:
        sessao.verify = CA_LOCAL
    elif CERTIFICADO_SHA256:
        sessao.verify = False  # a validacao passa a ser a impressao digital (assert_fingerprint)
        sessao.mount("https://", _AdaptadorFixado(CERTIFICADO_SHA256))
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return sessao


_SESSAO = _criar_sessao()


def api(metodo: str, caminho: str, **kwargs) -> requests.Response:
    return _SESSAO.request(metodo, f"{URL_BACKEND}{caminho}", headers=cabecalhos(), timeout=5, **kwargs)


def listar_cameras(maximo: int = 6) -> List[int]:
    """Indices de camera que abrem e entregam imagem (para o painel oferecer a escolha)."""
    encontradas = []
    for indice in range(maximo):
        captura = cv2.VideoCapture(indice, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(indice)
        if captura.isOpened() and captura.read()[0]:
            encontradas.append(indice)
        captura.release()
    return encontradas


def sem_acentos(texto: str) -> str:
    """O cv2.putText nao desenha acentos; usado so nos rotulos da janela."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def ler_imagem(caminho: str) -> Optional[np.ndarray]:
    """cv2.imread falha no Windows com acentos no caminho (ex.: C:\\Users\\João); le os bytes e decodifica."""
    try:
        return cv2.imdecode(np.fromfile(caminho, dtype=np.uint8), cv2.IMREAD_COLOR)
    except (OSError, ValueError):
        return None


class Reconhecedor:
    """
    Detecta rostos e extrai o vetor de caracteristicas (embedding normalizado, 512 posicoes).
    Com prova_de_vida, usa o modelo de anti-spoofing distribuido pelo InsightFace (arquitetura MiniFASNet,
    entrada 80x80) para recusar fotos e telas mostradas a camera.
    """

    def __init__(self, prova_de_vida: bool = False):
        # Importado aqui para o "--help" dos scripts nao carregar o onnxruntime
        import onnxruntime
        from insightface.app import FaceAnalysis

        provedores = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider")
                      if p in onnxruntime.get_available_providers()]
        # "observe": o InsightFace calcula o escore mas nao bloqueia o embedding; a decisao fica em vivo()
        self.app = FaceAnalysis(name=MODELO, allowed_modules=["detection", "recognition"], providers=provedores,
                                addons=["liveness"] if prova_de_vida else [],
                                liveness_mode="observe", liveness_threshold=LIMIAR_PROVA_VIDA)
        self.app.prepare(ctx_id=0 if provedores[0] == "CUDAExecutionProvider" else -1,
                         det_size=(TAMANHO_DETECCAO, TAMANHO_DETECCAO))
        self.provedor = provedores[0]

    def rostos(self, quadro: np.ndarray) -> list:
        """Detecta e extrai o embedding de todos os rostos do quadro."""
        return self.app.get(quadro)

    def detectar(self, quadro: np.ndarray) -> list:
        """So a deteccao (SCRFD), sem o embedding: usado com o rastreamento, que reconhece uma vez por trilha."""
        from insightface.app.common import Face

        caixas, pontos = self.app.det_model.detect(quadro, max_num=0, metric="default")
        return [Face(bbox=caixas[i, 0:4], kps=None if pontos is None else pontos[i], det_score=caixas[i, 4])
                for i in range(caixas.shape[0])]

    def extrair(self, quadro: np.ndarray, rosto) -> np.ndarray:
        """Embedding normalizado (ArcFace) de um rosto ja detectado."""
        self.app.models["recognition"].get(quadro, rosto)
        return rosto.normed_embedding

    def vivo(self, quadro: np.ndarray, rosto) -> Optional[bool]:
        """
        Prova de vida: True (pessoa real), False (foto/tela) ou None (inconclusivo: rosto cortado na borda
        da imagem). Sem prova de vida ligada, sempre True.
        """
        modelo = self.app.addons.get("liveness")
        if modelo is None:
            return True
        resultado = rosto.get("liveness") or modelo.get(quadro, rosto)
        return resultado["is_live"] if resultado["status"] == "ok" else None

    @staticmethod
    def escore_vida(rosto) -> Optional[float]:
        resultado = rosto.get("liveness")
        return resultado["live_score"] if resultado else None


class Galeria:
    """Embeddings dos alunos cadastrados da turma; identifica um rosto por similaridade de cosseno."""

    def __init__(self, alunos: List[dict]):
        self.ids = [a["aluno_id"] for a in alunos]
        self.nomes = {a["aluno_id"]: a["nome"] for a in alunos}
        self.matriz = np.array([a["embedding"] for a in alunos], dtype=np.float32) if alunos else None

    def __len__(self) -> int:
        return len(self.ids)

    def identificar(self, embedding: np.ndarray) -> Tuple[Optional[int], float]:
        """Aluno mais parecido e a similaridade (embeddings normalizados: produto escalar = cosseno)."""
        if self.matriz is None:
            return None, 0.0
        similaridades = self.matriz @ embedding
        i = int(np.argmax(similaridades))
        return self.ids[i], float(similaridades[i])


def abrir_fonte(camera: int, imagem: Optional[str], video: Optional[str]) -> Iterator[np.ndarray]:
    """Gera quadros da camera, de um video (em loop) ou de uma imagem fixa (~10 quadros/s)."""
    if imagem:
        quadro = ler_imagem(imagem)
        if quadro is None:
            raise SystemExit(f"Nao foi possivel ler a imagem {imagem}")
        while True:
            yield quadro.copy()
            time.sleep(0.1)

    captura = cv2.VideoCapture(video if video else camera)
    if not captura.isOpened():
        raise SystemExit(f"Nao foi possivel abrir {'o video ' + video if video else f'a camera {camera}'}. "
                         "Verifique a conexao ou tente outro indice (--camera 1).")
    if not video and RESOLUCAO_CAMERA:
        largura, altura = (int(v) for v in RESOLUCAO_CAMERA.lower().split("x"))
        captura.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))  # Full HD a 30 quadros/s em USB 2.0
        captura.set(cv2.CAP_PROP_FRAME_WIDTH, largura)
        captura.set(cv2.CAP_PROP_FRAME_HEIGHT, altura)
        print(f"Camera {camera}: {int(captura.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
              f"{int(captura.get(cv2.CAP_PROP_FRAME_HEIGHT))}", flush=True)
    # Video gravado e reproduzido no ritmo real, como uma camera ao vivo: se o processamento atrasa,
    # quadros sao pulados (sem isso o video "andaria" na velocidade do processador)
    fps_video = (captura.get(cv2.CAP_PROP_FPS) or 30.0) if video else 0.0
    inicio, indice = time.time(), 0
    try:
        while True:
            if video:
                alvo = int((time.time() - inicio) * fps_video)
                while indice < alvo:  # descarta os quadros que ja "passaram"
                    if not captura.grab():
                        break
                    indice += 1
            ok, quadro = captura.read()
            if not ok:
                if video:  # recomeca o video
                    captura.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    inicio, indice = time.time(), 0
                    continue
                raise SystemExit("A camera parou de enviar imagens.")
            if video:
                indice += 1
                espera = inicio + indice / fps_video - time.time()
                if espera > 0:
                    time.sleep(espera)
            yield quadro
    finally:
        captura.release()


def desenhar_rosto(quadro: np.ndarray, rosto, rotulo: str, cor: Tuple[int, int, int]) -> None:
    x1, y1, x2, y2 = rosto.bbox.astype(int)
    cv2.rectangle(quadro, (x1, y1), (x2, y2), cor, 2)
    cv2.putText(quadro, sem_acentos(rotulo), (x1, max(y1 - 8, 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, cor, 2)


def escrever_status(quadro: np.ndarray, texto: str) -> None:
    cv2.putText(quadro, sem_acentos(texto), (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
    cv2.putText(quadro, sem_acentos(texto), (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)


def mostrar(nome: str, quadro: np.ndarray, largura_max: int = 1280) -> None:
    """Mostra o quadro na janela reduzido para caber na tela (a captura em Full HD passa do tamanho da tela);
    so a exibicao e reduzida: o reconhecimento usa o quadro inteiro."""
    if quadro.shape[1] > largura_max:
        escala = largura_max / quadro.shape[1]
        quadro = cv2.resize(quadro, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)
    cv2.imshow(nome, quadro)


def janela_fechada(nome: str) -> bool:
    """O usuario fechou a janela no X (sem isto, o proximo imshow a reabre e ela nunca fecha)."""
    try:
        return cv2.getWindowProperty(nome, cv2.WND_PROP_VISIBLE) < 1
    except cv2.error:
        return True


def desenhar_pessoa(quadro: np.ndarray, caixa, rotulo: str, cor: Tuple[int, int, int]) -> None:
    x1, y1, x2, y2 = (int(v) for v in caixa)
    cv2.rectangle(quadro, (x1, y1), (x2, y2), cor, 1)
    cv2.putText(quadro, sem_acentos(rotulo), (x1 + 4, y2 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor, 2)
