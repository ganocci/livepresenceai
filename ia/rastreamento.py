"""
LivePresenceAI - Modulo de IA: deteccao de pessoas (YOLOv8) e rastreamento (DeepSORT).

Cada pessoa na sala recebe um numero de trilha que se mantem entre os quadros. O rosto so precisa ser
reconhecido uma vez por trilha (e reconferido de tempos em tempos): enquanto a trilha existir, o aluno
continua sendo visto, mesmo de cabeca baixa, de lado ou de costas para a camera.
"""
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

MODELO_YOLO = os.getenv("MODELO_YOLO", "yolov8n.pt")
CONFIANCA_PESSOA = 0.4   # confianca minima da deteccao de pessoa (YOLOv8)
N_INIT = 3               # quadros seguidos para uma trilha ser confirmada (evita deteccoes espurias)
MAX_AGE = 30             # quadros que uma trilha sobrevive sem ser detectada (oclusoes curtas)
REVERIFICAR = 10.0       # segundos: o rosto da trilha e reconhecido de novo para confirmar a identidade
FALHAS_MAXIMAS = 3       # reconferencias seguidas sem reconhecer o rosto ate a trilha perder a identidade
ESQUECER = 60.0          # segundos sem ver a trilha para descartar a identidade associada

CLASSE_PESSOA = 0        # classe "person" do conjunto COCO usado pelo YOLOv8


@dataclass
class Trilha:
    id: str
    caixa: Tuple[float, float, float, float]  # x1, y1, x2, y2


@dataclass
class Identidade:
    aluno_id: int
    similaridade: float
    verificado_em: float
    visto_em: float
    falhas: int = 0  # reconferencias seguidas em que o rosto nao foi reconhecido


class RastreadorPessoas:
    def __init__(self, gpu: bool = False):
        from deep_sort_realtime.deepsort_tracker import DeepSort
        from ultralytics import YOLO

        self.yolo = YOLO(MODELO_YOLO)
        self.dispositivo = 0 if gpu else "cpu"
        self.deepsort = DeepSort(max_age=MAX_AGE, n_init=N_INIT, embedder="mobilenet",
                                 half=gpu, bgr=True, embedder_gpu=gpu)

    def atualizar(self, quadro: np.ndarray) -> List[Trilha]:
        """Trilhas confirmadas e vistas neste quadro."""
        resultado = self.yolo.predict(quadro, classes=[CLASSE_PESSOA], conf=CONFIANCA_PESSOA,
                                      device=self.dispositivo, verbose=False)[0]
        deteccoes = []
        for (x1, y1, x2, y2), conf in zip(resultado.boxes.xyxy.tolist(), resultado.boxes.conf.tolist()):
            deteccoes.append(([x1, y1, x2 - x1, y2 - y1], conf, "pessoa"))
        trilhas = self.deepsort.update_tracks(deteccoes, frame=quadro)
        return [Trilha(str(t.track_id), tuple(t.to_ltrb()))
                for t in trilhas if t.is_confirmed() and t.time_since_update == 0]


def trilha_do_rosto(rosto, trilhas: List[Trilha]) -> Optional[Trilha]:
    """Trilha (pessoa) que contem o centro do rosto; havendo mais de uma, a de menor area (mais proxima)."""
    x1, y1, x2, y2 = rosto.bbox
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    candidatas = [t for t in trilhas if t.caixa[0] <= cx <= t.caixa[2] and t.caixa[1] <= cy <= t.caixa[3]]
    if not candidatas:
        return None
    return min(candidatas, key=lambda t: (t.caixa[2] - t.caixa[0]) * (t.caixa[3] - t.caixa[1]))


class Identidades:
    """Associacao trilha -> aluno, com reverificacao periodica e um aluno por trilha."""

    def __init__(self):
        self.por_trilha: Dict[str, Identidade] = {}

    def precisa_reconhecer(self, trilha_id: str, agora: float) -> bool:
        identidade = self.por_trilha.get(trilha_id)
        return identidade is None or agora - identidade.verificado_em >= REVERIFICAR

    def registrar(self, trilha_id: str, aluno_id: Optional[int], similaridade: float,
                  limite: float, agora: float) -> None:
        atual = self.por_trilha.get(trilha_id)
        if aluno_id is None or similaridade < limite:
            # Rosto visivel mas nao reconhecido (cabeca baixa, de lado, imagem tremida): a trilha mantem
            # a identidade e tenta de novo depois; so a perde apos FALHAS_MAXIMAS tentativas seguidas.
            if atual:
                atual.falhas += 1
                atual.verificado_em = agora
                if atual.falhas >= FALHAS_MAXIMAS:
                    del self.por_trilha[trilha_id]
            return
        # Reconhecido (como o mesmo aluno ou como outro: o rastreador pode ter trocado as pessoas)
        # Um aluno so pode estar em uma trilha: fica a de maior similaridade
        for outra_id, outra in list(self.por_trilha.items()):
            if outra_id != trilha_id and outra.aluno_id == aluno_id:
                if outra.similaridade >= similaridade:
                    return
                del self.por_trilha[outra_id]
        self.por_trilha[trilha_id] = Identidade(aluno_id, similaridade, agora, agora)

    def vistos(self, trilhas: List[Trilha], agora: float) -> List[Tuple[Trilha, Identidade]]:
        """Trilhas deste quadro que ja tem aluno associado; descarta identidades antigas."""
        resultado = []
        for trilha in trilhas:
            identidade = self.por_trilha.get(trilha.id)
            if identidade:
                identidade.visto_em = agora
                resultado.append((trilha, identidade))
        for trilha_id, identidade in list(self.por_trilha.items()):
            if agora - identidade.visto_em > ESQUECER:
                del self.por_trilha[trilha_id]
        return resultado

    def limpar(self) -> None:
        self.por_trilha.clear()
