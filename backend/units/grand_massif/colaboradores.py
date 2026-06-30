"""
Loader de colaboradores — Grand Massif Trindade.
Suporta dois formatos:
  1. Calendário (Escala_*.xlsx): linhas por colaborador, colunas 1-31 com status P/F/N...
     Coluna "Plantão" fornece turno (Diurno/Noturno) e regime (Par/Ímpar/Fixo).
  2. Tabela simples (colaboradores*.xlsx): fallback com coluna Plantão para regime Par/Ímpar/Fixo.
"""
import glob
import os
import time
import unicodedata
from datetime import datetime

import pandas as pd

from units.grand_massif.config import DATA_DIR

_colab_cache: dict = {"df": None, "ts": 0.0}
_COLAB_TTL = 600  # 10 minutos

STATUS_PRESENTES = frozenset({"P", "N", "C", "M", "T", "D"})


def _ascii_lower(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower()


def _normalizar_status(val) -> str:
    if val is None:
        return "F"
    if isinstance(val, float) and pd.isna(val):
        return "F"
    s = str(val).strip().upper()
    return "F" if not s or s == "NAN" else s


def _parse_plantao(p: str) -> tuple[str, str]:
    pts = [x.strip() for x in str(p).split("-")]
    turno = pts[0].capitalize()
    if len(pts) > 1:
        r = _ascii_lower(pts[1])
        if "impar" in r:
            regime = "Ímpar"
        elif "par" in r:
            regime = "Par"
        else:
            regime = pts[1].strip().capitalize()
    else:
        regime = "Fixo"
    return turno, regime


# ── Formato calendário ─────────────────────────────────────────────────────────

def _detectar_header_calendario(df_raw) -> int:
    """Detecta linha de cabeçalho pela presença de >= 5 colunas com números 1-31."""
    for r in range(min(12, len(df_raw))):
        n_dias = 0
        for j in range(5, min(df_raw.shape[1], 45)):
            cell = df_raw.iloc[r, j]
            if cell is None or (isinstance(cell, float) and pd.isna(cell)):
                continue
            try:
                d = int(float(str(cell).strip()))
                if 1 <= d <= 31:
                    n_dias += 1
            except Exception:
                pass
        if n_dias >= 5:
            return r
    return 6  # fallback


def _parse_calendario_gm(df_raw) -> pd.DataFrame | None:
    """Parse escala calendário do Grand Massif (Escala_*.xlsx)."""
    header_row = _detectar_header_calendario(df_raw)

    _NOMES = {"diarista", "funcionario", "funcionário", "nome", "colaborador"}
    _CARGOS = {"cargo", "funcao", "função", "funcao/cargo"}
    _PLANTAO = {"plantão", "plantao", "plant", "planta"}
    _HORARIO = {"horario", "horário", "hora", "carga horaria"}

    col_nome, col_cargo, col_plantao, col_horario = 2, 4, 5, 6
    dia_col: dict[int, int] = {}

    for j in range(df_raw.shape[1]):
        cell = df_raw.iloc[header_row, j]
        if cell is None or (isinstance(cell, float) and pd.isna(cell)):
            continue
        raw = str(cell).strip()
        norm = _ascii_lower(raw)
        if any(kw in norm for kw in _NOMES):
            col_nome = j
        elif any(kw in norm for kw in _CARGOS):
            col_cargo = j
        elif any(kw in norm for kw in _PLANTAO):
            col_plantao = j
        elif any(kw in norm for kw in _HORARIO):
            col_horario = j
        else:
            try:
                d = int(float(raw))
                if 1 <= d <= 31:
                    dia_col[d] = j
            except Exception:
                pass

    if not dia_col:
        return None

    rows = []
    for i in range(header_row + 1, len(df_raw)):
        cell_nome = df_raw.iloc[i, col_nome]
        if not isinstance(cell_nome, str) or not cell_nome.strip():
            continue
        nome = cell_nome.strip()
        if nome.upper() in ("NAN", ""):
            continue

        cargo_cell = df_raw.iloc[i, col_cargo]
        cargo = str(cargo_cell or "").strip()
        if not cargo or cargo.lower() in ("nan", ""):
            continue

        plantao_raw = str(df_raw.iloc[i, col_plantao] or "").strip()
        if not plantao_raw or plantao_raw.lower() == "nan":
            continue  # linhas sem Plantão são legenda/rodapé, não funcionários
        turno, regime = _parse_plantao(plantao_raw)

        horario = str(df_raw.iloc[i, col_horario] or "").strip()
        if horario.lower() == "nan":
            horario = ""

        dias_plantao = {
            dia: _normalizar_status(df_raw.iloc[i, col_idx])
            for dia, col_idx in dia_col.items()
        }
        rows.append({
            "funcionario": nome,
            "cargo": cargo,
            "turno": turno,
            "regime": regime,
            "horario": horario,
            "dias_plantao": dias_plantao,
        })

    return pd.DataFrame(rows).reset_index(drop=True) if rows else None


def _tem_colunas_dia(df_raw) -> bool:
    """Verifica se há >= 5 colunas de dia (1-31) — formato calendário."""
    for r in range(min(12, len(df_raw))):
        n = 0
        for j in range(5, min(df_raw.shape[1], 45)):
            cell = df_raw.iloc[r, j]
            if cell is None or (isinstance(cell, float) and pd.isna(cell)):
                continue
            try:
                d = int(float(str(cell).strip()))
                if 1 <= d <= 31:
                    n += 1
            except Exception:
                pass
        if n >= 5:
            return True
    return False


# ── Formato tabela simples (fallback) ─────────────────────────────────────────

def _detectar_estrutura(df_raw):
    KEYWORDS = {
        "funcionario": ["diarista", "funcionário", "funcionario", "nome"],
        "cargo": ["cargo"],
        "plantao": ["plantão", "plantao", "plant"],
        "horario": ["horário", "horario", "hor"],
    }
    FALLBACKS = {"funcionario": 2, "cargo": 4, "plantao": 5, "horario": 6}

    header_row = 6
    for i in range(min(12, len(df_raw))):
        row_vals = [str(v).strip().lower() for v in df_raw.iloc[i]]
        if "cargo" in row_vals:
            header_row = i
            break

    col_map = {}
    header_vals = [str(v).strip().lower() for v in df_raw.iloc[header_row]]
    for field, keywords in KEYWORDS.items():
        for col_idx, val in enumerate(header_vals):
            if any(kw in val for kw in keywords):
                if field not in col_map:
                    col_map[field] = col_idx
                    break
        if field not in col_map:
            col_map[field] = FALLBACKS[field]

    return header_row, col_map


def _parse_df_raw(df_raw):
    header_row, col_map = _detectar_estrutura(df_raw)
    data_start = header_row + 1

    cols = [col_map["funcionario"], col_map["cargo"], col_map["plantao"], col_map["horario"]]
    df = df_raw.iloc[data_start:, cols].copy()
    df.columns = ["funcionario", "cargo", "plantao", "horario"]
    df["funcionario"] = df["funcionario"].astype(str).str.strip()
    df["plantao"] = df["plantao"].astype(str).str.strip()
    df = df[df["plantao"].str.match(r"^(Diurno|Noturno)", na=False)]
    df = df[~df["funcionario"].str.lower().isin(["nan", "", "a ser contratado"])]

    df[["turno", "regime"]] = df["plantao"].apply(lambda p: pd.Series(_parse_plantao(p)))
    df["dias_plantao"] = [{}] * len(df)
    return df[["funcionario", "cargo", "turno", "regime", "horario", "dias_plantao"]].reset_index(drop=True)


# ── Seleção de arquivo e aba ───────────────────────────────────────────────────

_MESES_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril", 5: "maio",
    6: "junho", 7: "julho", 8: "agosto", 9: "setembro", 10: "outubro",
    11: "novembro", 12: "dezembro",
}


def _selecionar_arquivo() -> str | None:
    mes_atual = _ascii_lower(_MESES_PT[datetime.now().month])
    all_xlsx = glob.glob(os.path.join(DATA_DIR, "*.xlsx"))

    # 1. Prefere Escala_*.xlsx com nome do mês atual
    escalas = [f for f in all_xlsx if "escala" in os.path.basename(f).lower()]
    for f in escalas:
        if mes_atual in _ascii_lower(os.path.basename(f)):
            return f
    if escalas:
        return max(escalas, key=os.path.getmtime)

    # 2. Fallback: colaboradores*.xlsx mais recente
    colabs = [f for f in all_xlsx if "colaboradores" in os.path.basename(f).lower()]
    return max(colabs, key=os.path.basename) if colabs else None


def _selecionar_aba(xl: pd.ExcelFile) -> str:
    mes_atual = _MESES_PT[datetime.now().month]
    for s in xl.sheet_names:
        if mes_atual.lower() in s.lower():
            return s
    return xl.sheet_names[-1]


# ── API pública ────────────────────────────────────────────────────────────────

def carregar_colaboradores():
    """Carrega colaboradores. Prioriza Escala_*.xlsx (calendário) sobre colaboradores*.xlsx. Cache 10 min."""
    if _colab_cache["df"] is not None and time.time() - _colab_cache["ts"] < _COLAB_TTL:
        return _colab_cache["df"]

    arquivo = _selecionar_arquivo()
    if not arquivo or not os.path.exists(arquivo):
        print(f"[GM] AVISO: nenhuma planilha de colaboradores em {DATA_DIR}")
        return None

    xl = pd.ExcelFile(arquivo, engine="openpyxl")
    sheet = _selecionar_aba(xl)
    df_raw = pd.read_excel(arquivo, sheet_name=sheet, header=None, engine="openpyxl")

    if _tem_colunas_dia(df_raw):
        df = _parse_calendario_gm(df_raw)
        modo = "calendario"
        if df is None or df.empty:
            df = _parse_df_raw(df_raw)
            modo = "tabela_simples (fallback)"
    else:
        df = _parse_df_raw(df_raw)
        modo = "tabela_simples"
        if df is None or df.empty:
            df = _parse_calendario_gm(df_raw)
            modo = "calendario (fallback)"

    if df is None or df.empty:
        print(f"[GM] ERRO: nenhuma linha válida | {arquivo} | aba={sheet!r}")
        return None

    print(f"[GM] colaboradores OK | {arquivo} | aba={sheet!r} | modo={modo} | {len(df)} pessoas")
    _colab_cache["df"] = df
    _colab_cache["ts"] = time.time()
    return df


def esta_disponivel(row, data_os) -> bool:
    """Verifica disponibilidade: usa calendário diário se disponível, senão regime Par/Ímpar/Fixo."""
    dias_plantao = row.get("dias_plantao", {})
    if dias_plantao:
        status = dias_plantao.get(data_os.day, "F")
        return status in STATUS_PRESENTES

    # Fallback par/ímpar para planilhas sem calendário
    regime = str(row.get("regime", "")).strip().lower()
    if regime in ("fixo", "nan", ""):
        return True
    dia = data_os.day
    if regime in ("par", "pares"):
        return dia % 2 == 0
    if regime in ("ímpar", "impar", "ímpares", "impares"):
        return dia % 2 != 0
    return True
