"""
Persistência leve (JSON local, um arquivo por unidade) para os dois atributos de
colaborador que a aplicação edita: status (Ativo/Desligado) e habilidades.

O Excel continua sendo a fonte de verdade para nome/cargo/turno/regime/escala — este
overlay nunca escreve no Excel, só guarda o que não existe nele. Colaboradores nunca
são removidos fisicamente: "Desligado" é um status, não uma exclusão.
"""
import json
import os
import threading

_lock = threading.Lock()


def _arquivo(data_dir: str) -> str:
    return os.path.join(data_dir, "colaboradores_overlay.json")


def _chave(nome: str) -> str:
    return nome.strip().upper()


def carregar(data_dir: str) -> dict:
    caminho = _arquivo(data_dir)
    if not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _salvar(data_dir: str, dados: dict) -> None:
    caminho = _arquivo(data_dir)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, caminho)


def aplicar_overlay(df, data_dir: str):
    """Adiciona colunas 'status' e 'habilidades' ao DataFrame de colaboradores carregado
    do Excel, usando o overlay salvo. Colaborador sem entrada no overlay é Ativo, sem
    habilidades — o padrão de quem nunca foi editado pela aplicação.

    Também pode sobrescrever 'bloqueado'/'aviso' quando o overlay tem uma entrada
    explícita pra isso — usado quando a planilha de origem não tem coluna de Status
    própria (ex: formato calendário simples) mas ainda assim existe uma pendência real
    de aptidão (ex: autorização elétrica pendente) que precisa continuar bloqueando a
    recomendação. Sem entrada no overlay, mantém o que o parser já calculou (ex: o
    formato rico/12x36 já bloqueia sozinho via sua própria coluna Status)."""
    overlay = carregar(data_dir)
    status_col, habilidades_col, bloqueado_col, aviso_col = [], [], [], []
    tem_bloqueado_no_df = "bloqueado" in df.columns
    tem_aviso_no_df = "aviso" in df.columns
    for idx, nome in enumerate(df["funcionario"]):
        entry = overlay.get(_chave(nome), {})
        status_col.append(entry.get("status", "Ativo"))
        habilidades_col.append(list(entry.get("habilidades", [])))
        if "bloqueado" in entry:
            bloqueado_col.append(bool(entry["bloqueado"]))
            aviso_col.append(entry.get("aviso"))
        else:
            bloqueado_col.append(bool(df.iloc[idx]["bloqueado"]) if tem_bloqueado_no_df else False)
            aviso_col.append(df.iloc[idx]["aviso"] if tem_aviso_no_df else None)
    df = df.copy()
    df["status"] = status_col
    df["habilidades"] = habilidades_col
    df["bloqueado"] = bloqueado_col
    df["aviso"] = aviso_col
    # Atribuir uma lista Python com None misturado a string faz o pandas promover pra
    # NaN (float) silenciosamente — json.dumps não recusa NaN, só emite o token
    # literal `NaN`, que não é JSON válido e quebra JSON.parse no frontend. Mesmo bug
    # já visto (e corrigido) no parser da HETRIN; aqui reaparece porque esta função
    # reconstrói a coluna do zero via lista Python em vez de só copiar do DataFrame.
    df["aviso"] = df["aviso"].astype(object).where(df["aviso"].notna(), None)
    return df


def set_bloqueado(data_dir: str, nome: str, bloqueado: bool, aviso: str | None = None) -> None:
    """Marca (ou desmarca) um colaborador como bloqueado via overlay — pensado pra
    planilhas sem coluna de Status própria (formato calendário), onde a única forma de
    registrar uma pendência de aptidão (ex: autorização elétrica) é fora do Excel."""
    with _lock:
        dados = carregar(data_dir)
        entry = dados.setdefault(_chave(nome), {})
        entry["bloqueado"] = bloqueado
        if bloqueado and aviso:
            entry["aviso"] = aviso
        elif not bloqueado:
            entry.pop("aviso", None)
        _salvar(data_dir, dados)


def set_status(data_dir: str, nome: str, status: str) -> None:
    if status not in ("Ativo", "Desligado"):
        raise ValueError("status inválido — use 'Ativo' ou 'Desligado'")
    with _lock:
        dados = carregar(data_dir)
        dados.setdefault(_chave(nome), {})["status"] = status
        _salvar(data_dir, dados)


def adicionar_habilidade(data_dir: str, nome: str, habilidade_id: str) -> list:
    with _lock:
        dados = carregar(data_dir)
        entry = dados.setdefault(_chave(nome), {})
        habilidades = entry.setdefault("habilidades", [])
        if habilidade_id not in habilidades:
            habilidades.append(habilidade_id)
        _salvar(data_dir, dados)
        return habilidades


def remover_habilidade(data_dir: str, nome: str, habilidade_id: str) -> list:
    with _lock:
        dados = carregar(data_dir)
        entry = dados.setdefault(_chave(nome), {})
        habilidades = entry.setdefault("habilidades", [])
        if habilidade_id in habilidades:
            habilidades.remove(habilidade_id)
        _salvar(data_dir, dados)
        return habilidades
