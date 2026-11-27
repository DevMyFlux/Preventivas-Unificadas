"""
Persistência dos atributos de colaborador que a aplicação edita: status (Ativo/Desligado),
data de admissão/desligamento, bloqueio e habilidades. Em produção fica no BANCO (tabela
`colaborador_overlay`, ver core/overlay_store.py — durável e compartilhada entre workers);
o JSON versionado em data/<unidade>/ é só a semente da primeira leitura.

O Excel continua sendo a fonte de verdade para nome/cargo/turno/regime/escala — este
overlay nunca escreve no Excel, só guarda o que não existe nele. Colaboradores nunca
são removidos fisicamente: "Desligado" é um status, não uma exclusão.

`status` (Ativo/Desligado) é uma exclusão de MÊS INTEIRO — usado pela camada de rota
(_colab_ativos, em cada units/*/routes.py) como pré-filtro antes até de chamar o motor
de recomendação: um colaborador "Desligado" nunca aparece em nenhuma preventiva daquele
mês, dia nenhum. `data_admissao`/`data_desligamento` são mais precisos — valem por DIA,
consultados dentro de esta_disponivel() (ver dentro_do_vinculo() abaixo): alguém pode
estar "Ativo" (presente no arquivo do mês, sem status manual setado) mas ainda assim
ficar indisponível a partir do dia seguinte ao desligamento, sem precisar editar a
planilha nem esperar a virada de mês — foi exatamente essa lacuna (colaborador desligado
NO MEIO do mês continuando a ser recomendado até o arquivo do mês seguinte ser trocado)
que motivou adicionar essas duas datas: confirmado com dado real (HETRIN, set/2026) que
3 colaboradores com contrato de experiência encerrado em 11, 16 e 22/09 continuaram
sendo recomendados em preventivas e até em OS reais no Neovero até o fim do mês, porque
a única forma de removê-los era ou apagar a linha da planilha (só foi feito na planilha
do mês SEGUINTE) ou chamar o PATCH de status manualmente (nunca foi chamado)."""
from datetime import date, datetime

from core.overlay_store import como_store


def _chave(nome: str) -> str:
    return nome.strip().upper()


def carregar(destino) -> dict:
    """Entradas do overlay. `destino`: pasta (JSON) ou um OverlayStore (ex.: DbStore da unidade)."""
    return como_store(destino).load()


def aplicar_overlay(df, destino):
    """Adiciona colunas 'status' e 'habilidades' ao DataFrame de colaboradores carregado
    do Excel, usando o overlay salvo. Colaborador sem entrada no overlay é Ativo, sem
    habilidades — o padrão de quem nunca foi editado pela aplicação.

    Também pode sobrescrever 'bloqueado'/'aviso' quando o overlay tem uma entrada
    explícita pra isso — usado quando a planilha de origem não tem coluna de Status
    própria (ex: formato calendário simples) mas ainda assim existe uma pendência real
    de aptidão (ex: autorização elétrica pendente) que precisa continuar bloqueando a
    recomendação. Sem entrada no overlay, mantém o que o parser já calculou (ex: o
    formato rico/12x36 já bloqueia sozinho via sua própria coluna Status)."""
    overlay = carregar(destino)
    status_col, habilidades_col, bloqueado_col, aviso_col = [], [], [], []
    data_admissao_col, data_desligamento_col = [], []
    tem_bloqueado_no_df = "bloqueado" in df.columns
    tem_aviso_no_df = "aviso" in df.columns
    for idx, nome in enumerate(df["funcionario"]):
        entry = overlay.get(_chave(nome), {})
        status_col.append(entry.get("status", "Ativo"))
        habilidades_col.append(list(entry.get("habilidades", [])))
        data_admissao_col.append(entry.get("data_admissao"))
        data_desligamento_col.append(entry.get("data_desligamento"))
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
    df["data_admissao"] = data_admissao_col
    df["data_desligamento"] = data_desligamento_col
    # Atribuir uma lista Python com None misturado a string faz o pandas promover pra
    # NaN (float) silenciosamente — json.dumps não recusa NaN, só emite o token
    # literal `NaN`, que não é JSON válido e quebra JSON.parse no frontend. Mesmo bug
    # já visto (e corrigido) no parser da HETRIN; aqui reaparece porque esta função
    # reconstrói a coluna do zero via lista Python em vez de só copiar do DataFrame.
    df["aviso"] = df["aviso"].astype(object).where(df["aviso"].notna(), None)
    df["data_admissao"] = df["data_admissao"].astype(object).where(df["data_admissao"].notna(), None)
    df["data_desligamento"] = df["data_desligamento"].astype(object).where(df["data_desligamento"].notna(), None)
    return _acrescentar_desligados_fora_da_escala(df, overlay)


def _acrescentar_desligados_fora_da_escala(df, overlay: dict):
    """Colaboradores desligados deixam de constar nas escalas dos meses seguintes, mas o
    histórico precisa continuar identificável: OS antigas ainda podem estar no nome deles
    e a supervisão precisa vê-las para revisão. Para cada entrada do overlay com
    `data_desligamento` (ou status "Desligado") que NÃO está na planilha carregada,
    acrescenta uma linha "fantasma": status Desligado, sem escala, nunca elegível. Nada é
    excluído — é o oposto de apagar o registro. Dados de exibição (nome/cargo/turno)
    vêm da própria entrada do overlay (campos opcionais `nome`, `cargo`, `turno`)."""
    import pandas as pd

    presentes = {_chave(n) for n in df["funcionario"]}
    novas = []
    for chave, entry in overlay.items():
        if chave in presentes:
            continue
        if not entry.get("data_desligamento") and entry.get("status") != "Desligado":
            continue
        novas.append({
            "funcionario": entry.get("nome") or chave.title(),
            "cargo": entry.get("cargo", "—"),
            "turno": entry.get("turno", ""),
            "regime": "—",
            "horario": "",
            "dias_plantao": {},
            "status": "Desligado",
            "habilidades": list(entry.get("habilidades", [])),
            "bloqueado": False,
            "aviso": "Desligado — fora da escala vigente (registro histórico).",
            "data_admissao": entry.get("data_admissao"),
            "data_desligamento": entry.get("data_desligamento"),
            "fora_da_escala": True,
        })
    if not novas:
        return df
    extra = pd.DataFrame(novas)
    if "fora_da_escala" not in df.columns:
        df = df.assign(fora_da_escala=False)
    saida = pd.concat([df, extra], ignore_index=True)
    # concat promove ausências a NaN; as colunas usadas como texto/data precisam de None real
    for col in ("aviso", "data_admissao", "data_desligamento"):
        saida[col] = saida[col].astype(object).where(saida[col].notna(), None)
    saida["fora_da_escala"] = saida["fora_da_escala"].fillna(False).astype(bool)
    return saida


def _parse_data(valor) -> date | None:
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    return datetime.strptime(str(valor)[:10], "%Y-%m-%d").date()


def dentro_do_vinculo(row, data_os: date) -> bool:
    """True se `data_os` está dentro do período de vínculo do colaborador — a partir de
    `data_admissao` (inclusive, se houver) e ANTES de `data_desligamento` (exclusive,
    se houver — o próprio dia do desligamento já conta como indisponível, não o
    seguinte). Segue o exemplo dado pela supervisão ao pedir esse mecanismo: "Até
    15/09/2026 → pode ser considerado elegível; A partir de 16/09/2026 (a data do
    desligamento) → não pode ser recomendado".

    Sem nenhuma das duas datas setadas (o caso comum — ninguém precisou registrar isso
    ainda), sempre retorna True: ausência de dado nunca vira exclusão por omissão, é
    "sem restrição de data" mesmo. Comparação por DIA (não por mês inteiro, que é o que
    o campo `status` Ativo/Desligado já cobre) — é o que permite um desligamento no
    MEIO do mês parar de gerar recomendações a partir do próprio dia, sem precisar
    editar a planilha nem esperar a virada de mês pra trocar de arquivo."""
    data_desligamento = _parse_data(row.get("data_desligamento"))
    if data_desligamento is not None and data_os >= data_desligamento:
        return False
    data_admissao = _parse_data(row.get("data_admissao"))
    if data_admissao is not None and data_os < data_admissao:
        return False
    return True


def set_bloqueado(destino, nome: str, bloqueado: bool, aviso: str | None = None, por: str | None = None) -> None:
    """Marca (ou desmarca) um colaborador como bloqueado via overlay — pensado pra
    planilhas sem coluna de Status própria (formato calendário), onde a única forma de
    registrar uma pendência de aptidão (ex: autorização elétrica) é fora do Excel."""
    def mutar(entry: dict) -> None:
        entry["bloqueado"] = bloqueado
        if bloqueado and aviso:
            entry["aviso"] = aviso
        elif not bloqueado:
            entry.pop("aviso", None)
    como_store(destino).update(_chave(nome), mutar, por)


def set_status(destino, nome: str, status: str, por: str | None = None) -> None:
    if status not in ("Ativo", "Desligado"):
        raise ValueError("status inválido — use 'Ativo' ou 'Desligado'")
    como_store(destino).update(_chave(nome), lambda e: e.__setitem__("status", status), por)


def _validar_data(data: str | None) -> None:
    if data is not None:
        _parse_data(data)  # levanta ValueError se o formato não for YYYY-MM-DD


def _definir_data(destino, nome: str, campo: str, data: str | None, por: str | None) -> None:
    _validar_data(data)

    def mutar(entry: dict) -> None:
        if data:
            entry[campo] = data
        else:
            entry.pop(campo, None)
    como_store(destino).update(_chave(nome), mutar, por)


def set_data_desligamento(destino, nome: str, data: str | None, por: str | None = None) -> None:
    """`data` no formato "YYYY-MM-DD", ou None pra remover a data (volta a não ter
    restrição). A PARTIR dessa data (inclusive — o próprio dia do desligamento já
    conta), dentro_do_vinculo() passa a retornar False pra esse colaborador — ver
    docstring da função. Independe do campo `status`: dá pra desligar alguém no meio do mês
    sem editar a planilha nem esperar a virada de mês, e sem marcar status="Desligado"."""
    _definir_data(destino, nome, "data_desligamento", data, por)


def set_data_admissao(destino, nome: str, data: str | None, por: str | None = None) -> None:
    """Mesma ideia de set_data_desligamento(), pro outro lado: ANTES dessa data,
    dentro_do_vinculo() retorna False — cobre o caso de alguém contratado no meio do
    mês cujo calendário da planilha já vem preenchido desde o dia 1."""
    _definir_data(destino, nome, "data_admissao", data, por)


def adicionar_habilidade(destino, nome: str, habilidade_id: str, por: str | None = None) -> list:
    def mutar(entry: dict) -> list:
        habilidades = entry.setdefault("habilidades", [])
        if habilidade_id not in habilidades:
            habilidades.append(habilidade_id)
        return list(habilidades)
    return como_store(destino).update(_chave(nome), mutar, por)


def remover_habilidade(destino, nome: str, habilidade_id: str, por: str | None = None) -> list:
    def mutar(entry: dict) -> list:
        habilidades = entry.setdefault("habilidades", [])
        if habilidade_id in habilidades:
            habilidades.remove(habilidade_id)
        return list(habilidades)
    return como_store(destino).update(_chave(nome), mutar, por)
