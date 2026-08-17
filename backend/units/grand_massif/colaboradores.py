"""
Loader de colaboradores — Grand Massif Trindade.
Suporta três formatos, tentados nesta ordem:
  1. Rico/12x36 (Escala_HETRIN_*.xlsx a partir de 2026-08): linhas por colaborador com
     Equipe/Função contratual/Cargo operacional/Turno/Status/Observação + colunas 1-31.
     Tem coluna "Status" própria (Apto/Condicionado/Transição/...) que pode bloquear a
     recomendação independente do código do dia — ver `_CODIGOS_FORMATO_RICO`.
  2. Calendário (Escala_*.xlsx antigas): linhas por colaborador, colunas 1-31 com status P/F/N...
     Coluna "Plantão" fornece turno (Diurno/Noturno) e regime (Par/Ímpar/Fixo).
  3. Tabela simples (colaboradores*.xlsx): fallback com coluna Plantão para regime Par/Ímpar/Fixo.
"""
import glob
import os
import time
import unicodedata
from datetime import datetime

import pandas as pd

from core import colaboradores_overlay as _overlay
from units.grand_massif.config import DATA_DIR

_colab_cache: dict = {"df": None, "ts": 0.0}
_COLAB_TTL = 600  # 10 minutos

STATUS_PRESENTES = frozenset({"P", "N", "C", "M", "T", "D"})

# ── Formato rico/12x36 ──────────────────────────────────────────────────────────
# Códigos e significado extraídos da própria legenda da planilha Escala_HETRIN_*
# (aba principal, linhas "Legenda"), em 2026-08. Note que o código "T" aqui significa
# "Transição - não escalar" — o OPOSTO do "T" do formato calendário antigo (linha 22
# acima, onde T="trabalhando"). Por isso este formato usa seu próprio dicionário,
# nunca STATUS_PRESENTES, para não colidir os dois significados.
_CODIGOS_FORMATO_RICO = {
    "P":   True,   # Plantão diurno
    "N":   True,   # Plantão noturno
    "D36": False,  # Descanso de 36h
    "F":   False,  # Folga administrativa
    "V":   False,  # Vaga/plantão descoberto
    "RES": False,  # Reserva/folguista
    "T":   False,  # Transição - não escalar
    "C":   False,  # Condicionado à regularização
    "ADM": False,  # Pré-admissão / não escalado
}

# Status do colaborador (coluna "Status") que bloqueiam recomendação mesmo que o
# código do dia mostre presença agendada — confirmado com dado real: Wellington de
# Souza Brito aparece com plantões N/D36 normais, mas o Status diz "Condicionado"
# e a Observação "Bloqueado até comprovação NR-10 e autorização". Os demais status
# (Transição, Admissão DD/MM) já se resolvem sozinhos pelo código do dia — antes da
# data de admissão o código é ADM (não presente); depois da transição o código vira
# V (não presente) — não precisam de bloqueio adicional aqui.
_STATUS_BLOQUEIAM = frozenset({"condicionado"})


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


# ── Formato rico/12x36 ──────────────────────────────────────────────────────────

def _eh_formato_rico(df_raw) -> bool:
    """Detecta o novo formato pela combinação de cabeçalhos que só ele tem:
    'equipe'/'colaborador' + 'status' + 'observa' na mesma linha, seguida de
    colunas de dia. Não confunde com o formato calendário antigo (que não tem
    coluna Status nem Observação dedicadas)."""
    for r in range(min(10, len(df_raw))):
        row_vals = [_ascii_lower(str(v)) if v is not None else "" for v in df_raw.iloc[r]]
        tem_equipe_ou_colab = any("equipe" in v or "colaborador" in v for v in row_vals)
        tem_status = any(v.strip() == "status" for v in row_vals)
        tem_observacao = any("observa" in v for v in row_vals)
        if tem_equipe_ou_colab and tem_status and tem_observacao:
            return True
    return False


def _normalizar_turno_rico(turno_raw: str) -> str:
    """'Diurno alternado' -> 'Diurno', 'Noturno alternado' -> 'Noturno', mantém
    'Administrativo'/'Reserva' como estão — calcular_score() compara turno com
    igualdade exata em 'diurno'/'noturno', então precisa chegar limpo."""
    t = _ascii_lower(turno_raw)
    if t.startswith("diurno"):
        return "Diurno"
    if t.startswith("noturno"):
        return "Noturno"
    return turno_raw.strip().capitalize() if turno_raw else ""


def _parse_formato_rico_hetrin(df_raw) -> pd.DataFrame | None:
    header_row = None
    for r in range(min(10, len(df_raw))):
        row_vals = [_ascii_lower(str(v)) if v is not None else "" for v in df_raw.iloc[r]]
        if any("equipe" in v for v in row_vals) and any(v.strip() == "status" for v in row_vals):
            header_row = r
            break
    if header_row is None:
        return None

    col_map = {}
    dia_col: dict[int, int] = {}
    for j in range(df_raw.shape[1]):
        cell = df_raw.iloc[header_row, j]
        if cell is None or (isinstance(cell, float) and pd.isna(cell)):
            continue
        norm = _ascii_lower(str(cell).strip())
        if "equipe" in norm:
            col_map["equipe"] = j
        elif "colaborador" in norm:
            col_map["nome"] = j
        elif "funcao contratual" in norm:
            col_map["funcao_contratual"] = j
        elif "cargo operacional" in norm:
            col_map["cargo_operacional"] = j
        elif norm == "turno":
            col_map["turno"] = j
        elif "horario" in norm:
            col_map["horario"] = j
        elif norm == "status":
            col_map["status"] = j
        elif "observa" in norm:
            col_map["observacao"] = j
        else:
            try:
                d = int(float(str(cell).strip()))
                if 1 <= d <= 31:
                    dia_col[d] = j
            except Exception:
                pass

    if "nome" not in col_map or not dia_col:
        return None

    _MARCADORES_FIM = {"legenda", "nota", "atencao", "atenção"}

    rows = []
    for i in range(header_row + 1, len(df_raw)):
        linha_vazia = all(
            v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""
            for v in df_raw.iloc[i]
        )
        equipe_cell = df_raw.iloc[i, col_map.get("equipe")] if "equipe" in col_map else None
        equipe_norm = _ascii_lower(str(equipe_cell).strip()) if equipe_cell is not None else ""
        if (linha_vazia and rows) or equipe_norm in _MARCADORES_FIM:
            # linha em branco após já termos colaboradores reais, ou marcador de
            # Legenda/Nota/Atenção — a partir daqui é rodapé, não mais gente.
            break

        cell_nome = df_raw.iloc[i, col_map["nome"]]
        if not isinstance(cell_nome, str) or not cell_nome.strip():
            continue
        nome = cell_nome.strip()
        if nome.upper() in ("NAN", "") or "legenda" in nome.lower():
            continue

        status_raw = str(df_raw.iloc[i, col_map.get("status")] or "").strip() if "status" in col_map else ""
        status_norm = _ascii_lower(status_raw)

        # Linha de vaga em aberto (sem pessoa real) — não é um colaborador, não entra na lista.
        if nome.upper().startswith("VAGA") or status_norm == "vaga":
            continue

        cargo = str(df_raw.iloc[i, col_map.get("cargo_operacional", col_map["nome"])] or "").strip()
        funcao_contratual = str(df_raw.iloc[i, col_map.get("funcao_contratual")] or "").strip() if "funcao_contratual" in col_map else ""
        turno_raw = str(df_raw.iloc[i, col_map.get("turno")] or "").strip() if "turno" in col_map else ""
        horario = str(df_raw.iloc[i, col_map.get("horario")] or "").strip() if "horario" in col_map else ""
        observacao = str(df_raw.iloc[i, col_map.get("observacao")] or "").strip() if "observacao" in col_map else ""
        equipe = str(df_raw.iloc[i, col_map.get("equipe")] or "").strip() if "equipe" in col_map else ""

        dias_plantao = {}
        for dia, col_idx in dia_col.items():
            codigo = str(df_raw.iloc[i, col_idx] or "").strip().upper()
            dias_plantao[dia] = "P" if _CODIGOS_FORMATO_RICO.get(codigo, False) else "F"

        bloqueado = status_norm in _STATUS_BLOQUEIAM
        aviso = None
        if bloqueado:
            aviso = f"Bloqueado — status \"{status_raw}\"" + (f": {observacao}" if observacao else ".")

        rows.append({
            "funcionario": nome,
            "cargo": cargo or funcao_contratual,
            "funcao_contratual": funcao_contratual,
            "turno": _normalizar_turno_rico(turno_raw),
            "regime": "",  # não há regime único aqui — a disponibilidade vem do calendário
            "horario": horario,
            "equipe": equipe,
            "status_planilha": status_raw,
            "bloqueado": bloqueado,
            "aviso": aviso,
            "dias_plantao": dias_plantao,
        })

    return pd.DataFrame(rows).reset_index(drop=True) if rows else None


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
    """Parse escala calendário — suporta formato com coluna Plantão e formato ESCALA DE FOLGA (DIURNO/NOTURNO)."""
    header_row = _detectar_header_calendario(df_raw)

    _NOMES = {"diarista", "funcionario", "funcionário", "nome", "colaborador"}
    _CARGOS = {"cargo", "funcao", "função", "funcao/cargo"}
    _PLANTAO = {"plantão", "plantao", "plant", "planta"}
    _HORARIO = {"horario", "horário", "hora", "carga horaria"}
    _SEPARADORES = {"DIURNO": "Diurno", "NOTURNO": "Noturno"}

    col_nome, col_cargo, col_plantao, col_horario = 2, 4, None, 6
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
    turno_atual = "Diurno"

    for i in range(header_row + 1, len(df_raw)):
        # Separadores DIURNO/NOTURNO na col 0 (formato ESCALA DE FOLGA)
        cell_col0 = df_raw.iloc[i, 0]
        if isinstance(cell_col0, str) and cell_col0.strip().upper() in _SEPARADORES:
            turno_atual = _SEPARADORES[cell_col0.strip().upper()]
            continue

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

        if col_plantao is not None:
            plantao_raw = str(df_raw.iloc[i, col_plantao] or "").strip()
            if not plantao_raw or plantao_raw.lower() == "nan":
                continue  # linha de legenda/rodapé → ignorar
            turno_atual, regime = _parse_plantao(plantao_raw)
        else:
            regime = "Fixo"  # formato ESCALA DE FOLGA: turno via separador, regime fixo

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
            "turno": turno_atual,
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


def _prefere_arquivo(a: str, b: str) -> str:
    """Escolhe entre dois candidatos do mesmo mês. NÃO usa mtime como critério —
    num deploy via git/Docker, o checkout normalmente grava a mesma data de
    modificação (ou uma ordem arbitrária) em todos os arquivos copiados juntos, então
    'o mais recente por mtime' deixa de significar 'o mais recente de verdade' assim
    que o app é implantado (confirmado: funcionava local, mas não em produção).
    Em vez disso, prefere o arquivo cujo conteúdo já é o formato rico/12x36 (mais
    novo por estrutura, não por metadado de sistema de arquivos)."""
    try:
        rico_a = _eh_formato_rico(pd.read_excel(a, sheet_name=0, header=None, engine="openpyxl"))
    except Exception:
        rico_a = False
    try:
        rico_b = _eh_formato_rico(pd.read_excel(b, sheet_name=0, header=None, engine="openpyxl"))
    except Exception:
        rico_b = False
    if rico_a != rico_b:
        return a if rico_a else b
    return max(a, b, key=os.path.getmtime)


def _selecionar_arquivo() -> str | None:
    mes_atual = _ascii_lower(_MESES_PT[datetime.now().month])
    all_xlsx = glob.glob(os.path.join(DATA_DIR, "*.xlsx"))

    # 1. Entre as Escala_*.xlsx com nome do mês atual, escolhe por conteúdo (formato
    # rico tem prioridade) — ver _prefere_arquivo — não por mtime.
    escalas = [f for f in all_xlsx if "escala" in os.path.basename(f).lower()]
    escalas_mes_atual = [f for f in escalas if mes_atual in _ascii_lower(os.path.basename(f))]
    if escalas_mes_atual:
        melhor = escalas_mes_atual[0]
        for f in escalas_mes_atual[1:]:
            melhor = _prefere_arquivo(melhor, f)
        return melhor
    if escalas:
        melhor = escalas[0]
        for f in escalas[1:]:
            melhor = _prefere_arquivo(melhor, f)
        return melhor

    # 2. Fallback: colaboradores*.xlsx mais recente
    colabs = [f for f in all_xlsx if "colaboradores" in os.path.basename(f).lower()]
    return max(colabs, key=os.path.basename) if colabs else None


def _selecionar_aba(xl: pd.ExcelFile, caminho: str = "") -> str:
    # 1. Tenta usar o mês do nome do arquivo (ex: Escala_Julho_2026_GM.xlsx → julho)
    nome_arq = _ascii_lower(os.path.basename(caminho))
    for mes in _MESES_PT.values():
        mes_norm = _ascii_lower(mes)
        if mes_norm in nome_arq:
            for s in xl.sheet_names:
                if mes_norm in _ascii_lower(s):
                    return s
            break  # mês encontrado no nome mas sem aba correspondente → usa mês atual

    # 2. Aba do mês atual
    mes_atual = _ascii_lower(_MESES_PT[datetime.now().month])
    for s in xl.sheet_names:
        if mes_atual in _ascii_lower(s):
            return s

    # 3. Última aba (mês mais recente)
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
    sheet = _selecionar_aba(xl, arquivo)
    df_raw = pd.read_excel(arquivo, sheet_name=sheet, header=None, engine="openpyxl")

    if _eh_formato_rico(df_raw):
        df = _parse_formato_rico_hetrin(df_raw)
        modo = "rico/12x36"
        if df is None or df.empty:
            df = None  # não tenta cair pros formatos antigos com esse layout, evita parse errado
    elif _tem_colunas_dia(df_raw):
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

    if df is not None and not df.empty:
        for col, default in (("bloqueado", False), ("aviso", None)):
            if col not in df.columns:
                df[col] = default
        # pandas guarda ausência como NaN (float) numa coluna object com tipos mistos —
        # json.dumps não recusa NaN, só emite o token literal `NaN`, que não é JSON
        # válido e quebra JSON.parse no frontend. Normaliza pra None de verdade aqui,
        # na única passagem, em vez de em cada endpoint que serializa colaborador.
        df["aviso"] = df["aviso"].astype(object).where(df["aviso"].notna(), None)

    if df is None or df.empty:
        print(f"[GM] ERRO: nenhuma linha válida | {arquivo} | aba={sheet!r}")
        return None

    df = _overlay.aplicar_overlay(df, DATA_DIR)

    print(f"[GM] colaboradores OK | {arquivo} | aba={sheet!r} | modo={modo} | {len(df)} pessoas")
    _colab_cache["df"] = df
    _colab_cache["ts"] = time.time()
    return df


def invalidar_cache() -> None:
    """Força o próximo carregar_colaboradores() a reler o Excel + overlay do disco."""
    _colab_cache["df"] = None
    _colab_cache["ts"] = 0.0


def esta_disponivel(row, data_os) -> bool:
    """Verifica disponibilidade: usa calendário diário se disponível, senão regime Par/Ímpar/Fixo.
    Colaborador bloqueado (ex: status "Condicionado" pendente de documentação) nunca está
    disponível, mesmo que o código do dia mostre plantão agendado — o bloqueio é sobre
    aptidão, não sobre escala."""
    if row.get("bloqueado"):
        return False

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
