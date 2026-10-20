"""Geração de Excel compartilhada (openpyxl). Usada por ambas as unidades."""
import calendar
import csv
import io
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

_BORDA = Border(
    left=Side(style="thin", color="CCCCCC"),
    right=Side(style="thin", color="CCCCCC"),
    top=Side(style="thin", color="CCCCCC"),
    bottom=Side(style="thin", color="CCCCCC"),
)


def _header_row(ws, cols: list[tuple[str, int]], cor_fundo: str = "1F3864"):
    for col, (nome, larg) in enumerate(cols, 1):
        c = ws.cell(row=2, column=col, value=nome)
        c.font = Font(bold=True, color="FFFFFF", size=10)
        c.fill = PatternFill("solid", fgColor=cor_fundo)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = _BORDA
        ws.column_dimensions[get_column_letter(col)].width = larg
    ws.row_dimensions[2].height = 22
    ws.freeze_panes = "A3"


def _titulo_row(ws, cols: list[tuple[str, int]], titulo: str):
    ws.merge_cells(f"A1:{get_column_letter(len(cols))}1")
    ws["A1"] = titulo
    ws["A1"].font = Font(bold=True, color="1F3864", size=13)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28


def _somar_meses(d: date, meses: int) -> date:
    m = d.month - 1 + meses
    ano, mes = d.year + m // 12, m % 12 + 1
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def descrever_atraso(data_prev: date, hoje: date) -> str:
    """Tempo entre a data prevista e hoje, em linguagem corrida: "3 dias", "1 mês", "2 meses e 5 dias".
    Menos de um mês de calendário fica em dias; vazio quando não há atraso."""
    dias = (hoje - data_prev).days
    if dias <= 0:
        return ""
    meses = (hoje.year - data_prev.year) * 12 + hoje.month - data_prev.month
    if hoje.day < data_prev.day:
        meses -= 1
    if meses <= 0:
        return f"{dias} dia" if dias == 1 else f"{dias} dias"
    resto = max(0, (hoje - _somar_meses(data_prev, meses)).days)
    texto = f"{meses} mês" if meses == 1 else f"{meses} meses"
    if resto:
        texto += f" e {resto} dia" if resto == 1 else f" e {resto} dias"
    return texto


def _atraso_da_linha(r: dict, hoje: date) -> str:
    if not r.get("atrasada"):
        return ""
    try:
        return descrever_atraso(date.fromisoformat(str(r.get("data_iso") or "")), hoje)
    except ValueError:
        return ""


def gerar_excel_preventivas(preventivas: list, d_ini=None, d_fim=None, nome_unidade: str = "", hoje: date | None = None) -> io.BytesIO:
    """Planilha das preventivas já filtradas. OS atrasadas saem com o status "<status> em atraso" e, em "Período em atraso",
    há quanto tempo estão atrasadas (data prevista até `hoje`, data local do Brasil)."""
    if hoje is None:
        from core.preventivas import hoje_local   # import tardio: evita ciclo exporters <-> preventivas
        hoje = hoje_local()
    wb = Workbook()
    ws = wb.active
    ws.title = "Preventivas"

    cols = [
        ("Data", 12), ("Dia", 8), ("Turno", 10), ("Status", 24), ("Período em atraso", 20), ("Plano", 42), ("Tipo", 14),
        ("Oficina", 20), ("Equipamento", 28), ("Setor", 30), ("OS", 12), ("Responsável atual (Neovero)", 30),
        ("Situação do responsável", 16), ("Recomendado", 32), ("Cargo", 28), ("Escala", 16), ("Revisão", 9),
        ("Observação", 60),
    ]

    if d_ini and d_fim:
        periodo_str = f"{d_ini.strftime('%d/%m/%Y')} a {d_fim.strftime('%d/%m/%Y')}"
    elif d_ini:
        periodo_str = f"a partir de {d_ini.strftime('%d/%m/%Y')}"
    elif d_fim:
        periodo_str = f"até {d_fim.strftime('%d/%m/%Y')}"
    else:
        periodo_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    unidade_prefix = f"{nome_unidade} — " if nome_unidade else ""
    _titulo_row(ws, cols, f"{unidade_prefix}Preventivas — {periodo_str}")
    _header_row(ws, cols)

    cor_status = {"Concluída": "E8F5E9", "Em andamento": "E3F2FD", "Pendente": "FFFDE7", "Cancelada": "F5F5F5",
                  "Parada": "FFF3E0", "Aguardando geração": "FFFFFF", "Sem OS – verificar": "F3E5F5"}
    for i, r in enumerate(preventivas, 3):
        if r.get("atrasada"):
            fill = PatternFill("solid", fgColor="FFCDD2")
        elif r.get("sem_candidato") or r.get("requer_intervencao"):
            fill = PatternFill("solid", fgColor="FFEBEE")
        else:
            fill = PatternFill("solid", fgColor=cor_status.get(r.get("status", ""), "FFFFFF"))
        recomendados = r.get("recomendados") or ([r["recomendado"]] if r.get("recomendado") else [])
        if recomendados:
            recomendado = " + ".join(recomendados)
        elif r.get("sem_candidato"):
            recomendado = "SEM CANDIDATO"
        else:
            recomendado = ""
        obs = []
        if r.get("motivo_intervencao"):
            obs.append("Requer intervenção: " + r["motivo_intervencao"])
        elif r.get("motivo_sem_candidato"):
            obs.append(r["motivo_sem_candidato"])
        obs.extend(r.get("alertas") or [])
        if r.get("revisao"):
            obs.append("Revisar: responsável da OS no Neovero não é um executante válido.")
        for col, val in enumerate([
            r.get("data_prev", ""),
            r.get("dia_par", ""),
            r.get("turno", ""),
            f"{r.get('status', '')} em atraso" if r.get("atrasada") else r.get("status", ""),
            _atraso_da_linha(r, hoje),
            r.get("plano", ""),
            r.get("tipo", ""),
            r.get("oficina", ""),
            r.get("equipamento", "—"),
            r.get("setor", "—"),
            r.get("os_vinculada", "—"),
            r.get("responsavel_atual") or "",
            r.get("responsavel_status", ""),
            recomendado,
            r.get("cargo", ""),
            r.get("escala", ""),
            "Sim" if r.get("revisao") else "",
            " | ".join(obs),
        ], 1):
            c = ws.cell(row=i, column=col, value=valor_seguro(val))
            c.fill = fill
            c.alignment = Alignment(vertical="center", wrap_text=True)
            c.border = _BORDA
        ws.row_dimensions[i].height = 18

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def gerar_excel_planos(planos: list, nome_unidade: str = "") -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "Planos de Manutenção"

    cols = [
        ("ID", 10), ("Descrição", 45), ("Tipo", 30), ("Periodicidade", 16),
        ("Oficina", 22), ("Procedimento", 45), ("Ativo", 12),
    ]

    unidade_prefix = f"{nome_unidade} — " if nome_unidade else ""
    _titulo_row(ws, cols, f"{unidade_prefix}Planos de Manutenção — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    _header_row(ws, cols)

    for i, r in enumerate(planos, 3):
        ativo = bool(r.get("ativo"))
        fill = PatternFill("solid", fgColor="FFFFFF" if ativo else "F5F5F5")
        for col, val in enumerate([
            r.get("id", ""),
            r.get("descricao", ""),
            r.get("tipo", ""),
            r.get("periodicidade", ""),
            r.get("oficina", ""),
            r.get("procedimento", ""),
            "Sim" if ativo else "Não",
        ], 1):
            c = ws.cell(row=i, column=col, value=valor_seguro(val))
            c.fill = fill
            c.alignment = Alignment(vertical="center", wrap_text=True)
            c.border = _BORDA
        ws.row_dimensions[i].height = 18

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ── Exportação genérica (relatórios administrativos) ──────────────────────────

_PREFIXOS_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def valor_seguro(valor):
    """Neutraliza injeção de fórmula (CSV/Excel): texto que começa com = + - @ vira texto literal."""
    if isinstance(valor, str) and valor.startswith(_PREFIXOS_FORMULA):
        return "'" + valor
    return valor


def gerar_excel_tabela(titulo: str, colunas: list[tuple[str, int]], linhas: list[list], nome_aba: str = "Relatório",
                       subtitulo: str | None = None) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = nome_aba[:31]
    _titulo_row(ws, colunas, titulo)
    _header_row(ws, colunas)
    for i, linha in enumerate(linhas, 3):
        for col, val in enumerate(linha, 1):
            c = ws.cell(row=i, column=col, value=valor_seguro(val))
            c.alignment = Alignment(vertical="center", wrap_text=True)
            c.border = _BORDA
    if subtitulo:
        ws.cell(row=len(linhas) + 4, column=1, value=subtitulo).font = Font(italic=True, color="555555", size=9)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def gerar_csv_tabela(colunas: list[str], linhas: list[list]) -> io.BytesIO:
    texto = io.StringIO()
    w = csv.writer(texto, delimiter=";", lineterminator="\r\n")
    w.writerow(colunas)
    for linha in linhas:
        w.writerow([valor_seguro(v) for v in linha])
    # BOM para o Excel abrir acentos corretamente
    return io.BytesIO(("\ufeff" + texto.getvalue()).encode("utf-8"))
