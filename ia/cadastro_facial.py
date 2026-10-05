"""
LivePresenceAI - Cadastro facial de alunos.

Captura algumas amostras do rosto do aluno, calcula a media dos embeddings e envia ao backend.
Somente o vetor de caracteristicas e gravado; a foto nunca sai deste computador nem e salva.

Uso:
  python cadastro_facial.py --turma 1                 # lista os alunos e quem ja tem cadastro
  python cadastro_facial.py --aluno 3                 # cadastra pela camera (pede o consentimento)
  python cadastro_facial.py --aluno 3 --imagem f.jpg  # cadastra a partir de uma foto
  python cadastro_facial.py --remover 3               # exclui o cadastro facial (LGPD)
"""
import argparse
import sys
import time

import cv2
import numpy as np

from comum import Reconhecedor, abrir_fonte, api, desenhar_rosto, escrever_status, ler_imagem

AMOSTRAS = 10
INTERVALO_AMOSTRAS = 0.3  # segundos entre amostras, para variar um pouco a pose
SCORE_MINIMO = 0.7        # confianca minima da deteccao do rosto
LADO_MINIMO = 80          # rosto menor que isso (px) fica com pouco detalhe

TERMO = (
    "O aluno foi informado de que:\n"
    "  - o rosto sera usado apenas para registrar a presenca nas aulas;\n"
    "  - somente um vetor numerico e guardado, nunca a foto;\n"
    "  - pode pedir a exclusao do cadastro a qualquer momento;\n"
    "  - pode optar pela chamada sem reconhecimento facial.\n"
)


def listar(turma_id: int) -> None:
    r = api("GET", f"/ia/turmas/{turma_id}/alunos")
    if r.status_code != 200:
        sys.exit(f"Erro {r.status_code}: {r.text}")
    for a in r.json():
        print(f"  {a['aluno_id']:>4}  {a['nome']:<30} {'cadastrado' if a['cadastrado'] else '-'}")


def amostra_valida(rostos: list) -> str:
    """Mensagem do problema, ou '' se o quadro serve como amostra."""
    if not rostos:
        return "Nenhum rosto encontrado"
    if len(rostos) > 1:
        return "Mais de um rosto: deixe so o aluno na imagem"
    rosto = rostos[0]
    x1, y1, x2, y2 = rosto.bbox
    if rosto.det_score < SCORE_MINIMO or min(x2 - x1, y2 - y1) < LADO_MINIMO:
        return "Aproxime-se da camera e olhe de frente"
    return ""


def capturar(reconhecedor: Reconhecedor, camera: int) -> list:
    print(f"Olhe para a camera. Serao coletadas {AMOSTRAS} amostras (ESC cancela).")
    amostras, ultima = [], 0.0
    for quadro in abrir_fonte(camera, None, None):
        rostos = reconhecedor.rostos(quadro)
        problema = amostra_valida(rostos)
        if not problema and time.time() - ultima >= INTERVALO_AMOSTRAS:
            amostras.append(rostos[0].normed_embedding)
            ultima = time.time()
        for rosto in rostos:
            desenhar_rosto(quadro, rosto, "", (0, 200, 0) if not problema else (0, 0, 255))
        escrever_status(quadro, problema or f"Amostras: {len(amostras)}/{AMOSTRAS}")
        cv2.imshow("LivePresenceAI - cadastro facial", quadro)
        if cv2.waitKey(1) & 0xFF == 27:
            break
        if len(amostras) >= AMOSTRAS:
            break
    cv2.destroyAllWindows()
    return amostras


def cadastrar(aluno_id: int, camera: int, imagem: str, consentimento: bool) -> None:
    print(TERMO)
    if not consentimento:
        resposta = input("O aluno concorda com o cadastro facial? [s/N] ").strip().lower()
        if resposta not in ("s", "sim"):
            sys.exit("Cadastro cancelado: sem consentimento.")

    reconhecedor = Reconhecedor()
    if imagem:
        quadro = ler_imagem(imagem)
        if quadro is None:
            sys.exit(f"Nao foi possivel ler a imagem {imagem}")
        rostos = reconhecedor.rostos(quadro)
        problema = amostra_valida(rostos)
        if problema:
            sys.exit(f"Imagem recusada: {problema}")
        amostras = [rostos[0].normed_embedding]
    else:
        amostras = capturar(reconhecedor, camera)
        if len(amostras) < AMOSTRAS:
            sys.exit("Cadastro cancelado antes de completar as amostras.")

    media = np.mean(amostras, axis=0)
    media /= np.linalg.norm(media)
    # Amostras muito diferentes da media indicam troca de pessoa ou imagem ruim
    consistencia = min(float(a @ media) for a in amostras)
    if consistencia < 0.5:
        sys.exit(f"Amostras inconsistentes (similaridade minima {consistencia:.2f}); repita o cadastro.")

    r = api("PUT", f"/ia/alunos/{aluno_id}/embedding",
            json={"embedding": media.tolist(), "consentimento": True})
    if r.status_code != 200:
        sys.exit(f"Erro {r.status_code}: {r.text}")
    print(f"Cadastro facial de {r.json()['nome']} concluido "
          f"({len(amostras)} amostra(s), consistencia {consistencia:.2f}).")


def remover(aluno_id: int) -> None:
    r = api("DELETE", f"/ia/alunos/{aluno_id}/embedding")
    if r.status_code != 200:
        sys.exit(f"Erro {r.status_code}: {r.text}")
    print(f"Cadastro facial de {r.json()['nome']} excluido.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cadastro facial de alunos (LivePresenceAI)")
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--turma", type=int, help="lista os alunos da turma")
    grupo.add_argument("--aluno", type=int, help="cadastra o rosto do aluno")
    grupo.add_argument("--remover", type=int, metavar="ALUNO", help="exclui o cadastro facial do aluno")
    parser.add_argument("--camera", type=int, default=0, help="indice da camera (padrao 0)")
    parser.add_argument("--imagem", help="usa uma foto em vez da camera")
    parser.add_argument("--consentimento-registrado", action="store_true", dest="consentimento",
                        help="o consentimento ja foi colhido por escrito (nao pergunta)")
    args = parser.parse_args()

    if args.turma is not None:
        listar(args.turma)
    elif args.remover is not None:
        remover(args.remover)
    else:
        cadastrar(args.aluno, args.camera, args.imagem, args.consentimento)


if __name__ == "__main__":
    main()
