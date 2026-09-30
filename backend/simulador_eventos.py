"""
LivePresenceAI - Simulador de Eventos de Reconhecimento
Imita a camera/IA: cada aluno "chega" em um momento diferente e continua sendo
visto de tempos em tempos, como acontece com o reconhecimento real. Assim o
backend consegue calcular o tempo de permanencia e o percentual de presenca.

Tambem simula alunos que saem da sala (param de ser vistos), com ou sem retorno,
para demonstrar o desconto de tempo fora da sala e a regra de 40% (RN-03).

Uso (com o venv do backend ativo):
    python simulador_eventos.py ID_DA_SESSAO
    python simulador_eventos.py 3 --demo         (roteiro pronto para apresentacao)
    python simulador_eventos.py 3 --alunos 1,2,3 --intervalo 2 --chegada-max 15
    python simulador_eventos.py 3 --sai 4:40     (aluno 4 sai aos 40 s e nao volta)
    python simulador_eventos.py 3 --pausa 3:40-120   (aluno 3 fica fora de 40 s a 120 s)
    python simulador_eventos.py 3 --uma-vez      (cada aluno e enviado so uma vez)

O simulador se autentica com a chave do modulo de IA (cabecalho X-API-Key),
lida da variavel de ambiente CHAVE_MODULO_IA (mesmo padrao do backend).

Os tempos sao contados a partir do inicio do simulador. Uma ausencia so e
descontada pelo backend se for maior que LIMITE_AUSENCIA (60 s por padrao).

Pare com Ctrl+C. O ID_DA_SESSAO aparece no titulo da tela "Chamada" do app.
"""
import argparse
import os
import random
import sys
import time

import requests

BASE_URL = "http://127.0.0.1:8000"
# Chave do modulo de IA (RN-09); deve ser a mesma configurada no backend.
CHAVE_MODULO_IA = os.getenv("CHAVE_MODULO_IA", "livepresenceai-ia-dev")

# Roteiro do --demo, pensado para uma apresentacao de ~3 minutos:
#   alunos 1, 2 e 5 ficam a aula toda (presenca);
#   aluno 3 sai aos 40 s e volta aos 120 s (presenca, com percentual reduzido);
#   aluno 4 sai aos 40 s e nao volta (falta por ficar abaixo de 40%);
#   alunos fora da lista (ex.: 6) nunca aparecem (falta, nao detectado).
DEMO = {"alunos": "1,2,3,4,5", "chegada_max": 10.0, "sai": "4:40", "pausa": "3:40-120"}


def enviar(sessao_id: int, aluno_id: int) -> dict | None:
    confianca = round(random.uniform(0.70, 0.98), 2)
    try:
        resposta = requests.post(
            f"{BASE_URL}/sessoes/{sessao_id}/reconhecimento",
            json={"aluno_id": aluno_id, "confianca": confianca},
            headers={"X-API-Key": CHAVE_MODULO_IA},
            timeout=5,
        )
    except requests.RequestException as erro:
        print(f"  [erro] aluno {aluno_id}: {erro}")
        return None

    if resposta.status_code != 200:
        print(f"  [erro] aluno {aluno_id}: {resposta.status_code} {resposta.text}")
        return None
    return resposta.json()


def ler_saidas(texto: str) -> dict[int, float]:
    """'4:40,5:90' -> {4: 40.0, 5: 90.0} (aluno: segundo em que sai de vez)."""
    saidas = {}
    for item in filter(None, (p.strip() for p in texto.split(","))):
        aluno, segundo = item.split(":")
        saidas[int(aluno)] = float(segundo)
    return saidas


def ler_pausas(texto: str) -> dict[int, tuple[float, float]]:
    """'3:40-120' -> {3: (40.0, 120.0)} (aluno: intervalo em que fica fora da sala)."""
    pausas = {}
    for item in filter(None, (p.strip() for p in texto.split(","))):
        aluno, periodo = item.split(":")
        inicio, fim = periodo.split("-")
        pausas[int(aluno)] = (float(inicio), float(fim))
    return pausas


def fora_da_sala(aluno: int, decorrido: float, saidas: dict, pausas: dict) -> bool:
    if aluno in saidas and decorrido >= saidas[aluno]:
        return True
    if aluno in pausas:
        inicio, fim = pausas[aluno]
        return inicio <= decorrido < fim
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador de reconhecimento facial (modo demo)")
    parser.add_argument("sessao_id", type=int, help="ID da sessao aberta (mostrado no app)")
    parser.add_argument("--alunos", default="1,2,3,4,5", help="IDs dos alunos, separados por virgula")
    parser.add_argument("--intervalo", type=float, default=3.0, help="Segundos entre varreduras da camera")
    parser.add_argument("--chegada-max", type=float, default=20.0, help="Ate quantos segundos um aluno pode demorar a chegar")
    parser.add_argument("--duracao", type=float, default=0.0, help="Duracao total em segundos (0 = ate Ctrl+C)")
    parser.add_argument("--uma-vez", action="store_true", help="Envia cada aluno apenas uma vez")
    parser.add_argument("--sai", default="", help="Alunos que saem e nao voltam, ex.: 4:40,5:90 (aluno:segundo)")
    parser.add_argument("--pausa", default="", help="Alunos que saem e voltam, ex.: 3:40-120 (aluno:inicio-fim)")
    parser.add_argument("--demo", action="store_true", help="Roteiro pronto para apresentacao (ver DEMO no codigo)")
    args = parser.parse_args()

    if args.demo:
        args.alunos, args.chegada_max = DEMO["alunos"], DEMO["chegada_max"]
        args.sai, args.pausa = DEMO["sai"], DEMO["pausa"]

    try:
        alunos = [int(x) for x in args.alunos.split(",") if x.strip()]
        saidas = ler_saidas(args.sai)
        pausas = ler_pausas(args.pausa)
    except ValueError:
        print("Formato invalido. Exemplos: --alunos 1,2,3  --sai 4:40  --pausa 3:40-120")
        sys.exit(1)

    chegadas = {aluno: random.uniform(0, args.chegada_max) for aluno in alunos}
    ja_chegou = set()
    fora = set()  # alunos que estao fora da sala neste momento

    print(f"Simulando a sessao {args.sessao_id} com os alunos {alunos}.")
    print("Chegadas previstas (s): " + ", ".join(f"{a}={t:.0f}" for a, t in sorted(chegadas.items())))
    for aluno, segundo in sorted(saidas.items()):
        print(f"Aluno {aluno} sai aos {segundo:.0f} s e nao volta.")
    for aluno, (inicio, fim) in sorted(pausas.items()):
        print(f"Aluno {aluno} fica fora da sala de {inicio:.0f} s a {fim:.0f} s.")
    print("Pressione Ctrl+C para parar.\n")

    inicio = time.time()
    try:
        while True:
            decorrido = time.time() - inicio
            if args.duracao and decorrido > args.duracao:
                break

            for aluno, chegada in chegadas.items():
                if decorrido < chegada:
                    continue
                if args.uma_vez and aluno in ja_chegou:
                    continue

                if fora_da_sala(aluno, decorrido, saidas, pausas):
                    if aluno in ja_chegou and aluno not in fora:
                        fora.add(aluno)
                        print(f"[{decorrido:5.1f}s] aluno {aluno} saiu da sala")
                    continue
                if aluno in fora:
                    fora.discard(aluno)
                    print(f"[{decorrido:5.1f}s] aluno {aluno} voltou para a sala")

                resultado = enviar(args.sessao_id, aluno)
                if resultado and aluno not in ja_chegou:
                    ja_chegou.add(aluno)
                    print(f"[{decorrido:5.1f}s] aluno {aluno} chegou -> {resultado}")

            if args.uma_vez and len(ja_chegou) == len(alunos):
                break
            time.sleep(args.intervalo)
    except KeyboardInterrupt:
        print("\nSimulacao interrompida.")
        return

    print("Simulacao concluida.")


if __name__ == "__main__":
    main()
