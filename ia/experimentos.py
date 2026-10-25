"""
LivePresenceAI - Ferramentas dos experimentos do TCC (secao 4.6): E1, E2, E3 e E5.

Nenhuma imagem e gravada: cada captura guarda so numeros (similaridades, escore da prova de vida, tamanho
do rosto), em JSON Lines. O protocolo completo esta em docs/experimentos/PROTOCOLO.md.

E1 e E2 - captura (uma "tentativa" = uma pessoa diante da camera por alguns segundos):
  python experimentos.py capturar --turma 3 --pessoa 12 --condicao luz-normal-1m
  python experimentos.py capturar --turma 3 --pessoa nao-cadastrado --condicao luz-normal-1m
  python experimentos.py capturar --turma 3 --pessoa 12 --apresentacao foto --condicao foto-impressa-a4
  python experimentos.py capturar --turma 3 --pessoa 12 --apresentacao video --condicao tela-celular

E1 - reconhecimento (FMR/FNMR, ISO/IEC 19795-1) e E2 - prova de vida (APCER/BPCER, ISO/IEC 30107-3):
  python experimentos.py reconhecimento resultados/capturas.jsonl
  python experimentos.py prova-de-vida resultados/capturas.jsonl

E3 - permanencia: cronometro do observador durante a aula e comparacao com o relatorio do sistema:
  python experimentos.py cronometro --pessoas "12=Ana,13=Bruno" --saida resultados/e3_eventos.csv
  python experimentos.py permanencia --sessao 57 --eventos resultados/e3_eventos.csv --email prof@exemplo.com

E1 - base publica LFW (Labeled Faces in the Wild), protocolo padrao de 6.000 pares em 10 partes:
  python experimentos.py lfw --pasta C:/dados/lfw_base      (contem lfw/<pessoa>/<pessoa>_0001.jpg e pairs.txt)

E5 - desempenho: o proprio modulo da sala mede (modulo_reconhecimento.py --medir) e este comando resume:
  python modulo_reconhecimento.py --turma 3 --medir resultados/e5.csv --duracao 300
  python experimentos.py desempenho resultados/e5.csv
"""
import argparse
import csv
import getpass
import json
import math
import os
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Tuple

PASTA_RESULTADOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultados")
LIMIARES_SIMILARIDADE = [round(0.20 + 0.025 * i, 3) for i in range(25)]   # 0,20 a 0,80
LIMIARES_VIDA = [round(0.50 + 0.025 * i, 3) for i in range(20)]           # 0,50 a 0,975
APRESENTACOES = ("genuina", "foto", "video")


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


def ler_jsonl(arquivos: Iterable[str]) -> List[dict]:
    linhas = []
    for arquivo in arquivos:
        with open(arquivo, encoding="utf-8") as f:
            linhas += [json.loads(linha) for linha in f if linha.strip()]
    if not linhas:
        raise SystemExit("Nenhuma amostra nos arquivos informados.")
    return linhas


def proporcao(parte: int, total: int) -> Optional[float]:
    return parte / total if total else None


def pct(valor: Optional[float], casas: int = 2) -> str:
    return "-" if valor is None else f"{100 * valor:.{casas}f}%"


def limite_superior_zero_erros(n: int) -> Optional[float]:
    """'Regra de tres': com 0 erros em n tentativas independentes, o limite superior de 95% da taxa e ~3/n."""
    return 3 / n if n else None


def escolher_limiar(curva: List[list], admissivel, custo) -> Tuple[list, float, float]:
    """
    Entre os limiares admissiveis, os de menor custo; se varios empatam, o do meio da faixa empatada (maior
    margem para os dois lados, em vez de ficar colado na borda medida com poucas amostras).
    """
    validos = [c for c in curva if admissivel(c)]
    menor = min(custo(c) for c in validos)
    empatados = [c for c in validos if custo(c) == menor]
    return empatados[len(empatados) // 2], empatados[0][0], empatados[-1][0]


def gravar_csv(caminho: str, cabecalho: List[str], linhas: List[list]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:  # BOM: o Excel abre com acentos
        escritor = csv.writer(f, delimiter=";")
        escritor.writerow(cabecalho)
        # Decimal com virgula: o Excel em portugues le "0.6" como texto
        escritor.writerows([[f"{v:.4f}".replace(".", ",") if isinstance(v, float) else v for v in linha]
                            for linha in linhas])


def grafico(caminho: str, titulo: str, eixo_x: str, eixo_y: str, series: List[Tuple[str, list, list]],
            linha_vertical: Optional[Tuple[float, str]] = None, histograma: bool = False) -> None:
    """Figura estatica para o texto do TCC (PNG, 150 dpi). Duas series no maximo: azul e laranja."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cores = ["#2a78d6", "#eb6834"]
    fig, ax = plt.subplots(figsize=(7, 4), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    if histograma:  # mesmas faixas para as duas series, para as barras serem comparaveis
        valores = [v for _, xs, _ in series for v in xs]
        faixas = series[0][2]
        bordas = [min(valores) + (max(valores) - min(valores) + 1e-9) * i / faixas for i in range(faixas + 1)]
    for i, (rotulo, xs, ys) in enumerate(series):
        if histograma:
            ax.hist(xs, bins=bordas, color=cores[i], alpha=0.6, label=rotulo, edgecolor="#fcfcfb", linewidth=1)
        else:
            ax.plot(xs, ys, color=cores[i], linewidth=2, label=rotulo)
    if linha_vertical:
        ax.axvline(linha_vertical[0], color="#52514e", linewidth=1, linestyle="--")
        ax.annotate(linha_vertical[1], (linha_vertical[0], 0.5), xycoords=("data", "axes fraction"),
                    xytext=(4, 0), textcoords="offset points", color="#52514e", fontsize=8,
                    bbox={"boxstyle": "square,pad=0.2", "facecolor": "#fcfcfb", "edgecolor": "none"})
    ax.set_title(titulo, color="#0b0b0b", fontsize=11, loc="left")
    ax.set_xlabel(eixo_x, color="#52514e")
    ax.set_ylabel(eixo_y, color="#52514e")
    ax.tick_params(colors="#52514e", labelsize=8)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color("#c9c8c2")
    ax.grid(axis="y", color="#e6e5e0", linewidth=0.6)
    if eixo_y == "taxa":
        from matplotlib.ticker import PercentFormatter
        ax.yaxis.set_major_formatter(PercentFormatter(1.0))
    ax.legend(frameon=False, fontsize=8, labelcolor="#0b0b0b", loc="best")
    fig.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    fig.savefig(caminho)
    plt.close(fig)


# ============================================================================ captura (E1 e E2)

def capturar(args) -> None:
    import cv2

    from comum import Galeria, Reconhecedor, abrir_fonte, api, desenhar_rosto, escrever_status

    r = api("GET", f"/ia/turmas/{args.turma}/galeria")
    if r.status_code != 200:
        raise SystemExit(f"Erro {r.status_code} ao carregar a turma {args.turma}: {r.text}")
    dados = r.json()
    galeria = Galeria(dados["alunos"])
    if not len(galeria):
        raise SystemExit("A turma nao tem alunos com cadastro facial.")
    cadastrado = args.pessoa != "nao-cadastrado"
    if cadastrado and int(args.pessoa) not in galeria.nomes:
        raise SystemExit(f"Aluno {args.pessoa} sem cadastro facial na turma {args.turma}. "
                         f"Cadastrados: {', '.join(f'{i}={n}' for i, n in galeria.nomes.items())}")
    pessoa = int(args.pessoa) if cadastrado else None
    nome = galeria.nomes[pessoa] if cadastrado else "pessoa nao cadastrada"

    print(f"Carregando modelos (turma '{dados['turma_nome']}', {len(galeria)} cadastrados)...", flush=True)
    reconhecedor = Reconhecedor(prova_de_vida=True)
    saida = args.saida or os.path.join(PASTA_RESULTADOS, "capturas.jsonl")
    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    tentativa = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    intervalo = 1.0 / args.taxa
    inicio_preparo = time.time()
    inicio_captura = None
    ultima_amostra = 0.0
    amostras = sem_rosto = 0

    with open(saida, "a", encoding="utf-8") as arquivo:
        for quadro in abrir_fonte(args.camera, args.imagem, args.video):
            agora = time.time()
            restante_preparo = args.preparo - (agora - inicio_preparo)
            if restante_preparo > 0:
                status = f"{nome} ({args.apresentacao}, {args.condicao}): comeca em {math.ceil(restante_preparo)} s"
            else:
                inicio_captura = inicio_captura or agora
                decorrido = agora - inicio_captura
                if decorrido >= args.segundos:
                    break
                status = f"Gravando {nome}: {args.segundos - decorrido:.0f} s | {amostras} amostras"
                if agora - ultima_amostra >= intervalo:
                    rostos = reconhecedor.rostos(quadro)
                    if not rostos:
                        sem_rosto += 1
                    elif not args.todos_rostos:
                        # Uma pessoa por tentativa: o maior rosto e o dela (ignora quem passa ao fundo)
                        rostos = [max(rostos, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))]
                    for rosto in rostos:
                        similaridades = galeria.matriz @ rosto.normed_embedding
                        melhor = int(similaridades.argmax())
                        vida = rosto.get("liveness") or {}
                        amostra = {
                            "tentativa": tentativa,
                            "momento": agora_utc().isoformat(),
                            "turma": args.turma,
                            "pessoa": pessoa,
                            "apresentacao": args.apresentacao,
                            "condicao": args.condicao,
                            "grupo": args.grupo,
                            "largura_rosto_px": int(rosto.bbox[2] - rosto.bbox[0]),
                            "deteccao": round(float(rosto.det_score), 4),
                            "vida_status": vida.get("status"),
                            "vida_escore": None if vida.get("live_score") is None else round(float(vida["live_score"]), 4),
                            "top1_aluno": galeria.ids[melhor],
                            "top1_similaridade": round(float(similaridades[melhor]), 4),
                            "similaridades": {str(i): round(float(s), 4) for i, s in zip(galeria.ids, similaridades)},
                            "limiar_sistema": dados["confianca_minima"],
                        }
                        arquivo.write(json.dumps(amostra, ensure_ascii=False) + "\n")
                        amostras += 1
                        if not args.sem_janela:
                            cor = (0, 200, 0) if amostra["top1_aluno"] == pessoa else (0, 140, 255)
                            desenhar_rosto(quadro, rosto, f"{galeria.nomes[amostra['top1_aluno']]} "
                                           f"{amostra['top1_similaridade']:.2f} | vida {amostra['vida_escore']}", cor)
                    ultima_amostra = agora
            if not args.sem_janela:
                escrever_status(quadro, status)
                cv2.imshow("LivePresenceAI - experimento", quadro)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    if not args.sem_janela:
        cv2.destroyAllWindows()
    print(f"Tentativa {tentativa}: {amostras} amostras gravadas em {saida}"
          + (f" ({sem_rosto} leituras sem rosto)" if sem_rosto else ""))
    if amostras == 0:
        print("ATENCAO: nenhum rosto detectado; confira o enquadramento e repita a tentativa.")


# ============================================================================ E1 - reconhecimento

def analisar_reconhecimento(args) -> None:
    amostras = [a for a in ler_jsonl(args.arquivos) if a["apresentacao"] == "genuina"]
    if not amostras:
        raise SystemExit("Nenhuma amostra genuina (apresentacao=genuina).")
    limiar_sistema = amostras[-1]["limiar_sistema"]

    # Verificacao 1:1: cada rosto comparado com cada cadastro da galeria
    genuinas, impostoras = [], []
    for a in amostras:
        for aluno, s in a["similaridades"].items():
            (genuinas if a["pessoa"] is not None and int(aluno) == a["pessoa"] else impostoras).append(s)

    def taxas(t: float) -> Tuple[Optional[float], Optional[float]]:
        fmr = proporcao(sum(s >= t for s in impostoras), len(impostoras))
        fnmr = proporcao(sum(s < t for s in genuinas), len(genuinas))
        return fmr, fnmr

    # Identificacao 1:N (como o sistema decide: melhor candidato acima do limiar)
    def identificacao(lista: List[dict], t: float) -> Dict[str, Optional[float]]:
        cadastrados = [a for a in lista if a["pessoa"] is not None]
        nao_cadastrados = [a for a in lista if a["pessoa"] is None]
        certos = sum(a["top1_aluno"] == a["pessoa"] and a["top1_similaridade"] >= t for a in cadastrados)
        trocados = sum(a["top1_aluno"] != a["pessoa"] and a["top1_similaridade"] >= t for a in cadastrados)
        falsos = sum(a["top1_similaridade"] >= t for a in nao_cadastrados)
        return {"acerto": proporcao(certos, len(cadastrados)), "troca": proporcao(trocados, len(cadastrados)),
                "fpir": proporcao(falsos, len(nao_cadastrados)), "n_cad": len(cadastrados), "n_nao": len(nao_cadastrados)}

    curva = []
    for t in LIMIARES_SIMILARIDADE:
        fmr, fnmr = taxas(t)
        ident = identificacao(amostras, t)
        curva.append([t, fmr, fnmr, ident["acerto"], ident["troca"], ident["fpir"]])
    eer = min(curva, key=lambda c: abs((c[1] or 0) - (c[2] or 0)))

    print(f"\nE1 - RECONHECIMENTO ({len(amostras)} amostras genuinas, {len({a['tentativa'] for a in amostras})} tentativas, "
          f"{len({a['pessoa'] for a in amostras if a['pessoa'] is not None})} pessoas cadastradas"
          f"{', com pessoas nao cadastradas' if any(a['pessoa'] is None for a in amostras) else ''})")
    print(f"Comparacoes 1:1: {len(genuinas)} genuinas, {len(impostoras)} impostoras")
    print(f"\n{'limiar':>7} {'FMR':>9} {'FNMR':>9} {'acerto 1:N':>11} {'troca 1:N':>10} {'FPIR':>9}")
    for t, fmr, fnmr, acerto, troca, fpir in curva:
        marca = "  <- limiar atual" if abs(t - limiar_sistema) < 1e-9 else ""
        print(f"{t:>7.3f} {pct(fmr):>9} {pct(fnmr):>9} {pct(acerto):>11} {pct(troca):>10} {pct(fpir):>9}{marca}")
    print(f"\nEER aproximada: {pct((eer[1] + eer[2]) / 2)} no limiar {eer[0]:.3f}")

    admissivel = lambda c: c[1] is not None and c[1] <= args.fmr_alvo and (c[4] or 0) == 0  # noqa: E731
    if any(admissivel(c) for c in curva):
        t, de, ate = escolher_limiar(curva, admissivel, lambda c: c[2] or 0)
        print(f"Limiar sugerido: {t[0]:.3f} (FMR <= {pct(args.fmr_alvo)}, nenhuma troca de identidade e menor FNMR; "
              f"faixa com o mesmo resultado: {de:.3f} a {ate:.3f}): FNMR {pct(t[2])}, acerto 1:N {pct(t[3])}")
        if t[1] == 0:
            print(f"  Com 0 falsas aceitacoes em {len(impostoras)} comparacoes impostoras, o limite superior de 95% "
                  f"da FMR e ~{pct(limite_superior_zero_erros(len(impostoras)))} (regra de tres; as amostras de uma "
                  "mesma tentativa sao correlacionadas, entao o valor real de comparacoes independentes e menor).")
    else:
        print(f"Nenhum limiar da grade atinge FMR <= {pct(args.fmr_alvo)} sem trocas: aumente a amostra ou reveja o cadastro.")

    # Por condicao e por grupo, no limiar atual do sistema
    for campo in ("condicao", "grupo"):
        grupos = defaultdict(list)
        for a in amostras:
            grupos[a.get(campo) or "-"].append(a)
        if len(grupos) > 1 or campo == "condicao":
            print(f"\nPor {campo} (limiar {limiar_sistema}):")
            print(f"  {'':<28} {'amostras':>8} {'acerto 1:N':>11} {'troca':>8} {'FPIR':>8} {'sim. media (genuina)':>21}")
            for nome, lista in sorted(grupos.items()):
                ident = identificacao(lista, limiar_sistema)
                sims = [a["similaridades"][str(a["pessoa"])] for a in lista if a["pessoa"] is not None]
                media = f"{sum(sims) / len(sims):.3f}" if sims else "-"
                print(f"  {nome:<28} {len(lista):>8} {pct(ident['acerto']):>11} {pct(ident['troca']):>8} "
                      f"{pct(ident['fpir']):>8} {media:>21}")

    # Por tentativa (como o professor ve: a pessoa foi reconhecida durante a tentativa?)
    por_tentativa = defaultdict(list)
    for a in amostras:
        por_tentativa[a["tentativa"]].append(a)
    cad = [l for l in por_tentativa.values() if l[0]["pessoa"] is not None]
    reconhecidas = sum(any(a["top1_aluno"] == a["pessoa"] and a["top1_similaridade"] >= limiar_sistema for a in l) for l in cad)
    com_troca = sum(any(a["top1_aluno"] != a["pessoa"] and a["top1_similaridade"] >= limiar_sistema for a in l) for l in cad)
    print(f"\nPor tentativa (limiar {limiar_sistema}): {reconhecidas}/{len(cad)} tentativas de cadastrados reconhecidas; "
          f"{com_troca} com alguma amostra atribuida a outra pessoa")

    base = os.path.splitext(args.arquivos[0])[0]
    gravar_csv(base + "_e1_curva.csv", ["limiar", "FMR", "FNMR", "acerto_1N", "troca_1N", "FPIR"], curva)
    grafico(base + "_e1_distribuicao.png", "Similaridade entre rosto e cadastro", "similaridade de cosseno",
            "comparações", [("mesma pessoa (genuína)", genuinas, 40), ("outra pessoa (impostora)", impostoras, 40)],
            (limiar_sistema, f"limiar atual {limiar_sistema}"), histograma=True)
    grafico(base + "_e1_taxas.png", "FMR e FNMR por limiar", "limiar de similaridade", "taxa",
            [("FMR", [c[0] for c in curva], [c[1] for c in curva]),
             ("FNMR", [c[0] for c in curva], [c[2] for c in curva])],
            (limiar_sistema, f"limiar atual {limiar_sistema}"))
    print(f"\nArquivos: {base}_e1_curva.csv, {base}_e1_distribuicao.png, {base}_e1_taxas.png")


# ============================================================================ E2 - prova de vida

def analisar_prova_de_vida(args) -> None:
    todas = ler_jsonl(args.arquivos)
    inconclusivas = [a for a in todas if a.get("vida_status") != "ok"]
    amostras = [a for a in todas if a.get("vida_status") == "ok" and a.get("vida_escore") is not None]
    genuinas = [a["vida_escore"] for a in amostras if a["apresentacao"] == "genuina"]
    ataques = {tipo: [a["vida_escore"] for a in amostras if a["apresentacao"] == tipo] for tipo in ("foto", "video")}
    ataques = {t: v for t, v in ataques.items() if v}
    if not genuinas or not ataques:
        raise SystemExit("E2 precisa de amostras genuinas e de ataque (--apresentacao foto/video).")
    limiar_atual = args.limiar_atual

    def taxas(t: float):
        bpcer = proporcao(sum(s < t for s in genuinas), len(genuinas))
        apcer = {tipo: proporcao(sum(s >= t for s in v), len(v)) for tipo, v in ataques.items()}
        return bpcer, apcer, max(apcer.values())

    print(f"\nE2 - PROVA DE VIDA: {len(genuinas)} amostras genuinas; "
          + ", ".join(f"{len(v)} de ataque por {t}" for t, v in ataques.items())
          + f"; {len(inconclusivas)} inconclusivas (rosto cortado na borda), fora do calculo")
    tipos = list(ataques)
    print(f"\n{'limiar':>7} {'BPCER':>9} " + " ".join(f"{'APCER ' + t:>12}" for t in tipos) + f" {'APCER max':>10}")
    curva = []
    for t in LIMIARES_VIDA:
        bpcer, apcer, pior = taxas(t)
        curva.append([t, bpcer] + [apcer[x] for x in tipos] + [pior])
        marca = "  <- limiar atual" if abs(t - limiar_atual) < 1e-9 else ""
        print(f"{t:>7.3f} {pct(bpcer):>9} " + " ".join(f"{pct(apcer[x]):>12}" for x in tipos) + f" {pct(pior):>10}{marca}")

    admissivel = lambda c: c[-1] <= args.apcer_alvo  # noqa: E731
    if any(admissivel(c) for c in curva):
        melhor, de, ate = escolher_limiar(curva, admissivel, lambda c: c[1])
        print(f"\nLimiar sugerido: {melhor[0]:.3f} (menor BPCER com APCER <= {pct(args.apcer_alvo)} em todo tipo de ataque; "
              f"faixa com o mesmo resultado: {de:.3f} a {ate:.3f}): BPCER {pct(melhor[1])}, APCER max {pct(melhor[-1])}")
    else:
        print(f"\nNenhum limiar atinge APCER <= {pct(args.apcer_alvo)}: a prova de vida nao bloqueia esses ataques.")

    # Rostos genuínos recusados por faixa de tamanho: mostra a partir de que distância a prova de vida atrapalha
    faixas = [(0, 60), (60, 90), (90, 130), (130, 10 ** 6)]
    print(f"\nGenuínos recusados por largura do rosto (limiar {limiar_atual}):")
    for de, ate in faixas:
        lista = [a["vida_escore"] for a in amostras if a["apresentacao"] == "genuina" and de <= a["largura_rosto_px"] < ate]
        if lista:
            rotulo = f"{de}-{ate} px" if ate < 10 ** 6 else f">= {de} px"
            print(f"  {rotulo:<12} {len(lista):>5} amostras, recusadas {pct(proporcao(sum(s < limiar_atual for s in lista), len(lista)))}")

    # Por tentativa: um ataque "passa" se algum quadro for aceito (no sistema, basta um para identificar a trilha)
    por_tentativa = defaultdict(list)
    for a in amostras:
        por_tentativa[a["tentativa"]].append(a)
    print(f"\nPor tentativa (limiar {limiar_atual}):")
    for tipo in ["genuina"] + tipos:
        lista = [l for l in por_tentativa.values() if l[0]["apresentacao"] == tipo]
        if not lista:
            continue
        if tipo == "genuina":
            bloqueadas = sum(all(a["vida_escore"] < limiar_atual for a in l) for l in lista)
            print(f"  genuinas totalmente recusadas: {bloqueadas}/{len(lista)}")
        else:
            passaram = sum(any(a["vida_escore"] >= limiar_atual for a in l) for l in lista)
            print(f"  ataques por {tipo} com ao menos um quadro aceito: {passaram}/{len(lista)}")

    base = os.path.splitext(args.arquivos[0])[0]
    gravar_csv(base + "_e2_curva.csv", ["limiar", "BPCER"] + [f"APCER_{t}" for t in tipos] + ["APCER_max"], curva)
    todos_ataques = [s for v in ataques.values() for s in v]
    grafico(base + "_e2_distribuicao.png", "Escore da prova de vida", "escore (1 = pessoa real)", "amostras",
            [("pessoa real", genuinas, 30), ("ataque (" + ", ".join(tipos) + ")", todos_ataques, 30)],
            (limiar_atual, f"limiar atual {limiar_atual}"), histograma=True)
    grafico(base + "_e2_taxas.png", "BPCER e APCER por limiar", "limiar da prova de vida", "taxa",
            [("BPCER", [c[0] for c in curva], [c[1] for c in curva]),
             ("APCER (pior tipo)", [c[0] for c in curva], [c[-1] for c in curva])],
            (limiar_atual, f"limiar atual {limiar_atual}"))
    print(f"\nArquivos: {base}_e2_curva.csv, {base}_e2_distribuicao.png, {base}_e2_taxas.png")


# ============================================================================ E3 - permanencia

def cronometro(args) -> None:
    pessoas = {}
    for item in args.pessoas.split(","):
        numero, _, nome = item.partition("=")
        pessoas[int(numero.strip())] = nome.strip() or numero.strip()
    dentro = {p: False for p in pessoas}
    novo = not os.path.exists(args.saida)
    os.makedirs(os.path.dirname(os.path.abspath(args.saida)), exist_ok=True)
    print("Cronometro do E3. Digite o numero do aluno e Enter quando ele ENTRAR ou SAIR da sala (alterna).")
    print("  " + "   ".join(f"{p} = {n}" for p, n in pessoas.items()))
    print("  'v' + Enter: ver quem esta dentro    'q' + Enter: terminar\n")
    with open(args.saida, "a", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f, delimiter=";")
        if novo:
            escritor.writerow(["momento_utc", "aluno_id", "nome", "evento"])
        while True:
            try:
                comando = input("> ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                break
            momento = agora_utc()  # registrado no Enter, antes de qualquer processamento
            if comando == "q":
                break
            if comando == "v":
                print("  dentro: " + (", ".join(n for p, n in pessoas.items() if dentro[p]) or "ninguem"))
                continue
            if not comando.isdigit() or int(comando) not in pessoas:
                print("  numero desconhecido")
                continue
            p = int(comando)
            dentro[p] = not dentro[p]
            evento = "entrou" if dentro[p] else "saiu"
            escritor.writerow([momento.isoformat(), p, pessoas[p], evento])
            f.flush()
            print(f"  {momento.astimezone():%H:%M:%S}  {pessoas[p]} {evento}")
    print(f"Eventos gravados em {args.saida}")


def _instante(texto: str) -> datetime:
    """Datas do backend sem fuso sao UTC (padrao do sistema desde 30/09/2026)."""
    valor = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)


def permanencia(args) -> None:
    from comum import URL_BACKEND, _SESSAO

    senha = os.getenv("LIVEPRESENCEAI_SENHA") or getpass.getpass(f"Senha de {args.email}: ")
    r = _SESSAO.post(f"{URL_BACKEND}/login", data={"username": args.email, "password": senha}, timeout=10)
    if r.status_code != 200:
        raise SystemExit(f"Login recusado: {r.text}")
    token = r.json()["access_token"]
    r = _SESSAO.get(f"{URL_BACKEND}/sessoes/{args.sessao}/relatorio", headers={"Authorization": f"Bearer {token}"},
                    timeout=10)
    if r.status_code != 200:
        raise SystemExit(f"Relatorio indisponivel ({r.status_code}): {r.text} - a chamada precisa estar encerrada.")
    relatorio = r.json()
    inicio, fim = _instante(relatorio["inicio"]), _instante(relatorio["fim"])
    duracao = (fim - inicio).total_seconds()
    minimo = relatorio.get("frequencia_minima", 0.4)
    minimo = minimo * 100 if minimo <= 1 else minimo

    eventos = defaultdict(list)
    with open(args.eventos, encoding="utf-8") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            eventos[int(linha["aluno_id"])].append((_instante(linha["momento_utc"]), linha["evento"]))

    linhas, erros_s, erros_pp, situacoes_erradas = [], [], [], 0
    sistema = {a["aluno_id"]: a for a in relatorio["alunos"]}
    print(f"\nE3 - PERMANENCIA: sessao #{args.sessao}, {duracao / 60:.1f} min, minimo {minimo:.0f}%")
    print(f"{'aluno':<22} {'cronometro':>11} {'sistema':>9} {'erro (s)':>9} {'esperado':>9} {'sistema':>8} {'erro (pp)':>10} situacao")
    for aluno_id, lista in sorted(eventos.items()):
        lista.sort()
        real, entrou = 0.0, None
        for momento, evento in lista:
            if evento == "entrou":
                entrou = momento
            elif entrou is not None:
                real += max(0.0, (min(momento, fim) - max(entrou, inicio)).total_seconds())
                entrou = None
        if entrou is not None:  # ainda na sala no encerramento
            real += max(0.0, (fim - max(entrou, inicio)).total_seconds())
        s = sistema.get(aluno_id)
        if not s:
            print(f"  aluno {aluno_id} nao esta no relatorio (turma errada?)")
            continue
        medido = s["tempo_total_presente"]
        pct_real = 100 * real / duracao if duracao else 0
        pct_sistema = s["percentual_presenca"]
        esperada = "presenca" if pct_real >= minimo else "falta"
        calculada = s.get("situacao_calculada") or s["situacao"]
        situacoes_erradas += esperada != calculada
        erros_s.append(medido - real)
        erros_pp.append(pct_sistema - pct_real)
        linhas.append([aluno_id, s["nome"], round(real, 1), round(medido, 1), round(medido - real, 1),
                       round(pct_real, 2), round(pct_sistema, 2), round(pct_sistema - pct_real, 2), esperada, calculada])
        ok = "ok" if esperada == calculada else f"ERRO (esperado {esperada})"
        print(f"{s['nome'][:22]:<22} {real:>10.0f}s {medido:>8.0f}s {medido - real:>+9.0f} {pct_real:>8.1f}% "
              f"{pct_sistema:>7.1f}% {pct_sistema - pct_real:>+10.1f} {calculada} {ok}")
    if erros_s:
        mae_s = sum(abs(e) for e in erros_s) / len(erros_s)
        mae_pp = sum(abs(e) for e in erros_pp) / len(erros_pp)
        print(f"\nErro absoluto medio: {mae_s:.1f} s e {mae_pp:.2f} pontos percentuais; "
              f"maior erro {max(erros_s, key=abs):+.0f} s; situacao divergente em {situacoes_erradas}/{len(erros_s)}")
        print("Sinal do erro: positivo = o sistema contou mais tempo que o cronometro.")
    saida = os.path.splitext(args.eventos)[0] + f"_sessao{args.sessao}_comparacao.csv"
    gravar_csv(saida, ["aluno_id", "nome", "cronometro_s", "sistema_s", "erro_s", "esperado_pct", "sistema_pct",
                       "erro_pp", "situacao_esperada", "situacao_sistema"], linhas)
    print(f"Arquivo: {saida}")


# ============================================================================ E5 - desempenho

def _percentis(valores: List[float]) -> str:
    if not valores:
        return "-"
    v = sorted(valores)

    def p(q):
        return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]
    return f"mediana {p(0.5):7.1f} | p95 {p(0.95):7.1f} | max {v[-1]:7.1f}"


def desempenho(args) -> None:
    quadros, envios, recursos = [], [], []
    with open(args.arquivo, encoding="utf-8") as f:
        for linha in csv.DictReader(f, delimiter=";"):
            {"quadro": quadros, "envio": envios, "recurso": recursos}[linha["tipo"]].append(linha)
    if not quadros:
        raise SystemExit("Nenhum quadro medido (a chamada estava aberta durante a medicao?).")

    def coluna(linhas, nome):
        return [float(l[nome]) for l in linhas if l.get(nome) not in (None, "")]

    instantes = coluna(quadros, "momento")
    duracao = instantes[-1] - instantes[0] if len(instantes) > 1 else 0
    print(f"\nE5 - DESEMPENHO: {len(quadros)} quadros em {duracao:.0f} s ({quadros[0].get('modo', '')}, "
          f"{quadros[0].get('provedor', '')})")
    if duracao:
        print(f"Quadros por segundo (media): {(len(quadros) - 1) / duracao:.1f}")
    print("\nTempo por quadro (ms):")
    for nome, rotulo in (("captura_ms", "espera da camera"), ("rastreamento_ms", "YOLOv8 + DeepSORT"),
                         ("deteccao_ms", "deteccao de rostos (SCRFD)"), ("prova_vida_ms", "prova de vida"),
                         ("reconhecimento_ms", "reconhecimento (ArcFace)"), ("processamento_ms", "processamento total")):
        valores = coluna(quadros, nome)
        if valores:
            print(f"  {rotulo:<28} {_percentis(valores)}")
    rostos = coluna(quadros, "rostos")
    if rostos:
        print(f"  rostos por quadro: media {sum(rostos) / len(rostos):.2f}, maximo {max(rostos):.0f}")
    if envios:
        print(f"\nDa captura do quadro ao registro no backend ({len(envios)} envios, ms):")
        print(f"  latencia total               {_percentis(coluna(envios, 'latencia_ms'))}")
        print(f"  so a requisicao HTTP         {_percentis(coluna(envios, 'http_ms'))}")
    if recursos:
        print("\nRecursos (amostras a cada 2 s):")
        for nome, rotulo in (("cpu_processo_pct", "CPU do modulo (% do total)"), ("cpu_sistema_pct", "CPU do computador (%)"),
                             ("memoria_mb", "memoria do modulo (MB)"), ("gpu_pct", "GPU (%)"), ("gpu_memoria_mb", "memoria da GPU (MB)")):
            valores = coluna(recursos, nome)
            if valores:
                print(f"  {rotulo:<28} media {sum(valores) / len(valores):7.1f} | max {max(valores):7.1f}")


# ============================================================================ E1 - base pública LFW

def _pares_lfw(arquivo: str) -> List[Tuple[int, str, str, bool]]:
    """pairs.txt: '10 300' e, em cada parte, 300 pares da mesma pessoa ('nome i j') e 300 de pessoas
    diferentes ('nome1 i nome2 j'). Devolve (parte, imagem_a, imagem_b, mesma_pessoa)."""
    with open(arquivo, encoding="utf-8") as f:
        linhas = [l.split() for l in f if l.strip()]
    partes, por_parte = int(linhas[0][0]), int(linhas[0][1])
    img = lambda nome, n: f"{nome}/{nome}_{int(n):04d}.jpg"  # noqa: E731
    pares, i = [], 1
    for parte in range(partes):
        for _ in range(por_parte):
            nome, a, b = linhas[i]
            pares.append((parte, img(nome, a), img(nome, b), True))
            i += 1
        for _ in range(por_parte):
            n1, a, n2, b = linhas[i]
            pares.append((parte, img(n1, a), img(n2, b), False))
            i += 1
    return pares


def lfw(args) -> None:
    import numpy as np

    from comum import Reconhecedor, ler_imagem

    pasta = args.pasta
    pares = _pares_lfw(os.path.join(pasta, "pairs.txt"))
    raiz = os.path.join(pasta, "lfw")
    imagens = sorted({p[1] for p in pares} | {p[2] for p in pares})
    cache = os.path.join(PASTA_RESULTADOS, "lfw_vetores.npz")
    vetores: Dict[str, np.ndarray] = {}
    if os.path.exists(cache):
        dados = np.load(cache, allow_pickle=False)
        vetores = {k: dados[k] for k in dados.files}
    faltam = [i for i in imagens if i.replace("/", "__") not in vetores]
    sem_rosto = []
    if faltam:
        print(f"Extraindo vetores de {len(faltam)} imagens (o resultado fica em cache)...", flush=True)
        reconhecedor = Reconhecedor(prova_de_vida=False)
        inicio = time.time()
        for k, nome in enumerate(faltam, 1):
            quadro = ler_imagem(os.path.join(raiz, nome))
            rostos = reconhecedor.rostos(quadro) if quadro is not None else []
            if rostos:
                # Na LFW o rosto da pessoa está centralizado: escolhe o mais próximo do centro
                cy, cx = quadro.shape[0] / 2, quadro.shape[1] / 2
                rosto = min(rostos, key=lambda f: ((f.bbox[0] + f.bbox[2]) / 2 - cx) ** 2
                            + ((f.bbox[1] + f.bbox[3]) / 2 - cy) ** 2)
                vetores[nome.replace("/", "__")] = rosto.normed_embedding.astype(np.float32)
            else:
                sem_rosto.append(nome)
            if k % 500 == 0:
                print(f"  {k}/{len(faltam)} ({(time.time() - inicio) / k * 1000:.0f} ms por imagem)", flush=True)
        os.makedirs(PASTA_RESULTADOS, exist_ok=True)
        np.savez(cache, **vetores)

    # Similaridade de cosseno de cada par (vetores normalizados: produto escalar)
    avaliados, falhas_aquisicao = [], 0
    for parte, a, b, mesma in pares:
        va, vb = vetores.get(a.replace("/", "__")), vetores.get(b.replace("/", "__"))
        if va is None or vb is None:
            falhas_aquisicao += 1
            continue
        avaliados.append((parte, float(va @ vb), mesma))
    genuinas = [s_ for _, s_, m in avaliados if m]
    impostoras = [s_ for _, s_, m in avaliados if not m]

    def taxas(t, lista=avaliados):
        g = [s_ for _, s_, m in lista if m]
        i = [s_ for _, s_, m in lista if not m]
        return proporcao(sum(x >= t for x in i), len(i)), proporcao(sum(x < t for x in g), len(g))

    curva = [[t, *taxas(t)] for t in LIMIARES_SIMILARIDADE]
    # Acurácia em 10 partes: o limiar é escolhido nas outras 9 partes e aplicado na parte que ficou de fora
    grade = [round(0.10 + 0.005 * i, 3) for i in range(141)]
    acuracias = []
    for parte in range(10):
        treino = [x for x in avaliados if x[0] != parte]
        teste = [x for x in avaliados if x[0] == parte]
        acerto = lambda lista, t: sum((s_ >= t) == m for _, s_, m in lista) / len(lista)  # noqa: E731
        notas = [acerto(treino, t) for t in grade]
        empatados = [t for t, n in zip(grade, notas) if n == max(notas)]
        melhor = empatados[len(empatados) // 2]  # meio da faixa de melhor acurácia, como no E1 em sala
        acuracias.append((acerto(teste, melhor), melhor))
    media = sum(a for a, _ in acuracias) / len(acuracias)
    dp = (sum((a - media) ** 2 for a, _ in acuracias) / (len(acuracias) - 1)) ** 0.5
    eer = min(curva, key=lambda c: abs((c[1] or 0) - (c[2] or 0)))
    fmr6, fnmr6 = taxas(0.6)

    print(f"\nE1 - LFW: {len(pares)} pares; {len(avaliados)} avaliados; {falhas_aquisicao} pares com falha de "
          f"aquisição (rosto não detectado em uma das imagens{': ' + str(len(sem_rosto)) + ' imagens' if sem_rosto else ''})")
    print(f"Acurácia de verificação (10 partes, limiar escolhido nas outras 9): {100 * media:.2f}% ± {100 * dp:.2f}%"
          f" (limiares escolhidos: {min(t for _, t in acuracias):.3f} a {max(t for _, t in acuracias):.3f})")
    print(f"EER aproximada: {pct((eer[1] + eer[2]) / 2)} no limiar {eer[0]:.3f}")
    print(f"No limiar do sistema (0,60): FMR {pct(fmr6)} e FNMR {pct(fnmr6)}")
    if fmr6 == 0:
        print(f"  0 falsas aceitações em {len(impostoras)} pares impostores: limite superior de 95% da FMR "
              f"~{pct(limite_superior_zero_erros(len(impostoras)))} (regra de três)")
    print(f"\n{'limiar':>7} {'FMR':>9} {'FNMR':>9}")
    for t, fmr, fnmr in curva:
        print(f"{t:>7.3f} {pct(fmr):>9} {pct(fnmr):>9}")

    base = os.path.join(PASTA_RESULTADOS, "lfw")
    gravar_csv(base + "_e1_curva.csv", ["limiar", "FMR", "FNMR"], curva)
    gravar_csv(base + "_e1_partes.csv", ["parte", "acuracia", "limiar"],
               [[i + 1, a, t] for i, (a, t) in enumerate(acuracias)])
    grafico(base + "_e1_distribuicao.png", "Similaridade nos pares da LFW", "similaridade de cosseno", "pares",
            [("mesma pessoa", genuinas, 40), ("pessoas diferentes", impostoras, 40)], (0.6, "limiar do sistema 0.6"),
            histograma=True)
    grafico(base + "_e1_taxas.png", "FMR e FNMR por limiar (LFW)", "limiar de similaridade", "taxa",
            [("FMR", [c[0] for c in curva], [c[1] for c in curva]),
             ("FNMR", [c[0] for c in curva], [c[2] for c in curva])], (0.6, "limiar do sistema 0.6"))
    print(f"\nArquivos: {base}_e1_curva.csv, {base}_e1_partes.csv, {base}_e1_distribuicao.png, {base}_e1_taxas.png")


# ============================================================================ linha de comando

def main() -> None:
    parser = argparse.ArgumentParser(description="Experimentos do TCC (LivePresenceAI)",
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)

    c = sub.add_parser("capturar", help="E1/E2: grava as medidas de uma tentativa (sem imagens)")
    c.add_argument("--turma", type=int, required=True, help="turma de experimento (alunos cadastrados = galeria)")
    c.add_argument("--pessoa", required=True, help="aluno_id de quem esta na frente da camera, ou nao-cadastrado")
    c.add_argument("--apresentacao", choices=APRESENTACOES, default="genuina",
                   help="genuina (a propria pessoa), foto (impressa) ou video (tela de celular)")
    c.add_argument("--condicao", required=True, help="rotulo livre, ex.: luz-normal-1m, contraluz-3m, oculos")
    c.add_argument("--grupo", default=None, help="grupo demografico declarado (opcional, para a analise por grupo)")
    c.add_argument("--segundos", type=float, default=10, help="duracao da gravacao (padrao 10)")
    c.add_argument("--preparo", type=float, default=3, help="contagem regressiva antes de gravar (padrao 3)")
    c.add_argument("--taxa", type=float, default=3, help="amostras por segundo (padrao 3)")
    c.add_argument("--todos-rostos", action="store_true", help="grava todos os rostos do quadro, nao so o maior")
    c.add_argument("--camera", type=int, default=0)
    c.add_argument("--video", help="arquivo de video no lugar da camera")
    c.add_argument("--imagem", help="imagem fixa no lugar da camera")
    c.add_argument("--saida", help="arquivo JSONL (padrao ia/resultados/capturas.jsonl)")
    c.add_argument("--sem-janela", action="store_true")

    e1 = sub.add_parser("reconhecimento", help="E1: FMR, FNMR, identificacao 1:N e limiar sugerido")
    e1.add_argument("arquivos", nargs="+")
    e1.add_argument("--fmr-alvo", type=float, default=0.001, help="FMR maxima para sugerir o limiar (padrao 0,1%%)")

    e2 = sub.add_parser("prova-de-vida", help="E2: APCER, BPCER e limiar sugerido")
    e2.add_argument("arquivos", nargs="+")
    e2.add_argument("--apcer-alvo", type=float, default=0.05, help="APCER maxima para sugerir o limiar (padrao 5%%)")
    e2.add_argument("--limiar-atual", type=float, default=float(os.getenv("LIMIAR_PROVA_VIDA", "0.8")))

    cr = sub.add_parser("cronometro", help="E3: o observador registra entradas e saidas")
    cr.add_argument("--pessoas", required=True, help='"aluno_id=Nome,..." (ex.: "12=Ana,13=Bruno")')
    cr.add_argument("--saida", default=os.path.join(PASTA_RESULTADOS, "e3_eventos.csv"))

    pe = sub.add_parser("permanencia", help="E3: compara o cronometro com o relatorio da chamada")
    pe.add_argument("--sessao", type=int, required=True)
    pe.add_argument("--eventos", required=True)
    pe.add_argument("--email", required=True, help="professor dono da turma (senha pedida ou LIVEPRESENCEAI_SENHA)")

    lf = sub.add_parser("lfw", help="E1: verificação na base pública LFW (protocolo de 6.000 pares)")
    lf.add_argument("--pasta", required=True, help="pasta com lfw\\ (imagens por pessoa) e pairs.txt")

    de = sub.add_parser("desempenho", help="E5: resume o CSV de modulo_reconhecimento.py --medir")
    de.add_argument("arquivo")

    args = parser.parse_args()
    {"capturar": capturar, "reconhecimento": analisar_reconhecimento, "prova-de-vida": analisar_prova_de_vida,
     "cronometro": cronometro, "permanencia": permanencia, "desempenho": desempenho, "lfw": lfw}[args.comando](args)


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    main()
