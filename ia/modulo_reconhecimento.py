"""
LivePresenceAI - Modulo de reconhecimento da sala (substitui o simulador).

Fica ligado na sala da turma: espera o professor abrir a chamada no app, carrega os embeddings
dos alunos cadastrados e, a cada quadro da camera, identifica os rostos e envia o reconhecimento
ao backend pelo mesmo contrato do simulador (POST /sessoes/{id}/reconhecimento).

Por padrao usa YOLOv8 + DeepSORT (rastreamento.py): cada pessoa vira uma trilha, o rosto e reconhecido
uma vez por trilha e o aluno continua sendo visto enquanto a trilha existir, mesmo sem o rosto visivel.

A confianca enviada e a similaridade do rosto com o cadastro do aluno; o backend aplica a RN-04
(descarta abaixo de CONFIANCA_MINIMA) e todas as regras de permanencia. Este modulo so limita a
frequencia de envio por aluno.

Uso:
  python modulo_reconhecimento.py --sala 1                         # computador da sala (forma normal)
  python modulo_reconhecimento.py --listar-cameras                 # indices de camera disponiveis
  python modulo_reconhecimento.py --testar-camera 0                # janela de teste da camera ('q' fecha)
  python modulo_reconhecimento.py --turma 1                        # so a turma 1 (experimentos)
  python modulo_reconhecimento.py --turma 1 --camera 1 --intervalo 3
  python modulo_reconhecimento.py --turma 1 --sem-rastreamento      # so rostos (modo da etapa 1)
  python modulo_reconhecimento.py --turma 1 --imagem foto.jpg      # teste sem camera
  python modulo_reconhecimento.py --turma 1 --medir e5.csv --duracao 300   # experimento E5 (desempenho)

A prova de vida (anti-spoofing MiniFASNet do InsightFace) recusa fotos e telas mostradas a camera: um rosto
recusado nao e reconhecido e nao identifica nenhuma trilha.
"""
import argparse
import contextlib
import csv
import json
import os
import subprocess
import threading
import time
from datetime import datetime
from typing import Optional

import cv2
import requests

from comum import (LIMIAR_PROVA_VIDA, PROVA_VIDA_DISPENSAR_ABAIXO_PX, Galeria, Reconhecedor, abrir_fonte, api,
                   desenhar_pessoa, desenhar_rosto, escrever_status, janela_fechada, mostrar)

ESPERA_SEM_CHAMADA = 5   # segundos entre consultas enquanto nao ha chamada aberta
ATUALIZAR_GALERIA = 30   # segundos: recarrega cadastros feitos durante a aula
JANELA = "LivePresenceAI - reconhecimento"

VERDE, LARANJA, AZUL, CINZA, VERMELHO = (0, 200, 0), (0, 140, 255), (255, 140, 0), (160, 160, 160), (0, 0, 255)


class Medidor:
    """
    Experimento E5: tempo de cada etapa por quadro, latencia da captura ao registro no backend e uso de CPU,
    memoria e GPU (amostras a cada 2 s). O CSV e resumido por "experimentos.py desempenho".
    """

    CAMPOS = ["tipo", "momento", "modo", "provedor", "captura_ms", "rastreamento_ms", "deteccao_ms", "prova_vida_ms",
              "reconhecimento_ms", "processamento_ms", "rostos", "trilhas", "latencia_ms", "http_ms",
              "cpu_processo_pct", "cpu_sistema_pct", "memoria_mb", "gpu_pct", "gpu_memoria_mb"]

    def __init__(self, caminho: str, modo: str, provedor: str):
        os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
        self.arquivo = open(caminho, "w", newline="", encoding="utf-8")
        self.escritor = csv.DictWriter(self.arquivo, fieldnames=self.CAMPOS, delimiter=";")
        self.escritor.writeheader()
        self.trava = threading.Lock()
        self.modo, self.provedor = modo, provedor
        self.etapas = {}
        self.quadro_em = 0.0
        self.rostos = self.trilhas = 0
        self.inicio = None
        self.parar = threading.Event()
        threading.Thread(target=self._recursos, daemon=True).start()

    def _gravar(self, linha: dict) -> None:
        with self.trava:
            if not self.arquivo.closed:
                self.escritor.writerow(linha)

    @contextlib.contextmanager
    def etapa(self, nome: str):
        inicio = time.perf_counter()
        try:
            yield
        finally:
            self.etapas[nome] = self.etapas.get(nome, 0.0) + (time.perf_counter() - inicio) * 1000

    def novo_quadro(self, espera_ms: float) -> None:
        self.inicio = self.inicio or time.time()
        self.quadro_em = time.time()
        self.etapas = {"captura": espera_ms}
        self.rostos = self.trilhas = 0

    def fim_quadro(self) -> None:
        self._gravar({"tipo": "quadro", "momento": f"{self.quadro_em:.3f}", "modo": self.modo, "provedor": self.provedor,
                      "captura_ms": f"{self.etapas.get('captura', 0):.2f}",
                      "rastreamento_ms": f"{self.etapas.get('rastreamento', 0):.2f}",
                      "deteccao_ms": f"{self.etapas.get('deteccao', 0):.2f}",
                      "prova_vida_ms": f"{self.etapas.get('prova_vida', 0):.2f}",
                      "reconhecimento_ms": f"{self.etapas.get('reconhecimento', 0):.2f}",
                      "processamento_ms": f"{(time.time() - self.quadro_em) * 1000:.2f}",
                      "rostos": self.rostos, "trilhas": self.trilhas})

    def envio(self, http_ms: float) -> None:
        self._gravar({"tipo": "envio", "momento": f"{time.time():.3f}",
                      "latencia_ms": f"{(time.time() - self.quadro_em) * 1000:.2f}", "http_ms": f"{http_ms:.2f}"})

    def _recursos(self) -> None:
        import psutil  # instalado com o ultralytics

        processo = psutil.Process()
        processo.cpu_percent(None)
        psutil.cpu_percent(None)
        nucleos = psutil.cpu_count() or 1
        while not self.parar.wait(2.0):
            linha = {"tipo": "recurso", "momento": f"{time.time():.3f}",
                     "cpu_processo_pct": f"{processo.cpu_percent(None) / nucleos:.1f}",
                     "cpu_sistema_pct": f"{psutil.cpu_percent(None):.1f}",
                     "memoria_mb": f"{processo.memory_info().rss / 2**20:.0f}"}
            try:  # GPU NVIDIA, se houver
                saida = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                                        "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5,
                                       creationflags=0x08000000 if os.name == "nt" else 0)
                gpu, memoria = saida.stdout.strip().splitlines()[0].split(",")
                linha.update(gpu_pct=gpu.strip(), gpu_memoria_mb=memoria.strip())
            except (OSError, ValueError, IndexError, subprocess.SubprocessError):
                pass
            if self.inicio:
                self._gravar(linha)

    def fechar(self) -> None:
        self.parar.set()
        with self.trava:
            self.arquivo.close()


MEDIDOR: Optional[Medidor] = None


def etapa(nome: str):
    return MEDIDOR.etapa(nome) if MEDIDOR else contextlib.nullcontext()


def log(texto: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {texto}", flush=True)


class Estado:
    """Chamada aberta da sala (ou da turma) e galeria de embeddings, consultadas no backend."""

    def __init__(self, sala_id: Optional[int] = None, turma_id: Optional[int] = None):
        self.sala_id, self.turma_id = sala_id, turma_id
        self.rotulo = f"sala {sala_id}" if sala_id is not None else f"turma {turma_id}"
        self.caminho = (f"/ia/salas/{sala_id}/sessao-ativa" if sala_id is not None
                        else f"/ia/turmas/{turma_id}/sessao-ativa")
        self.sessao_id = None
        self.confianca_minima = 0.6
        self.galeria = Galeria([])
        self.consultado_em = 0.0

    def atualizar(self, forcar: bool = False) -> None:
        espera = ATUALIZAR_GALERIA if self.sessao_id else ESPERA_SEM_CHAMADA
        if not forcar and time.time() - self.consultado_em < espera:
            return
        try:
            r = api("GET", self.caminho)
        except requests.RequestException:
            log("Backend fora do ar; tentando de novo...")
            return
        if r.status_code != 200:
            raise SystemExit(f"Erro {r.status_code} ao consultar a turma: {r.text}")
        dados = r.json()
        primeira_consulta = self.consultado_em == 0.0
        self.consultado_em = time.time()
        if primeira_consulta and not dados["sessao_id"]:
            log(f"Nenhuma chamada aberta ({self.rotulo}); aguardando o professor.")
        if dados["sessao_id"] != self.sessao_id:
            if dados["sessao_id"]:
                log(f"Chamada aberta: sessao #{dados['sessao_id']} "
                    f"({len(dados['alunos'])} aluno(s) com cadastro facial)")
            else:
                log("Chamada encerrada; aguardando a proxima.")
        self.sessao_id = dados["sessao_id"]
        self.confianca_minima = dados["confianca_minima"]
        self.galeria = Galeria(dados["alunos"])


def enviar(estado: Estado, aluno_id: int, similaridade: float, origem: str) -> None:
    nome = estado.galeria.nomes[aluno_id]
    try:
        inicio = time.perf_counter()
        r = api("POST", f"/sessoes/{estado.sessao_id}/reconhecimento",
                json={"aluno_id": aluno_id, "confianca": round(max(0.0, min(1.0, similaridade)), 4)})
        if MEDIDOR and r.status_code == 200:
            MEDIDOR.envio((time.perf_counter() - inicio) * 1000)
    except requests.RequestException:
        log(f"{nome}: backend fora do ar, envio perdido")
        return
    if r.status_code == 404 and "Sess" in r.text:  # "Sessão não encontrada ou já encerrada"
        estado.atualizar(forcar=True)  # chamada encerrada pelo professor
        return
    if r.status_code != 200:
        log(f"{nome}: erro {r.status_code} {r.text}")
        return
    resultado = "registrado" if r.json().get("registrado") else "descartado (RN-04)"
    log(f"{nome:<25} similaridade {similaridade:.2f} ({origem}) -> {resultado}")


class Envios:
    """Limita os envios a um a cada --intervalo segundos por aluno."""

    def __init__(self, estado: Estado, intervalo: float):
        self.estado, self.intervalo, self.ultimo = estado, intervalo, {}

    def __call__(self, aluno_id: int, similaridade: float, origem: str) -> None:
        if time.time() - self.ultimo.get(aluno_id, 0) >= self.intervalo:
            self.ultimo[aluno_id] = time.time()
            enviar(self.estado, aluno_id, similaridade, origem)


_ultimo_aviso_vida = 0.0


def prova_de_vida(quadro, reconhecedor: Reconhecedor, rosto) -> Optional[bool]:
    """
    True (pessoa real), False (recusado: possivel foto ou tela) ou None (inconclusivo: rosto cortado na borda).
    Recusado ou inconclusivo e marcado em vermelho e nao e reconhecido.
    """
    global _ultimo_aviso_vida
    if PROVA_VIDA_DISPENSAR_ABAIXO_PX and rosto.bbox[2] - rosto.bbox[0] < PROVA_VIDA_DISPENSAR_ABAIXO_PX:
        return True  # rosto pequeno: prova de vida dispensada por configuracao
    with etapa("prova_vida"):
        vivo = reconhecedor.vivo(quadro, rosto)
    if vivo:
        return True
    escore = reconhecedor.escore_vida(rosto)
    rotulo = "prova de vida: inconclusiva" if vivo is None else f"prova de vida: recusado {escore:.2f}"
    desenhar_rosto(quadro, rosto, rotulo, VERMELHO)
    if vivo is False and time.time() - _ultimo_aviso_vida >= 10:  # evita repetir o aviso a cada quadro
        _ultimo_aviso_vida = time.time()
        log(f"Rosto recusado na prova de vida (escore {escore:.2f}): possivel foto ou tela")
    return vivo


def processar_sem_rastreamento(quadro, reconhecedor: Reconhecedor, estado: Estado, envios: Envios) -> None:
    """Etapa 1: cada rosto visivel e reconhecido em todo quadro; sem rosto visivel, nada e enviado."""
    with etapa("deteccao"):  # neste modo, deteccao e reconhecimento saem juntos do InsightFace
        rostos = reconhecedor.rostos(quadro)
    if MEDIDOR:
        MEDIDOR.rostos = len(rostos)
    for rosto in rostos:
        if not prova_de_vida(quadro, reconhecedor, rosto):
            continue
        aluno_id, similaridade = estado.galeria.identificar(rosto.normed_embedding)
        aceito = aluno_id is not None and similaridade >= estado.confianca_minima
        if aceito:
            envios(aluno_id, similaridade, "rosto")
            rotulo = f"{estado.galeria.nomes[aluno_id]} {similaridade:.2f}"
        else:
            # Rosto nao cadastrado ou parecido demais com ninguem: nada e enviado
            rotulo = f"desconhecido {similaridade:.2f}"
        desenhar_rosto(quadro, rosto, rotulo, VERDE if aceito else LARANJA)


def processar_com_rastreamento(quadro, reconhecedor: Reconhecedor, rastreador, identidades,
                               estado: Estado, envios: Envios) -> None:
    """
    YOLOv8 + DeepSORT: o rosto e reconhecido uma vez por trilha (e reconferido a cada REVERIFICAR s);
    enquanto a trilha existir, o aluno continua sendo enviado, mesmo sem o rosto visivel.
    """
    from rastreamento import trilha_do_rosto

    agora = time.time()
    antes = {t: i.aluno_id for t, i in identidades.por_trilha.items()}
    with etapa("rastreamento"):
        trilhas = rastreador.atualizar(quadro)
    with etapa("deteccao"):
        rostos = reconhecedor.detectar(quadro)
    if MEDIDOR:
        MEDIDOR.rostos, MEDIDOR.trilhas = len(rostos), len(trilhas)
    for rosto in rostos:
        trilha = trilha_do_rosto(rosto, trilhas)
        if trilha is not None and not identidades.precisa_reconhecer(trilha.id, agora):
            continue  # trilha ja identificada recentemente: dispensa o reconhecimento
        vivo = prova_de_vida(quadro, reconhecedor, rosto)
        if not vivo:
            # Foto/tela: nao identifica nenhuma trilha; numa trilha ja identificada, a recusa conta como falha,
            # e depois de FALHAS_MAXIMAS seguidas a trilha perde a identidade (antes ela continuava valendo)
            if vivo is False and trilha is not None:
                identidades.registrar(trilha.id, None, 0.0, estado.confianca_minima, agora)
            continue
        with etapa("reconhecimento"):
            aluno_id, similaridade = estado.galeria.identificar(reconhecedor.extrair(quadro, rosto))
        aceito = aluno_id is not None and similaridade >= estado.confianca_minima
        if trilha is not None:
            identidades.registrar(trilha.id, aluno_id, similaridade, estado.confianca_minima, agora)
        elif aceito:
            envios(aluno_id, similaridade, "rosto sem pessoa detectada")
        rotulo = f"{estado.galeria.nomes[aluno_id]} {similaridade:.2f}" if aceito else f"desconhecido {similaridade:.2f}"
        desenhar_rosto(quadro, rosto, rotulo, VERDE if aceito else LARANJA)

    vistos = {t.id: identidade for t, identidade in identidades.vistos(trilhas, agora)}
    depois = {t: i.aluno_id for t, i in identidades.por_trilha.items()}
    for trilha_id in antes.keys() | depois.keys():
        if antes.get(trilha_id) != depois.get(trilha_id):
            if trilha_id in depois:
                log(f"trilha {trilha_id} identificada: {estado.galeria.nomes.get(depois[trilha_id], '?')}")
            else:
                log(f"trilha {trilha_id} perdeu a identidade ({estado.galeria.nomes.get(antes[trilha_id], '?')})")
    for trilha in trilhas:
        identidade = vistos.get(trilha.id)
        if identidade:
            envios(identidade.aluno_id, identidade.similaridade, f"trilha {trilha.id}")
            rotulo = f"#{trilha.id} {estado.galeria.nomes.get(identidade.aluno_id, '?')}"
        else:
            rotulo = f"#{trilha.id}"
        desenhar_pessoa(quadro, trilha.caixa, rotulo, AZUL if identidade else CINZA)


def executar(args) -> None:
    log("Carregando modelos de reconhecimento...")
    reconhecedor = Reconhecedor(prova_de_vida=not args.sem_prova_de_vida)
    gpu = reconhecedor.provedor == "CUDAExecutionProvider"
    rastreador = identidades = None
    if not args.sem_rastreamento:
        from rastreamento import Identidades, RastreadorPessoas
        rastreador, identidades = RastreadorPessoas(gpu=gpu), Identidades()
    modo = "rosto apenas" if args.sem_rastreamento else "YOLOv8 + DeepSORT"
    vida = "sem prova de vida" if args.sem_prova_de_vida else f"prova de vida >= {LIMIAR_PROVA_VIDA}"
    estado = Estado(sala_id=args.sala, turma_id=args.turma)
    log(f"Modelos prontos ({reconhecedor.provedor}, {modo}, {vida}). {estado.rotulo.capitalize()}; "
        "'q' na janela encerra.")

    envios = Envios(estado, args.intervalo)
    sessao_anterior = None
    inicio_fps, quadros, fps = time.time(), 0, 0.0
    global MEDIDOR
    if args.medir:
        MEDIDOR = Medidor(args.medir, modo, reconhecedor.provedor)
        log(f"Medindo o desempenho em {args.medir} enquanto houver chamada aberta"
            + (f" (por {args.duracao:.0f} s)" if args.duracao else "") + ".")
    fim_espera = time.perf_counter()

    for quadro in abrir_fonte(args.camera, args.imagem, args.video):
        espera_ms = (time.perf_counter() - fim_espera) * 1000
        estado.atualizar()
        if estado.sessao_id != sessao_anterior:
            # Nova chamada (ou fim dela): identidades e limites de envio recomecam do zero
            sessao_anterior = estado.sessao_id
            envios.ultimo.clear()
            if identidades:
                identidades.limpar()

        if estado.sessao_id:
            if MEDIDOR:
                if args.duracao and MEDIDOR.inicio and time.time() - MEDIDOR.inicio >= args.duracao:
                    log("Medicao concluida.")
                    break
                MEDIDOR.novo_quadro(espera_ms)
            if rastreador:
                processar_com_rastreamento(quadro, reconhecedor, rastreador, identidades, estado, envios)
            else:
                processar_sem_rastreamento(quadro, reconhecedor, estado, envios)
            if MEDIDOR:
                MEDIDOR.fim_quadro()
            status = f"Sessao #{estado.sessao_id} | {len(estado.galeria)} cadastrados | {fps:.1f} q/s"
        else:
            status = f"{estado.rotulo.capitalize()}: aguardando o professor abrir a chamada"

        quadros += 1
        if time.time() - inicio_fps >= 2:
            fps, quadros, inicio_fps = quadros / (time.time() - inicio_fps), 0, time.time()

        if not args.sem_janela:
            escrever_status(quadro, status)
            mostrar(JANELA, quadro)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            if janela_fechada(JANELA):
                # Fechar o video no X nao desliga o reconhecimento da sala (isso e no painel ou com 'q')
                args.sem_janela = True
                cv2.destroyAllWindows()
                log("Janela de video fechada; o reconhecimento continua.")
        fim_espera = time.perf_counter()
    cv2.destroyAllWindows()
    if MEDIDOR:
        MEDIDOR.fechar()
        log(f"Resumo: python experimentos.py desempenho {args.medir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Modulo de reconhecimento facial da sala (LivePresenceAI)")
    alvo = parser.add_mutually_exclusive_group(required=True)
    alvo.add_argument("--sala", type=int, help="sala deste computador: atende a chamada aberta nela")
    alvo.add_argument("--turma", type=int, help="acompanha so a chamada desta turma (experimentos)")
    alvo.add_argument("--listar-cameras", action="store_true", help="mostra os indices de camera disponiveis")
    alvo.add_argument("--testar-camera", type=int, metavar="INDICE", help="abre a camera numa janela ('q' fecha)")
    parser.add_argument("--camera", type=int, default=0, help="indice da camera (padrao 0)")
    parser.add_argument("--video", help="usa um arquivo de video em vez da camera (teste)")
    parser.add_argument("--imagem", help="usa uma imagem fixa em vez da camera (teste)")
    parser.add_argument("--intervalo", type=float, default=3.0,
                        help="segundos minimos entre dois envios do mesmo aluno (padrao 3)")
    parser.add_argument("--sem-janela", action="store_true", help="nao abre a janela de video")
    parser.add_argument("--sem-rastreamento", action="store_true",
                        help="desliga YOLOv8 + DeepSORT: reconhece so rostos visiveis (modo da etapa 1)")
    parser.add_argument("--medir", metavar="CSV", help="experimento E5: grava tempos, latencia e uso de CPU/GPU")
    parser.add_argument("--duracao", type=float, help="com --medir: encerra apos N segundos de chamada aberta")
    parser.add_argument("--sem-prova-de-vida", action="store_true",
                        help="desliga a prova de vida (somente para experimentos)")
    args = parser.parse_args()
    if args.listar_cameras:
        from comum import listar_cameras
        print(json.dumps(listar_cameras()))
    elif args.testar_camera is not None:
        testar_camera(args.testar_camera)
    else:
        executar(args)


def testar_camera(indice: int) -> None:
    """Janela com a imagem da camera, para conferir enquadramento e foco ao instalar a sala."""
    janela = "LivePresenceAI - teste da camera"
    for quadro in abrir_fonte(indice, None, None):
        escrever_status(quadro, f"Camera {indice} - enquadre a sala; 'q' ou o X fecham")
        mostrar(janela, quadro)
        if cv2.waitKey(1) & 0xFF in (ord("q"), 27) or janela_fechada(janela):
            break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
