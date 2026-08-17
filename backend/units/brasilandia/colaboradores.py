"""
Loader de colaboradores — Hospital Municipal Brasilândia.
Suporta três formatos, tentados nesta ordem:
  1. Rico por grupo (Escala_HMB_*.xlsx a partir de 2026-08): linhas por colaborador com
     Grupo/Colaborador/Função/Plantão-regime/Horário + colunas de dia (nem sempre
     começando em 1 — arquivo pode cobrir só uma quinzena). Ver `_eh_formato_rico_hmb`.
  2. Calendário (Escala_Maio_Brasiliana.xlsx): linhas por colaborador, colunas 1-31 com status P/F/FR...
  3. Tabela simples (colaboradores.xlsx): fallback com Turno/Regime/Horário.
"""
import glob
import os
import time
from datetime import datetime

import pandas as pd

from core import colaboradores_overlay as _overlay
from core.planejamento import detectar_paridade
from units.brasilandia.config import DATA_DIR

_colab_cache: dict = {"df": None, "ts": 0.0}
_COLAB_TTL = 600  # 10 minutos

PLANILHA_PREFERIDA = "Escala_"
STATUS_PRESENTES = frozenset({"P", "C", "M", "T", "D", "N"})

# ── Formato rico por grupo ──────────────────────────────────────────────────────
# Códigos confirmados na legenda da própria planilha Escala_HMB_* (aba "Premissas e
# Pendências", item 12): "P = presença; INT = integração; FÉR = férias; PC = posição
# em contratação/cobertura pendente; vazio = descanso." INT e FÉR não contam como
# presença disponível pra recomendação — dia de integração não é uma escala normal,
# e férias é ausência. PC nem chega a aparecer numa linha de colaborador real: as
# linhas onde ele aparece são vagas/contratações pendentes, filtradas antes disso.
_CODIGOS_PRESENCA_HMB = frozenset({"P"})

# Termos que identificam uma linha como vaga/posição em aberto, não um colaborador
# real — confirmado com dado real: "Em processo de contratação", "Cobertura
# pendente – noturno par".
_MARCADORES_VAGA_HMB = ("em processo de contratacao", "cobertura pendente")


def _eh_vazio(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def _eh_formato_rico_hmb(df_raw) -> bool:
    """Detecta o novo formato pela combinação 'grupo' + 'plantao'/'regime' na mesma
    linha de cabeçalho, seguida de uma linha com números de dia (não necessariamente
    começando em 1 — o arquivo pode cobrir só uma quinzena)."""
    for r in range(min(6, len(df_raw) - 1)):
        row_vals = [str(v).strip().lower() if not _eh_vazio(v) else "" for v in df_raw.iloc[r]]
        tem_grupo = any("grupo" in v for v in row_vals)
        tem_regime = any("plantao" in v or "regime" in v for v in row_vals)
        if not (tem_grupo and tem_regime):
            continue
        prox = df_raw.iloc[r + 1]
        n_dias = sum(1 for v in prox if not _eh_vazio(v) and _eh_numero_dia(v))
        if n_dias >= 3:
            return True
    return False


def _eh_numero_dia(v) -> bool:
    try:
        d = int(float(str(v).strip()))
        return 1 <= d <= 31
    except Exception:
        return False


def _parse_plantao_regime_hmb(texto: str) -> tuple[str, str, str, bool]:
    """Extrai (turno, regime, tipo_posto, provisorio) de um texto livre como
    'Diurno par', 'Folguista diurno – provisório ímpar', 'Noturno par – provisório',
    'Folguista volante – provisório diurno par', 'Regime comercial'.
    Reaproveita detectar_paridade() (já testado contra falso-positivo tipo
    'PARTIDA' conter 'PAR') em vez de reimplementar a mesma checagem aqui."""
    t = texto.lower()
    if "noturno" in t:
        turno = "Noturno"
    elif "diurno" in t:
        turno = "Diurno"
    elif "comercial" in t:
        turno = "Administrativo"
    else:
        turno = "Diurno"

    paridade = detectar_paridade(texto)
    regime = {"PAR": "Par", "IMPAR": "Ímpar"}.get(paridade, "Fixo")

    if "folguista" in t:
        tipo_posto = "folguista"
    elif "volante" in t:
        tipo_posto = "volante"
    elif "reserva" in t:
        tipo_posto = "reserva"
    elif "comercial" in t:
        tipo_posto = "comercial"
    else:
        tipo_posto = "titular"

    provisorio = "provisorio" in t.replace("ó", "o")

    return turno, regime, tipo_posto, provisorio


def _parse_formato_rico_hmb(df_raw) -> pd.DataFrame | None:
    header_row = None
    for r in range(min(6, len(df_raw) - 1)):
        row_vals = [str(v).strip().lower() if not _eh_vazio(v) else "" for v in df_raw.iloc[r]]
        if any("grupo" in v for v in row_vals) and any("plantao" in v or "regime" in v for v in row_vals):
            header_row = r
            break
    if header_row is None:
        return None

    col_map = {}
    for j in range(df_raw.shape[1]):
        cell = df_raw.iloc[header_row, j]
        if _eh_vazio(cell):
            continue
        norm = str(cell).strip().lower()
        if "grupo" in norm:
            col_map["grupo"] = j
        elif "colaborador" in norm:
            col_map["nome"] = j
        elif norm == "funcao" or "função" in str(cell).lower():
            col_map["funcao"] = j
        elif "plantao" in norm or "regime" in norm:
            col_map["plantao_regime"] = j
        elif "horario" in norm or "horário" in str(cell).lower():
            col_map["horario"] = j

    if "nome" not in col_map:
        return None

    # linha de dias fica logo abaixo do cabeçalho de rótulos
    dia_row = header_row + 1
    dia_col: dict[int, int] = {}
    for j in range(df_raw.shape[1]):
        cell = df_raw.iloc[dia_row, j]
        if not _eh_vazio(cell) and _eh_numero_dia(cell):
            dia_col[int(float(str(cell).strip()))] = j

    if not dia_col:
        return None

    rows = []
    for i in range(dia_row + 1, len(df_raw)):
        cell_nome = df_raw.iloc[i, col_map["nome"]]
        if _eh_vazio(cell_nome) or not isinstance(cell_nome, str):
            continue
        nome = cell_nome.strip()
        if not nome or nome.lower() == "nan":
            continue

        nome_norm = nome.lower().replace("ç", "c").replace("ã", "a").replace("õ", "o")
        if any(marcador in nome_norm for marcador in _MARCADORES_VAGA_HMB):
            continue  # vaga/posição em aberto — não é um colaborador real

        grupo = str(df_raw.iloc[i, col_map.get("grupo")] or "").strip() if "grupo" in col_map else ""
        funcao = str(df_raw.iloc[i, col_map.get("funcao")] or "").strip() if "funcao" in col_map else ""
        plantao_regime_raw = str(df_raw.iloc[i, col_map.get("plantao_regime")] or "").strip() if "plantao_regime" in col_map else ""
        horario = str(df_raw.iloc[i, col_map.get("horario")] or "").strip() if "horario" in col_map else ""

        if not funcao or funcao.lower() == "nan":
            continue  # sem função = linha vazia/rodapé, não colaborador

        turno, regime, tipo_posto, provisorio = _parse_plantao_regime_hmb(plantao_regime_raw)

        dias_plantao = {}
        for dia, col_idx in dia_col.items():
            codigo = str(df_raw.iloc[i, col_idx] or "").strip().upper()
            dias_plantao[dia] = "P" if codigo in _CODIGOS_PRESENCA_HMB else "F"

        rows.append({
            "funcionario": nome,
            "cargo": funcao,
            "grupo": grupo,
            "turno": turno,
            "regime": regime,
            "tipo_posto": tipo_posto,
            "provisorio": provisorio,
            "horario": horario,
            "dias_plantao": dias_plantao,
        })

    return pd.DataFrame(rows).reset_index(drop=True) if rows else None


def _normalizar_status(val) -> str:
    if val is None:
        return "F"
    if isinstance(val, float) and pd.isna(val):
        return "F"
    s = str(val).strip().upper()
    return "F" if not s or s == "NAN" else s


def _norm_text(text: str) -> str:
    return (
        text.lower()
        .replace("ã", "a").replace("á", "a").replace("â", "a")
        .replace("ç", "c").replace("é", "e").replace("ê", "e")
        .replace("í", "i").replace("ó", "o").replace("ô", "o")
        .replace("ú", "u").replace("ü", "u")
    )


def _contar_colunas_dia_calendario(df_raw) -> int:
    """Conta colunas com dias (1-31) escaneando as primeiras linhas."""
    for row_idx in range(min(10, len(df_raw))):
        n = 0
        for col_idx in range(5, min(df_raw.shape[1], 45)):
            val = df_raw.iloc[row_idx, col_idx]
            try:
                d = int(float(val))
                if 1 <= d <= 31:
                    n += 1
            except Exception:
                pass
        if n >= 4:
            return n
    return 0


def _eh_formato_calendario(df_raw) -> bool:
    return df_raw.shape[1] >= 12 and _contar_colunas_dia_calendario(df_raw) >= 4


def _detectar_colunas_escala(df_raw) -> dict:
    _NOMES = {"nome", "funcionario", "colaborador", "servidor", "diarista"}
    _CARGOS = {"funcao", "cargo", "funcao/cargo"}
    _PLANTAO = {"plantao", "plantaoo", "plant"}
    _HORARIO = {"horario", "hora", "carga horaria"}

    # Detecta a linha de cabeçalho: primeira com >= 10 dias ou com keyword "nome"/"cargo"
    header_row = 0
    for r in range(min(10, len(df_raw))):
        row_vals = df_raw.iloc[r].tolist()
        n_dias, has_kw = 0, False
        for v in row_vals:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                continue
            s = str(v).strip()
            norm = _norm_text(s)
            if norm in _NOMES or norm in _CARGOS:
                has_kw = True
            try:
                d = int(float(s))
                if 1 <= d <= 31:
                    n_dias += 1
            except Exception:
                pass
        if n_dias >= 10 or has_kw:
            header_row = r
            break

    col_map: dict = {"dias": {}, "header_row": header_row}
    for j in range(df_raw.shape[1]):
        cell = df_raw.iloc[header_row, j]
        if cell is None or (isinstance(cell, float) and pd.isna(cell)):
            continue
        raw = str(cell).strip()
        norm = _norm_text(raw)
        if norm in _NOMES:
            col_map.setdefault("nome", j)
        elif norm in _CARGOS or norm.startswith("fun"):
            col_map.setdefault("cargo", j)
        elif norm in _PLANTAO or norm.startswith("plant"):
            col_map.setdefault("plantao", j)
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


def _parse_plantao_br(p: str) -> tuple[str, str]:
    """Extrai (turno, regime) de 'Diurno - Ímpar', 'Noturno - Par', 'Diurno', etc."""
    pts = [x.strip() for x in str(p).split("-")]
    turno = pts[0].strip().capitalize()
    if len(pts) > 1:
        r = _norm_text(pts[1])
        if "impar" in r:
            regime = "Ímpar"
        elif "par" in r:
            regime = "Par"
        else:
            regime = pts[1].strip().capitalize()
    else:
        regime = "Fixo"
    return turno, regime


def _parse_calendario(df_raw):
    col_map = _detectar_colunas_escala(df_raw)
    col_nome = col_map["nome"]
    col_cargo = col_map["cargo"]
    col_horario = col_map["horario"]
    col_plantao = col_map.get("plantao")  # presente apenas no novo formato
    dia_col = col_map["dias"]
    data_start = col_map.get("header_row", 0) + 1

    _SEPARADORES = {"DIURNO": "Diurno", "NOTURNO": "Noturno"}
    rows = []
    turno_atual = "Diurno"

    for i in range(data_start, len(df_raw)):
        # Separadores DIURNO/NOTURNO na col 0 (formato antigo ESCALA DE FOLGA)
        cell_col0 = df_raw.iloc[i, 0]
        if isinstance(cell_col0, str) and cell_col0.strip().upper() in _SEPARADORES:
            turno_atual = _SEPARADORES[cell_col0.strip().upper()]
            continue

        cell_nome = df_raw.iloc[i, col_nome]
        if not isinstance(cell_nome, str) or not cell_nome.strip():
            continue
        nome_strip = cell_nome.strip()

        if nome_strip.upper() in _SEPARADORES:
            turno_atual = _SEPARADORES[nome_strip.upper()]
            continue

        cargo_cell = df_raw.iloc[i, col_cargo]
        cargo = str(cargo_cell or "").strip()
        if not cargo or cargo.lower() in ("nan", ""):
            continue

        # Novo formato: Plantão define turno e regime
        if col_plantao is not None:
            plantao_raw = str(df_raw.iloc[i, col_plantao] or "").strip()
            if not plantao_raw or plantao_raw.lower() == "nan":
                continue  # linha de legenda/rodapé sem plantão → ignorar
            turno_atual, regime = _parse_plantao_br(plantao_raw)
        else:
            regime = "Fixo"  # formato antigo: regime sempre Fixo

        horario = str(df_raw.iloc[i, col_horario] or "").strip()
        if horario.lower() == "nan":
            horario = ""

        dias_plantao = {dia: _normalizar_status(df_raw.iloc[i, col_idx]) for dia, col_idx in dia_col.items()}
        rows.append({
            "funcionario": nome_strip,
            "cargo": cargo,
            "turno": turno_atual,
            "regime": regime,
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
    meses_pt = {
        1: "janeiro", 2: "fevereiro", 3: "marco", 4: "abril", 5: "maio",
        6: "junho", 7: "julho", 8: "agosto", 9: "setembro", 10: "outubro",
        11: "novembro", 12: "dezembro",
    }
    mes_atual = meses_pt[datetime.now().month]

    all_xlsx = glob.glob(os.path.join(DATA_DIR, "*.xlsx"))
    # Case-insensitive: inclui "Escala_*" e "ESCALA DE FOLGA*"
    escalas = [f for f in all_xlsx if "escala" in os.path.basename(f).lower()]

    # Entre as escalas do mês atual, usa a mais recente (mtime) — evita depender da
    # ordem não garantida do glob() e prioriza naturalmente um arquivo novo (ex: uma
    # quinzena atualizada) sobre um antigo do mesmo mês.
    escalas_mes_atual = [
        f for f in escalas
        if mes_atual in _norm_text(os.path.basename(f)) or mes_atual.replace("ç", "c").replace("ã", "a") in _norm_text(os.path.basename(f))
    ]
    if escalas_mes_atual:
        return max(escalas_mes_atual, key=os.path.getmtime)

    # Fallback: escala mais recente
    if escalas:
        return max(escalas, key=os.path.getmtime)

    # Último fallback: colaboradores*.xlsx
    colabs = [f for f in all_xlsx if "colaborador" in os.path.basename(f).lower()]
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
    """Detecta o arquivo e formato da escala e retorna DataFrame com colaboradores. Cache 10 min."""
    if _colab_cache["df"] is not None and time.time() - _colab_cache["ts"] < _COLAB_TTL:
        return _colab_cache["df"]

    path = _selecionar_arquivo()
    if not path or not os.path.exists(path):
        print(f"[BR] AVISO: nenhuma planilha de colaboradores em {DATA_DIR}")
        return None

    xl = pd.ExcelFile(path, engine="openpyxl")
    sheet = _selecionar_aba(xl)
    df_raw = pd.read_excel(path, sheet_name=sheet, header=None, engine="openpyxl")

    if _eh_formato_rico_hmb(df_raw):
        df = _parse_formato_rico_hmb(df_raw)
        modo = "rico/por-grupo"
        if df is None or df.empty:
            df = None  # layout não bate com o esperado, não arrisca cair num parser errado
    elif _eh_formato_calendario(df_raw):
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

    for col, default in (("bloqueado", False), ("aviso", None)):
        if col not in df.columns:
            df[col] = default
    df["aviso"] = df["aviso"].astype(object).where(df["aviso"].notna(), None)

    df = _overlay.aplicar_overlay(df, DATA_DIR)

    print(f"[BR] colaboradores OK | {path} | aba={sheet!r} | modo={modo} | {len(df)} pessoas")
    _colab_cache["df"] = df
    _colab_cache["ts"] = time.time()
    return df


def invalidar_cache() -> None:
    """Força o próximo carregar_colaboradores() a reler o Excel + overlay do disco."""
    _colab_cache["df"] = None
    _colab_cache["ts"] = 0.0


def esta_disponivel(row, data_os) -> bool:
    """Brasilândia verifica status por dia no calendário; fallback Par/Ímpar.
    Colaborador bloqueado (aptidão pendente) nunca está disponível, mesmo com
    plantão agendado no dia — mesma regra da unidade Hetrin."""
    if row.get("bloqueado"):
        return False

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
