"""
Loader de colaboradores — Grand Massif.
Formato: tabela simples com coluna Plantão (Diurno-Ímpar, Noturno-Par, etc.).
Seleciona a aba do mês atual; suporta versionamento mensal (colaboradores05_2026.xlsx).
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


def _ascii_lower(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower()


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


def carregar_colaboradores():
    """Carrega o colaboradores*.xlsx mais recente da pasta data/grand_massif. Cache 10 min."""
    if _colab_cache["df"] is not None and time.time() - _colab_cache["ts"] < _COLAB_TTL:
        return _colab_cache["df"]

    matches = glob.glob(os.path.join(DATA_DIR, "colaboradores*.xlsx"))
    if not matches:
        print(f"[GM] AVISO: nenhum colaboradores*.xlsx em {DATA_DIR}")
        return None
    arquivo = max(matches, key=os.path.basename)

    meses = {
        1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril", 5: "maio",
        6: "junho", 7: "julho", 8: "agosto", 9: "setembro", 10: "outubro",
        11: "novembro", 12: "dezembro",
    }
    mes_atual = meses[datetime.now().month]

    xl = pd.ExcelFile(arquivo, engine="openpyxl")
    sheet = next((s for s in xl.sheet_names if mes_atual.lower() in s.lower()), xl.sheet_names[-1])

    df_raw = pd.read_excel(arquivo, sheet_name=sheet, header=None, engine="openpyxl")
    df = _parse_df_raw(df_raw)
    print(f"[GM] colaboradores OK | {arquivo} | aba={sheet!r} | {len(df)} pessoas")
    _colab_cache["df"] = df
    _colab_cache["ts"] = time.time()
    return df


def esta_disponivel(row, data_os) -> bool:
    """Grand Massif usa regime Par/Ímpar/Fixo."""
    regime = str(row.get("regime", "")).strip().lower()
    if regime in ("fixo", "nan", ""):
        return True
    dia = data_os.day
    if regime in ("par", "pares"):
        return dia % 2 == 0
    if regime in ("ímpar", "impar", "ímpares", "impares"):
        return dia % 2 != 0
    return True
