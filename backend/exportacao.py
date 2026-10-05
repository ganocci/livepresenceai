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

from schemas import RelatorioSessao, SituacaoAlunoOut

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
