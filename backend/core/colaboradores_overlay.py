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
    habilidades — o padrão de quem nunca foi editado pela aplicação."""
    overlay = carregar(data_dir)
    status_col, habilidades_col = [], []
    for nome in df["funcionario"]:
        entry = overlay.get(_chave(nome), {})
        status_col.append(entry.get("status", "Ativo"))
        habilidades_col.append(list(entry.get("habilidades", [])))
    df = df.copy()
    df["status"] = status_col
    df["habilidades"] = habilidades_col
    return df


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
