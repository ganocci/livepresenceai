"""
LivePresenceAI - Exportacao do relatorio de uma aula em CSV, XLSX e PDF.

Os horarios sao gravados em UTC no banco e exibidos aqui no horario de Brasilia (UTC-3, sem horario de
verao desde 2019). O conteudo e o mesmo do relatorio do app: todos os alunos da aula, com RA, situacao,
entrada, permanencia e percentual (RN-03).
"""
import csv
import io
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from schemas import FrequenciaTurmaOut, RelatorioSessao, SituacaoAlunoOut

FUSO_BRASILIA = timezone(timedelta(hours=-3))
CABECALHO = ["Nome", "RA", "Situação", "Entrada", "Permanência", "Percentual (%)", "Observação"]
TIPOS = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def _local(instante: Optional[datetime]) -> Optional[datetime]:
    if instante is None:
        return None
    return instante.replace(tzinfo=timezone.utc).astimezone(FUSO_BRASILIA)


def _data_hora(instante: Optional[datetime]) -> str:
    local = _local(instante)
    return local.strftime("%d/%m/%Y %H:%M:%S") if local else "-"


def _hora(instante: Optional[datetime]) -> str:
    local = _local(instante)
    return local.strftime("%H:%M:%S") if local else "-"


def _duracao(segundos: float) -> str:
    segundos = int(round(segundos))
    return f"{segundos // 3600:02d}:{segundos % 3600 // 60:02d}:{segundos % 60:02d}"


def _situacao(aluno: SituacaoAlunoOut) -> str:
    if aluno.ajuste_manual:
        return "Presença (manual)" if aluno.situacao == "presenca" else "Falta (manual)"
    if aluno.situacao == "presenca":
        return "Presença"
    return "Falta" if aluno.detectado else "Falta (não detectado)"


def _percentual(valor: float) -> str:
    return f"{valor:.2f}".replace(".", ",")


def _metadados(rel: RelatorioSessao) -> List[Tuple[str, str]]:
    duracao = (rel.fim - rel.inicio).total_seconds() if rel.inicio and rel.fim else 0
    return [
        ("Turma", rel.turma_nome or "-"),
        ("Professor", rel.professor_nome or "-"),
        ("Sala", rel.sala_nome or "-"),
        ("Aula (sessão)", f"#{rel.sessao_id}"),
        ("Início", _data_hora(rel.inicio)),
        ("Fim", _data_hora(rel.fim)),
        ("Duração", _duracao(duracao)),
        ("Frequência mínima", f"{_percentual(rel.frequencia_minima)}% do tempo de aula"),
        ("Presenças", str(rel.total_presencas)),
        ("Faltas", str(rel.total_faltas)),
    ]


def _linhas(rel: RelatorioSessao) -> List[list]:
    return [
        [a.nome, a.ra or "-", _situacao(a), _hora(a.entrada), _duracao(a.tempo_total_presente),
         a.percentual_presenca, a.motivo_ajuste or ""]
        for a in rel.alunos
    ]


def nome_arquivo(rel: RelatorioSessao, formato: str) -> str:
    turma = unicodedata.normalize("NFKD", rel.turma_nome or "turma").encode("ascii", "ignore").decode()
    turma = re.sub(r"[^A-Za-z0-9]+", "_", turma).strip("_").lower() or "turma"
    data = _local(rel.inicio).strftime("%Y-%m-%d") if rel.inicio else "sem_data"
    return f"chamada_{turma}_{data}_aula{rel.sessao_id}.{formato}"


def gerar_csv(rel: RelatorioSessao) -> bytes:
    """Separador ';' e UTF-8 com BOM: abre direto no Excel em portugues."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    for chave, valor in _metadados(rel):
        escritor.writerow([chave, valor])
    escritor.writerow([])
    escritor.writerow(CABECALHO)
    for linha in _linhas(rel):
        escritor.writerow(linha[:5] + [_percentual(linha[5]), linha[6]])
    return saida.getvalue().encode("utf-8-sig")


def gerar_xlsx(rel: RelatorioSessao) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    livro = Workbook()
    folha = livro.active
    folha.title = "Chamada"
    folha.append(["Relatório de chamada - LivePresenceAI"])
    folha["A1"].font = Font(bold=True, size=14)
    for chave, valor in _metadados(rel):
        folha.append([chave, valor])
        folha.cell(row=folha.max_row, column=1).font = Font(bold=True)
    folha.append([])
    folha.append(CABECALHO)
    linha_cabecalho = folha.max_row
    for celula in folha[linha_cabecalho]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor="1F4E79")
        celula.alignment = Alignment(horizontal="center")
    for linha in _linhas(rel):
        folha.append(linha)
        folha.cell(row=folha.max_row, column=6).number_format = "0.00"  # percentual como numero
    folha.freeze_panes = folha.cell(row=linha_cabecalho + 1, column=1)
    for coluna, largura in zip("ABCDEFG", (34, 14, 24, 12, 14, 16, 40)):
        folha.column_dimensions[coluna].width = largura
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def gerar_pdf(rel: RelatorioSessao) -> bytes:
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    gerado_em = datetime.now(FUSO_BRASILIA).strftime("%d/%m/%Y %H:%M")

    class Documento(FPDF):
        def footer(self):
            self.set_y(-12)
            self.set_font("helvetica", size=8)
            self.set_text_color(110)
            self.cell(0, 6, f"Gerado pelo LivePresenceAI em {gerado_em} (horário de Brasília)", align="L")
            self.cell(0, 6, f"Página {self.page_no()}/{{nb}}", align="R")

    pdf = Documento(orientation="L", unit="mm", format="A4")  # paisagem: cabe a coluna de observacao
    pdf.set_title(f"Chamada - {rel.turma_nome or ''} - aula {rel.sessao_id}")
    pdf.set_author("LivePresenceAI")
    pdf.add_page()
    pdf.set_font("helvetica", "B", 15)
    pdf.cell(0, 9, "Relatório de chamada", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", size=10)
    for chave, valor in _metadados(rel):
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(42, 6, f"{chave}:")
        pdf.set_font("helvetica", size=10)
        pdf.cell(0, 6, valor, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("helvetica", size=9)
    cabecalho = FontFace(emphasis="BOLD", color=255, fill_color=(31, 78, 121))
    with pdf.table(col_widths=(62, 24, 36, 20, 24, 24, 77),
                   text_align=("LEFT", "LEFT", "LEFT", "CENTER", "CENTER", "RIGHT", "LEFT"),
                   headings_style=cabecalho, line_height=6) as tabela:
        tabela.row(CABECALHO)
        for linha in _linhas(rel):
            tabela.row([str(v) for v in linha[:5]] + [_percentual(linha[5]), linha[6]])
    return bytes(pdf.output())


def gerar(rel: RelatorioSessao, formato: str) -> Tuple[bytes, str, str]:
    """Conteudo, tipo MIME e nome do arquivo."""
    geradores = {"csv": gerar_csv, "xlsx": gerar_xlsx, "pdf": gerar_pdf}
    return geradores[formato](rel), TIPOS[formato], nome_arquivo(rel, formato)


# ---------------------------------------------------------------------------
# Frequencia acumulada da turma (RN-16)
# ---------------------------------------------------------------------------

CABECALHO_FREQUENCIA = ["Nome", "RA", "Aulas", "Presenças", "Faltas", "Frequência (%)", "Situação", "Ajustes manuais"]


def _metadados_frequencia(freq: FrequenciaTurmaOut) -> List[Tuple[str, str]]:
    periodo = (f"{_local(freq.aulas[0].inicio):%d/%m/%Y} a {_local(freq.aulas[-1].inicio):%d/%m/%Y}"
               if freq.aulas else "-")
    return [
        ("Turma", freq.turma_nome),
        ("Professor", freq.professor_nome or "-"),
        ("Período", periodo),
        ("Aulas encerradas", str(freq.total_aulas)),
        ("Frequência mínima", f"{_percentual(freq.frequencia_minima)}% das aulas"),
        ("Presença em cada aula", f"{_percentual(freq.frequencia_minima_aula)}% do tempo de aula"),
        ("Alunos abaixo do mínimo", str(freq.alunos_abaixo_do_minimo)),
    ]


def _situacao_frequencia(aluno) -> str:
    if aluno.percentual is None:
        return "Sem aulas"
    return "Abaixo do mínimo" if aluno.abaixo_do_minimo else "Regular"


def _linhas_frequencia(freq: FrequenciaTurmaOut) -> List[list]:
    return [[a.nome, a.ra or "-", a.aulas, a.presencas, a.faltas, a.percentual, _situacao_frequencia(a),
             a.ajustes_manuais] for a in freq.alunos]


def _datas_aulas(freq: FrequenciaTurmaOut) -> List[str]:
    return [f"{_local(a.inicio):%d/%m %H:%M}" for a in freq.aulas]


def nome_arquivo_frequencia(freq: FrequenciaTurmaOut, formato: str) -> str:
    turma = unicodedata.normalize("NFKD", freq.turma_nome or "turma").encode("ascii", "ignore").decode()
    turma = re.sub(r"[^A-Za-z0-9]+", "_", turma).strip("_").lower() or "turma"
    return f"frequencia_{turma}_{datetime.now(FUSO_BRASILIA):%Y-%m-%d}.{formato}"


def gerar_frequencia_csv(freq: FrequenciaTurmaOut) -> bytes:
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    for chave, valor in _metadados_frequencia(freq):
        escritor.writerow([chave, valor])
    escritor.writerow([])
    escritor.writerow(CABECALHO_FREQUENCIA + _datas_aulas(freq))
    for aluno, linha in zip(freq.alunos, _linhas_frequencia(freq)):
        percentual = "-" if linha[5] is None else _percentual(linha[5])
        escritor.writerow(linha[:5] + [percentual] + linha[6:] + [p or "" for p in aluno.por_aula])
    escritor.writerow([])
    escritor.writerow(["P = presença; F = falta; vazio = o aluno ainda não fazia parte da turma nessa aula"])
    return saida.getvalue().encode("utf-8-sig")


def gerar_frequencia_xlsx(freq: FrequenciaTurmaOut) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    def cabecalho(folha, valores):
        folha.append(valores)
        linha = folha.max_row
        for celula in folha[linha]:
            celula.font = Font(bold=True, color="FFFFFF")
            celula.fill = PatternFill("solid", fgColor="1F4E79")
            celula.alignment = Alignment(horizontal="center", wrap_text=True)
        return linha

    livro = Workbook()
    folha = livro.active
    folha.title = "Frequência"
    folha.append(["Frequência da turma - LivePresenceAI"])
    folha["A1"].font = Font(bold=True, size=14)
    for chave, valor in _metadados_frequencia(freq):
        folha.append([chave, valor])
        folha.cell(row=folha.max_row, column=1).font = Font(bold=True)
    folha.append([])
    inicio = cabecalho(folha, CABECALHO_FREQUENCIA)
    vermelho = Font(color="C00000", bold=True)
    for aluno, linha in zip(freq.alunos, _linhas_frequencia(freq)):
        folha.append(linha)
        folha.cell(row=folha.max_row, column=6).number_format = "0.00"
        if aluno.abaixo_do_minimo:
            folha.cell(row=folha.max_row, column=7).font = vermelho
    folha.freeze_panes = folha.cell(row=inicio + 1, column=1)
    for coluna, largura in zip("ABCDEFGH", (34, 14, 8, 11, 8, 15, 18, 16)):
        folha.column_dimensions[coluna].width = largura

    # Grade aluno x aula (como o diario de classe)
    grade = livro.create_sheet("Por aula")
    inicio = cabecalho(grade, ["Nome", "RA"] + _datas_aulas(freq))
    cores = {"P": PatternFill("solid", fgColor="E2F0D9"), "F": PatternFill("solid", fgColor="FCE4E4")}
    for aluno in freq.alunos:
        grade.append([aluno.nome, aluno.ra or "-"] + [p or "" for p in aluno.por_aula])
        for coluna, valor in enumerate(aluno.por_aula, start=3):
            celula = grade.cell(row=grade.max_row, column=coluna)
            celula.alignment = Alignment(horizontal="center")
            if valor:
                celula.fill = cores[valor]
    grade.freeze_panes = grade.cell(row=inicio + 1, column=3)
    grade.column_dimensions["A"].width = 34
    grade.column_dimensions["B"].width = 14
    for coluna in range(3, 3 + len(freq.aulas)):
        grade.column_dimensions[get_column_letter(coluna)].width = 11
    grade.append([])
    grade.append(["P = presença; F = falta; vazio = o aluno ainda não fazia parte da turma nessa aula"])
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


def gerar_frequencia_pdf(freq: FrequenciaTurmaOut) -> bytes:
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    gerado_em = datetime.now(FUSO_BRASILIA).strftime("%d/%m/%Y %H:%M")

    class Documento(FPDF):
        def footer(self):
            self.set_y(-12)
            self.set_font("helvetica", size=8)
            self.set_text_color(110)
            self.cell(0, 6, f"Gerado pelo LivePresenceAI em {gerado_em} (horário de Brasília)", align="L")
            self.cell(0, 6, f"Página {self.page_no()}/{{nb}}", align="R")

    pdf = Documento(orientation="P", unit="mm", format="A4")
    pdf.set_title(f"Frequência - {freq.turma_nome}")
    pdf.set_author("LivePresenceAI")
    pdf.add_page()
    pdf.set_font("helvetica", "B", 15)
    pdf.cell(0, 9, "Frequência da turma", new_x="LMARGIN", new_y="NEXT")
    for chave, valor in _metadados_frequencia(freq):
        pdf.set_font("helvetica", "B", 10)
        pdf.cell(48, 6, f"{chave}:")
        pdf.set_font("helvetica", size=10)
        pdf.cell(0, 6, valor, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("helvetica", size=9)
    estilo = FontFace(emphasis="BOLD", color=255, fill_color=(31, 78, 121))
    alerta = FontFace(emphasis="BOLD", color=(192, 0, 0))
    with pdf.table(col_widths=(58, 24, 14, 18, 14, 22, 30), headings_style=estilo, line_height=6,
                   text_align=("LEFT", "LEFT", "CENTER", "CENTER", "CENTER", "RIGHT", "LEFT")) as tabela:
        tabela.row(CABECALHO_FREQUENCIA[:7])
        for aluno, linha in zip(freq.alunos, _linhas_frequencia(freq)):
            linha_pdf = tabela.row()
            percentual = "-" if linha[5] is None else _percentual(linha[5])
            for valor in [str(v) for v in linha[:5]] + [percentual]:
                linha_pdf.cell(valor)
            linha_pdf.cell(linha[6], style=alerta if aluno.abaixo_do_minimo else None)
    return bytes(pdf.output())


def gerar_frequencia(freq: FrequenciaTurmaOut, formato: str) -> Tuple[bytes, str, str]:
    geradores = {"csv": gerar_frequencia_csv, "xlsx": gerar_frequencia_xlsx, "pdf": gerar_frequencia_pdf}
    return geradores[formato](freq), TIPOS[formato], nome_arquivo_frequencia(freq, formato)
