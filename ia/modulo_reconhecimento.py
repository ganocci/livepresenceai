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

A prova de vida (anti-spoofing MiniFASNet do InsightFace) recusa fotos e telas mostradas a camera: um rosto
recusado nao e reconhecido e nao identifica nenhuma trilha.
"""
import argparse
import json
import time
from datetime import datetime
from typing import Optional

import cv2
import requests

from comum import (LIMIAR_PROVA_VIDA, Galeria, Reconhecedor, abrir_fonte, api, desenhar_pessoa, desenhar_rosto,
                   escrever_status)

ESPERA_SEM_CHAMADA = 5   # segundos entre consultas enquanto nao ha chamada aberta
ATUALIZAR_GALERIA = 30   # segundos: recarrega cadastros feitos durante a aula

VERDE, LARANJA, AZUL, CINZA, VERMELHO = (0, 200, 0), (0, 140, 255), (255, 140, 0), (160, 160, 160), (0, 0, 255)


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
        r = api("POST", f"/sessoes/{estado.sessao_id}/reconhecimento",
                json={"aluno_id": aluno_id, "confianca": round(max(0.0, min(1.0, similaridade)), 4)})
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


def passou_prova_de_vida(quadro, reconhecedor: Reconhecedor, rosto) -> bool:
    """Rosto recusado (foto/tela) ou inconclusivo (cortado na borda) e marcado em vermelho e ignorado."""
    global _ultimo_aviso_vida
    vivo = reconhecedor.vivo(quadro, rosto)
    if vivo:
        return True
    escore = reconhecedor.escore_vida(rosto)
    rotulo = "prova de vida: inconclusiva" if vivo is None else f"prova de vida: recusado {escore:.2f}"
    desenhar_rosto(quadro, rosto, rotulo, VERMELHO)
    if vivo is False and time.time() - _ultimo_aviso_vida >= 10:  # evita repetir o aviso a cada quadro
        _ultimo_aviso_vida = time.time()
        log(f"Rosto recusado na prova de vida (escore {escore:.2f}): possivel foto ou tela")
    return False


def processar_sem_rastreamento(quadro, reconhecedor: Reconhecedor, estado: Estado, envios: Envios) -> None:
    """Etapa 1: cada rosto visivel e reconhecido em todo quadro; sem rosto visivel, nada e enviado."""
    for rosto in reconhecedor.rostos(quadro):
        if not passou_prova_de_vida(quadro, reconhecedor, rosto):
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
    trilhas = rastreador.atualizar(quadro)
    for rosto in reconhecedor.detectar(quadro):
        trilha = trilha_do_rosto(rosto, trilhas)
        if trilha is not None and not identidades.precisa_reconhecer(trilha.id, agora):
            continue  # trilha ja identificada recentemente: dispensa o reconhecimento
        if not passou_prova_de_vida(quadro, reconhecedor, rosto):
            continue  # foto/tela: nao identifica nem renova a identidade de nenhuma trilha
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

    for quadro in abrir_fonte(args.camera, args.imagem, args.video):
        estado.atualizar()
        if estado.sessao_id != sessao_anterior:
            # Nova chamada (ou fim dela): identidades e limites de envio recomecam do zero
            sessao_anterior = estado.sessao_id
            envios.ultimo.clear()
            if identidades:
                identidades.limpar()

        if estado.sessao_id:
            if rastreador:
                processar_com_rastreamento(quadro, reconhecedor, rastreador, identidades, estado, envios)
            else:
                processar_sem_rastreamento(quadro, reconhecedor, estado, envios)
            status = f"Sessao #{estado.sessao_id} | {len(estado.galeria)} cadastrados | {fps:.1f} q/s"
        else:
            status = f"{estado.rotulo.capitalize()}: aguardando o professor abrir a chamada"

        quadros += 1
        if time.time() - inicio_fps >= 2:
            fps, quadros, inicio_fps = quadros / (time.time() - inicio_fps), 0, time.time()

        if not args.sem_janela:
            escrever_status(quadro, status)
            cv2.imshow("LivePresenceAI - reconhecimento", quadro)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    cv2.destroyAllWindows()


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
    for quadro in abrir_fonte(indice, None, None):
        escrever_status(quadro, f"Camera {indice} - enquadre a sala; 'q' fecha")
        cv2.imshow("LivePresenceAI - teste da camera", quadro)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
