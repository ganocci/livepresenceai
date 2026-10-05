"""
LivePresenceAI - Cadastro facial pelo app do professor.

O app envia algumas fotos do aluno tiradas com o celular; aqui elas viram o vetor de caracteristicas
(embedding ArcFace de 512 posicoes, normalizado) com o mesmo modelo usado pelo modulo de IA da sala
(InsightFace buffalo_l). As fotos sao processadas so em memoria e descartadas: nada e gravado em disco.
"""
import os
import threading
from typing import List, Tuple

import cv2
import numpy as np

MODELO = os.getenv("MODELO_INSIGHTFACE", "buffalo_l")
FOTOS_MINIMAS, FOTOS_MAXIMAS = 3, 5
TAMANHO_MAXIMO_FOTO = 8 * 1024 * 1024  # bytes
SCORE_MINIMO = 0.7          # confianca minima da deteccao do rosto
LADO_MINIMO = 80            # px: rosto menor que isso tem pouco detalhe
CONSISTENCIA_MINIMA = 0.5   # similaridade minima de cada foto com a media (mesma pessoa)

_modelo = None
_trava = threading.Lock()


class FotoRecusada(ValueError):
    """Problema com as fotos, explicado em linguagem simples para o professor."""


def _carregar():
    """Carrega o InsightFace na primeira utilizacao (alguns segundos) e reaproveita depois."""
    global _modelo
    with _trava:
        if _modelo is None:
            from insightface.app import FaceAnalysis

            modelo = FaceAnalysis(name=MODELO, allowed_modules=["detection", "recognition"],
                                  providers=["CPUExecutionProvider"])
            modelo.prepare(ctx_id=-1, det_size=(640, 640))
            _modelo = modelo
    return _modelo


def _rosto_da_foto(modelo, conteudo: bytes, numero: int) -> np.ndarray:
    imagem = cv2.imdecode(np.frombuffer(conteudo, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagem is None:
        raise FotoRecusada(f"A foto {numero} não pôde ser lida.")
    rostos = modelo.get(imagem)
    if not rostos:
        raise FotoRecusada("Nenhum rosto encontrado. Enquadre o rosto do aluno na moldura.")
    if len(rostos) > 1:
        raise FotoRecusada("Há mais de um rosto na imagem. Deixe só o aluno no enquadramento.")
    rosto = rostos[0]
    x1, y1, x2, y2 = rosto.bbox
    if rosto.det_score < SCORE_MINIMO or min(x2 - x1, y2 - y1) < LADO_MINIMO:
        raise FotoRecusada("Rosto pequeno ou pouco nítido. Aproxime o celular e evite contraluz.")
    return rosto.normed_embedding


def gerar_vetor(fotos: List[bytes]) -> Tuple[List[float], float]:
    """Vetor medio normalizado das fotos e a consistencia (menor similaridade de uma foto com a media)."""
    if not FOTOS_MINIMAS <= len(fotos) <= FOTOS_MAXIMAS:
        raise FotoRecusada(f"Envie de {FOTOS_MINIMAS} a {FOTOS_MAXIMAS} fotos.")
    if any(len(f) > TAMANHO_MAXIMO_FOTO for f in fotos):
        raise FotoRecusada("Foto grande demais (máximo de 8 MB).")
    modelo = _carregar()
    vetores = [_rosto_da_foto(modelo, conteudo, i) for i, conteudo in enumerate(fotos, 1)]
    media = np.mean(vetores, axis=0)
    media /= np.linalg.norm(media)
    consistencia = min(float(v @ media) for v in vetores)
    if consistencia < CONSISTENCIA_MINIMA:
        raise FotoRecusada("As fotos parecem ser de pessoas diferentes ou estão tremidas. Tente de novo.")
    return media.tolist(), consistencia
