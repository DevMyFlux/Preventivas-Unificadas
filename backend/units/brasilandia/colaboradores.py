"""
Loader de colaboradores — Hospital Municipal Brasilândia.
Suporta dois formatos:
  1. Calendário (Escala_Maio_Brasiliana.xlsx): linhas por colaborador, colunas 1-31 com status P/F/FR...
  2. Tabela simples (colaboradores.xlsx): fallback com Turno/Regime/Horário.
"""
import glob
import os
from datetime import datetime

import pandas as pd

from units.brasilandia.config import DATA_DIR

PLANILHA_PREFERIDA = "Escala_"
STATUS_PRESENTES = frozenset({"P", "C", "M", "T", "D", "N"})


def _normalizar_status(val) -> str:
    if val is None:
        return "F"
    if isinstance(val, float) and pd.isna(val):
        return "F"
    s = str(val).strip().upper()
    return "F" if not s or s == "NAN" else s


def _contar_colunas_dia_calendario(df_raw) -> int:
    n = 0
    for col_idx in range(5, min(df_raw.shape[1], 45)):
        val = df_raw.iloc[0, col_idx]
        try:
            d = int(float(val))
            if 1 <= d <= 31:
                n += 1
        except Exception:
            pass
    return n


def _eh_formato_calendario(df_raw) -> bool:
    return df_raw.shape[1] >= 12 and _contar_colunas_dia_calendario(df_raw) >= 4


def _detectar_colunas_escala(df_raw) -> dict:
    _NOMES = {"nome", "funcionario", "colaborador", "servidor"}
    _CARGOS = {"funcao", "cargo", "funcao/cargo"}
    _HORARIO = {"horario", "hora", "carga horaria"}

    def _norm(text: str) -> str:
        return (
            text.lower()
            .replace("ã", "a").replace("á", "a").replace("â", "a")
            .replace("ç", "c").replace("é", "e").replace("ê", "e")
            .replace("í", "i").replace("ó", "o").replace("ô", "o")
            .replace("ú", "u").replace("ü", "u")
        )

    col_map: dict = {"dias": {}}
    for j in range(df_raw.shape[1]):
        cell = df_raw.iloc[0, j]
        if cell is None or (isinstance(cell, float) and pd.isna(cell)):
            continue
        raw = str(cell).strip()
        norm = _norm(raw)
        if norm in _NOMES:
            col_map.setdefault("nome", j)
        elif norm in _CARGOS or norm.startswith("fun"):
            col_map.setdefault("cargo", j)
        elif norm in _HORARIO or "horario" in norm or "horário" in raw.lower():
            col_map.setdefault("horario", j)
        else:
            try:
                d = int(float(raw))
                if 1 <= d <= 31:
                    col_map["dias"][d] = j
            except Exception:
                pass

    col_map.setdefault("nome", 0)
    col_map.setdefault("cargo", 2)
    col_map.setdefault("horario", 4)
    return col_map


def _parse_calendario(df_raw):
    col_map = _detectar_colunas_escala(df_raw)
    col_nome = col_map["nome"]
    col_cargo = col_map["cargo"]
    col_horario = col_map["horario"]
    dia_col = col_map["dias"]

    _SEPARADORES = {"DIURNO": "Diurno", "NOTURNO": "Noturno"}
    rows = []
    turno_atual = "Diurno"

    for i in range(1, len(df_raw)):
        cell_nome = df_raw.iloc[i, col_nome]
        if not isinstance(cell_nome, str) or not cell_nome.strip():
            continue
        nome_strip = cell_nome.strip()
        nome_upper = nome_strip.upper()

        if nome_upper in _SEPARADORES:
            turno_atual = _SEPARADORES[nome_upper]
            continue

        cargo_cell = df_raw.iloc[i, col_cargo]
        cargo = str(cargo_cell or "").strip()
        if not cargo or cargo.lower() in ("nan", ""):
            continue

        horario = str(df_raw.iloc[i, col_horario] or "").strip()
        if horario.lower() == "nan":
            horario = ""

        dias_plantao = {dia: _normalizar_status(df_raw.iloc[i, col_idx]) for dia, col_idx in dia_col.items()}
        rows.append({
            "funcionario": nome_strip,
            "cargo": cargo,
            "turno": turno_atual,
            "regime": "Fixo",
            "horario": horario,
            "dias_plantao": dias_plantao,
        })

    return pd.DataFrame(rows).reset_index(drop=True) if rows else None


def _parse_tabela_simples(df_raw):
    if df_raw.shape[0] < 2 or df_raw.shape[1] < 2:
        return None

    col_map = {}
    for j in range(df_raw.shape[1]):
        h = str(df_raw.iloc[0, j] if not pd.isna(df_raw.iloc[0, j]) else "").strip().lower()
        h = h.replace("í", "i").replace("ã", "a").replace("ç", "c")
        if h in ("funcionario", "nome", "colaborador"):
            col_map.setdefault("funcionario", j)
        elif h in ("cargo", "funcao", "funcao/cargo"):
            col_map.setdefault("cargo", j)
        elif h == "turno":
            col_map.setdefault("turno", j)
        elif h in ("regime", "plantao"):
            col_map.setdefault("regime", j)
        elif h == "horario":
            col_map.setdefault("horario", j)

    if "funcionario" not in col_map or "cargo" not in col_map:
        return None

    rows = []
    fi, fc = col_map["funcionario"], col_map["cargo"]
    ft, fr, fh = col_map.get("turno"), col_map.get("regime"), col_map.get("horario")

    for i in range(1, len(df_raw)):
        nome = df_raw.iloc[i, fi]
        if pd.isna(nome):
            continue
        nome = str(nome).strip()
        if not nome or nome.lower() == "nan":
            continue
        cargo = str(df_raw.iloc[i, fc] or "").strip()
        if not cargo or cargo.lower() == "nan":
            continue

        turno = "Diurno"
        if ft is not None:
            t = str(df_raw.iloc[i, ft] or "").strip()
            if t and t.lower() != "nan":
                turno = "Diurno" if t.lower().startswith("diur") else ("Noturno" if t.lower().startswith("not") else t)

        regime = "Fixo"
        if fr is not None:
            r = str(df_raw.iloc[i, fr] or "").strip()
            if r and r.lower() != "nan":
                regime = r

        horario = ""
        if fh is not None:
            horario = str(df_raw.iloc[i, fh] or "").strip()
            if horario.lower() == "nan":
                horario = ""

        rows.append({
            "funcionario": nome, "cargo": cargo, "turno": turno,
            "regime": regime, "horario": horario, "dias_plantao": {},
        })

    return pd.DataFrame(rows).reset_index(drop=True) if rows else None


def _selecionar_arquivo() -> str | None:
    # Prefere arquivos de escala (Escala_*.xlsx)
    escalas = sorted(glob.glob(os.path.join(DATA_DIR, "Escala_*.xlsx")), reverse=True)
    if escalas:
        return escalas[0]
    # Fallback para colaboradores*.xlsx
    colabs = glob.glob(os.path.join(DATA_DIR, "colaboradores*.xlsx"))
    return max(colabs, key=os.path.basename) if colabs else None


def _selecionar_aba(xl: pd.ExcelFile) -> str:
    meses_pt = {
        1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril", 5: "maio",
        6: "junho", 7: "julho", 8: "agosto", 9: "setembro", 10: "outubro",
        11: "novembro", 12: "dezembro",
    }
    mes_atual = meses_pt[datetime.now().month]

    for s in xl.sheet_names:
        if "escala" in s.lower() and mes_atual in s.lower():
            return s
    for s in xl.sheet_names:
        if mes_atual in s.lower():
            return s
    for s in xl.sheet_names:
        if "colaborador" in s.lower():
            return s
    return xl.sheet_names[0]


def carregar_colaboradores():
    """Detecta o arquivo e formato da escala e retorna DataFrame com colaboradores."""
    path = _selecionar_arquivo()
    if not path or not os.path.exists(path):
        print(f"[BR] AVISO: nenhuma planilha de colaboradores em {DATA_DIR}")
        return None

    xl = pd.ExcelFile(path, engine="openpyxl")
    sheet = _selecionar_aba(xl)
    df_raw = pd.read_excel(path, sheet_name=sheet, header=None, engine="openpyxl")

    if _eh_formato_calendario(df_raw):
        df = _parse_calendario(df_raw)
        modo = "calendario"
        if df is None or df.empty:
            df = _parse_tabela_simples(df_raw)
            modo = "tabela_simples (fallback)"
    else:
        df = _parse_tabela_simples(df_raw)
        modo = "tabela_simples"
        if df is None or df.empty:
            df = _parse_calendario(df_raw)
            modo = "calendario (fallback)"

    if df is None or df.empty:
        print(f"[BR] ERRO: nenhuma linha válida | {path} | aba={sheet!r}")
        return None

    print(f"[BR] colaboradores OK | {path} | aba={sheet!r} | modo={modo} | {len(df)} pessoas")
    return df


def esta_disponivel(row, data_os) -> bool:
    """Brasilândia verifica status por dia no calendário; fallback Par/Ímpar."""
    dias_plantao = row.get("dias_plantao", {})
    dia = data_os.day
    if dias_plantao:
        status = dias_plantao.get(dia, "F")
        return status in STATUS_PRESENTES
    regime = str(row.get("regime", "")).strip().lower()
    if regime in ("fixo", "nan", ""):
        return True
    if regime in ("par", "pares"):
        return dia % 2 == 0
    if regime in ("ímpar", "impar", "ímpares", "impares"):
        return dia % 2 != 0
    return True
