"""
Geração, classificação e filtragem das ocorrências de preventivas — lógica pura (sem
Flask e sem chamadas ao Neovero; os dados entram como listas de dicts), para ser testável.

MODELO DE OCORRÊNCIA
  Uma ocorrência é "algo previsto/realizado numa data de execução". Vem de duas origens:
    * "OS"    — ordem de serviço REAL do Neovero (aberta, em andamento, concluída…), com o
                responsável que o Neovero tem hoje.
    * "Plano" — projeção de um item de plano de manutenção (data prevista calculada a
                partir de `dataProximaPreventiva` + periodicidade) que ainda não tem OS.
  Se existe OS real para o mesmo (plano, equipamento/setor, dia), a projeção é descartada
  (casamento 1-para-1) — nunca a mesma manutenção aparece duas vezes nem é contada duas vezes.

STATUS DE EXECUÇÃO (campo `status`) e ATRASO (campo booleano `atrasada`)
    Concluída            OS Fechada (situação 3)
    Em andamento         OS em andamento (situação 2)
    Pendente             OS Aberta (situação 1)
    Cancelada            OS Cancelada (situação 4)
    Prevista             projeção sem OS ainda, data de hoje em diante
    Sem OS gerada        projeção sem OS, com data JÁ PASSADA — o Neovero não gerou/sincronizou
                         a OS; isto NÃO é atraso (não há informação suficiente para afirmar)
  `atrasada = True` somente para OS REAL ainda não concluída (Pendente ou Em andamento)
  cuja data prevista é anterior a HOJE (data local, BRT). Concluída/Cancelada nunca atrasam.

RESPONSÁVEL (campo `responsavel_status`) — o que o Neovero tem hoje na OS real
    Atribuída            executante do quadro, elegível
    Sem responsável      campo vazio
    Gestão               a OS está em nome de quem gerencia (causa-raiz do relato 5.2: o Neovero
                         cria a OS com o responsável PADRÃO do plano, que é o gestor)
    Genérico             nome que não é pessoa do quadro (ex.: "ELÉTRICA - DIURNO")
    Desligado            executante já desligado na data da OS
    Bloqueado            executante com aptidão pendente
  Qualquer coisa diferente de "Atribuída" marca `revisao = True` e gera recomendação de
  executante (a OS histórica NUNCA é reatribuída automaticamente por este módulo).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from core.neovero_client import SIT_MAP
from core.planejamento import detectar_paridade, detectar_turno, expandir_ocorrencias
from core.regras import elegibilidade as eleg
from core.regras import limites
from core.regras.atribuicao import ContextoOcorrencia, aplicar_regras, paridade_do_dia
from core.regras.nomes import encontrar_no_cadastro

# ── Status ────────────────────────────────────────────────────────────────────
ST_CONCLUIDA = "Concluída"
ST_EM_ANDAMENTO = "Em andamento"
ST_PENDENTE = "Pendente"
ST_CANCELADA = "Cancelada"
ST_PREVISTA = "Prevista"
ST_SEM_OS = "Sem OS gerada"
STATUS_ORDEM = [ST_PENDENTE, ST_EM_ANDAMENTO, ST_CONCLUIDA, ST_PREVISTA, ST_SEM_OS, ST_CANCELADA]

RESP_ATRIBUIDA = "Atribuída"
RESP_SEM = "Sem responsável"
RESP_GESTAO = "Gestão"
RESP_GENERICO = "Genérico"
RESP_DESLIGADO = "Desligado"
RESP_BLOQUEADO = "Bloqueado"

MOTIVOS_TEXTO = {
    "sem_colaboradores": "Cadastro de colaboradores indisponível.",
    "nenhum_elegivel": "Nenhum colaborador elegível/escalado nesta data.",
    "limite_diario": "Limite diário de ordens atingido por todos os profissionais compatíveis — requer intervenção.",
    "regra_nominal_indisponivel": "O responsável definido pela regra não está disponível nesta data — requer intervenção.",
    "regra_nominal_limite_diario": "O(s) responsável(is) da regra já atingiram o limite diário — requer intervenção.",
    "regra_pendente": "Regra de atribuição aguardando confirmação de nome.",
    "nenhum_apto": "Nenhum profissional apto encontrado.",
}


def hoje_local() -> date:
    """Data de hoje no fuso do Brasil (UTC-3). O servidor roda em UTC: `date.today()` viraria
    o dia 3 horas cedo (às 21h locais), classificando atrasos errado."""
    from datetime import timezone
    return (datetime.now(timezone.utc) + timedelta(hours=-3)).date()


def _data_de(valor) -> date | None:
    s = str(valor or "")[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _hora_de(valor) -> int:
    try:
        return int(str(valor)[11:13])
    except (ValueError, TypeError):
        return 8


def classificar_status(situacao_os: int | None, data_prev: date, hoje: date) -> tuple[str, bool]:
    """(status, atrasada) para uma ocorrência. `situacao_os` None = sem OS (projeção)."""
    if situacao_os is None:
        return (ST_PREVISTA, False) if data_prev >= hoje else (ST_SEM_OS, False)
    if situacao_os == 3:
        return ST_CONCLUIDA, False
    if situacao_os == 4:
        return ST_CANCELADA, False
    if situacao_os == 2:
        return ST_EM_ANDAMENTO, data_prev < hoje
    return ST_PENDENTE, data_prev < hoje   # situação 1 (ou desconhecida ≈ aberta)


@dataclass
class ContextoGeracao:
    colab_ativos: object                 # DataFrame (status Ativo) — universo de candidatos
    colab_todos: object                  # DataFrame completo (inclui desligados) — só p/ classificar responsável
    indicar: object                      # função(colaboradores, hist_tipo, hist_ativo, carga, tipo, setor, ativo, data, hora, **kw)
    regras_resolvidas: dict = field(default_factory=dict)
    nomes_permitidos_fn: object = None   # (descricao_plano, dia_par) -> set|None (escala nomeada HETRIN)
    hist_tipo: dict = field(default_factory=dict)
    hist_ativo: dict = field(default_factory=dict)
    carga: dict = field(default_factory=dict)
    hoje: date = field(default_factory=hoje_local)
    ocupacao: limites.OcupacaoDiaria = field(default_factory=limites.OcupacaoDiaria)


# ── responsável atual de uma OS real ──────────────────────────────────────────

def classificar_responsavel(nome_neovero: str | None, ctx: ContextoGeracao, dia: date) -> tuple[str, str | None]:
    """(responsavel_status, nome_no_cadastro) do responsável que o Neovero tem na OS."""
    nome = (nome_neovero or "").strip()
    if not nome:
        return RESP_SEM, None
    todos = ctx.colab_todos
    if todos is None or todos.empty:
        return RESP_GENERICO, None
    cadastro = encontrar_no_cadastro(nome, list(todos["funcionario"]))
    if cadastro is None:
        return RESP_GENERICO, None
    row = todos[todos["funcionario"] == cadastro].iloc[0]
    if eleg.cargo_e_gestao(str(row.get("cargo", ""))):
        return RESP_GESTAO, cadastro
    if eleg.ficou_desligado_ate(row, dia):
        return RESP_DESLIGADO, cadastro
    if row.get("bloqueado"):
        return RESP_BLOQUEADO, cadastro
    return RESP_ATRIBUIDA, cadastro


# ── construção das ocorrências ────────────────────────────────────────────────

def _contexto_regra(desc: str, oficina: str, tipo_id, periodicidade, unidade_tempo, dia: date) -> ContextoOcorrencia:
    return ContextoOcorrencia(
        descricao=desc or "", oficina=oficina or "", tipo_id=tipo_id,
        periodicidade=int(periodicidade or 0), unidade_tempo=str(unidade_tempo or "D"),
        data=dia, turno=detectar_turno(desc or ""))


def _ocorrencia_de_os(o: dict, hoje: date) -> dict | None:
    plano = o.get("planoManutencao") or {}
    if not o.get("planoManutencaoId") and not plano:
        return None  # OS sem plano (corretiva etc.) não é manutenção planejada
    dia = _data_de(o.get("dataHoraAbertura"))
    if dia is None:
        return None
    sit = o.get("situacao")
    status, atrasada = classificar_status(sit, dia, hoje)
    setor = ((o.get("setor") or {}).get("nome") or "").strip()
    equip = ((o.get("equipamento") or {}).get("nome") or "").strip()
    desc = plano.get("descricao") or ""
    oficina = ((o.get("oficina") or {}).get("descricao") or (plano.get("oficina") or {}).get("descricao") or "").strip()
    resp = o.get("responsavel") or {}
    return {
        "origem": "OS",
        "_dia": dia,
        "_plano_id": o.get("planoManutencaoId") or plano.get("id"),
        "_equip_id": o.get("equipamentoId"),
        "_setor_id": o.get("setorId"),
        "_os_id": o.get("id"),
        "_resp_id": o.get("responsavelId"),
        "_tipo_id": (o.get("tipoManutencao") or {}).get("id"),
        "_periodicidade": plano.get("periodicidade"),
        "_unidade_tempo": plano.get("periodicidadeTempoUnidade"),
        "_hora": _hora_de(o.get("dataHoraAbertura")),
        "_sit": sit,
        "id": f"os:{o.get('numero')}",
        "plano": desc,
        "tipo": ((o.get("tipoManutencao") or {}).get("descricao") or "").strip(),
        "oficina": oficina,
        "equipamento": equip or "—",
        "setor": setor or "—",
        "os_vinculada": o.get("numero", "") or "—",
        "os_id": o.get("id"),
        "os_situacao": SIT_MAP.get(sit, "—"),
        "responsavel_atual": (resp.get("nome") or "").strip() or None,
        "status": status,
        "atrasada": atrasada,
    }


def _ocorrencias_projetadas(planos, itens_por_plano, d_ini, d_fim, hoje) -> list[dict]:
    saida = []
    for p in planos:
        itens = itens_por_plano.get(p["id"], [])
        tipo = ((p.get("tipoManutencao") or {}).get("descricao") or "").strip()
        oficina = ((p.get("oficina") or {}).get("descricao") or "").strip()
        periodicidade = int(p.get("periodicidade") or 0)
        unidade = str(p.get("periodicidadeTempoUnidade") or "D")
        paridade = detectar_paridade(p.get("descricao", ""))
        for item in itens:
            dt_base = _data_de(item.get("dataProximaPreventiva"))
            if dt_base is None:
                continue
            equip = item.get("equipamento") or {}
            setor = ((item.get("setor") or equip.get("setorAtual") or {}).get("nome", "") or "").strip()
            equip_nome = (equip.get("nome") or "").strip()
            for dia in expandir_ocorrencias(dt_base, periodicidade, unidade, d_ini, d_fim, paridade):
                os_item = item.get("ordemServico") or {}
                # A OS vinculada só é "desta" ocorrência se o item está no ciclo atual
                # (data base) e a OS está aberta/em andamento; nas demais projeções ela é
                # uma OS antiga e não deve aparecer.
                os_ativa = os_item if (dia == dt_base and os_item.get("situacao") in (1, 2)) else {}
                sit = os_ativa.get("situacao")
                status, atrasada = classificar_status(sit, dia, hoje)
                saida.append({
                    "origem": "Plano",
                    "_dia": dia,
                    "_plano_id": p.get("id"),
                    "_equip_id": item.get("equipamentoId") or equip.get("id"),
                    "_setor_id": item.get("setorId") or (item.get("setor") or {}).get("id"),
                    "_item_id": item.get("id"),
                    "_os_id": os_ativa.get("id"),
                    "_resp_id": None,
                    "_tipo_id": (p.get("tipoManutencao") or {}).get("id"),
                    "_periodicidade": periodicidade,
                    "_unidade_tempo": unidade,
                    "_hora": 8,
                    "_sit": sit,
                    "_tipo_classif": f"{tipo} {p.get('descricao', '')} {oficina}".strip(),
                    "id": f"plano:{p.get('id')}:{item.get('id')}:{dia.isoformat()}",
                    "plano": p.get("descricao", ""),
                    "tipo": tipo,
                    "oficina": oficina,
                    "equipamento": equip_nome or "—",
                    "setor": setor or "—",
                    "os_vinculada": os_ativa.get("numero", "") or "—",
                    "os_id": os_ativa.get("id"),
                    "os_situacao": SIT_MAP.get(sit, "—") if sit else "—",
                    "responsavel_atual": None,
                    "status": status,
                    "atrasada": atrasada,
                })
    return saida


def _casar_projecoes_com_os(reais: list[dict], projecoes: list[dict]) -> list[dict]:
    """Descarta projeções que já têm OS real (mesmo plano + equipamento/setor, mesmo dia ou
    até 3 dias de diferença para planos não-diários — o Neovero pode abrir a OS com
    antecedência). Cada OS real absorve no máximo UMA projeção."""
    indice: dict[tuple, list[dict]] = defaultdict(list)
    for r in reais:
        chave_loc = r["_equip_id"] if r["_equip_id"] else ("S", r["_setor_id"])
        indice[(r["_plano_id"], chave_loc)].append(r)
    usadas: set[int] = set()
    restantes = []
    for pr in projecoes:
        chave_loc = pr["_equip_id"] if pr["_equip_id"] else ("S", pr["_setor_id"])
        tol = 0 if (pr["_periodicidade"] == 1 and pr["_unidade_tempo"] == "D") else 3
        melhor, melhor_dist = None, None
        for r in indice.get((pr["_plano_id"], chave_loc), ()):
            if id(r) in usadas:
                continue
            dist = abs((r["_dia"] - pr["_dia"]).days)
            if dist <= tol and (melhor is None or dist < melhor_dist):
                melhor, melhor_dist = r, dist
        if melhor is not None:
            usadas.add(id(melhor))
        else:
            restantes.append(pr)
    return restantes


def _recomendar(oc: dict, ctx: ContextoGeracao, andares, carga_alta) -> dict:
    """Executa o motor para UMA ocorrência (OS real a (re)atribuir ou projeção) e devolve
    os campos de recomendação. Atualiza ocupação diária/carga quando encontra alguém."""
    dia = oc["_dia"]
    desc = oc["plano"]
    turno_plano = detectar_turno(desc)
    hora_ref = 20 if turno_plano == "Noturno" else 8
    exigir_turno = turno_plano is not None
    tipo_classif = oc.get("_tipo_classif") or f"{desc} {oc['oficina']}".strip()
    setor = "" if oc["setor"] == "—" else oc["setor"]
    ativo = "" if oc["equipamento"] == "—" else oc["equipamento"]

    regra = aplicar_regras(ctx.regras_resolvidas, _contexto_regra(
        desc, oc["oficina"], oc["_tipo_id"], oc["_periodicidade"], oc["_unidade_tempo"], dia))
    resultado = {"recomendado": None, "recomendados": [], "cargo": "", "escala": "", "score": -999,
                 "motivo_sem_candidato": None, "regra": None, "alertas": list(regra.alertas)}
    if regra.regra_id:
        resultado["regra"] = {"id": regra.regra_id, "status": regra.status, "mensagem": regra.mensagem}

    if regra.status == "pendente":
        resultado["motivo_sem_candidato"] = regra.mensagem or MOTIVOS_TEXTO["regra_pendente"]
        return resultado

    nomes_permitidos = None
    if ctx.nomes_permitidos_fn is not None:
        nomes_permitidos = ctx.nomes_permitidos_fn(desc, paridade_do_dia(dia))

    isento = limites.tipo_isento(oc["_tipo_id"])   # tipos isentos não consultam nem consomem o limite diário
    diag: dict = {}
    principal, apoio, _ = ctx.indicar(
        ctx.colab_ativos, ctx.hist_tipo, ctx.hist_ativo, ctx.carga, tipo_classif, setor, ativo, dia, hora_ref,
        exigir_turno=exigir_turno, andares_colaborador=andares, carga_alta=carga_alta,
        nomes_permitidos=nomes_permitidos, ocupacao=None if isento else ctx.ocupacao,
        nomes_obrigatorios=set(regra.nomes) if regra.status == "aplicada" else None,
        diagnostico=diag,
    )
    if not principal:
        resultado["motivo_sem_candidato"] = MOTIVOS_TEXTO.get(diag.get("motivo", ""), MOTIVOS_TEXTO["nenhum_apto"])
        return resultado

    escolhidos = [principal]
    # regra com vários responsáveis (ex.: oficina AC/V em dia par): todos executam, nenhum sobrescreve o outro
    if regra.status == "aplicada" and len(regra.nomes) > 1 and apoio:
        escolhidos.append(apoio)

    chave = limites.chave_os(oc["os_vinculada"]) if oc["origem"] == "OS" else \
        limites.chave_prevista(oc["_plano_id"], oc.get("_item_id"), dia)
    for esc in escolhidos:
        if not isento:
            ctx.ocupacao.registrar(esc["nome"], dia, chave)
        ctx.carga[esc["nome"]] = ctx.carga.get(esc["nome"], 0) + 1
        if esc.get("andar"):
            andares[esc["nome"]].add(esc["andar"])
        if esc.get("complexidade") == "Alta":
            carga_alta[esc["nome"]] += 1

    resultado.update({
        "recomendado": principal["nome"],
        "recomendados": [e["nome"] for e in escolhidos],
        "cargo": principal["cargo"], "escala": principal["escala"], "score": principal["score"],
    })
    return resultado


def gerar_ocorrencias(
    ctx: ContextoGeracao, planos: list, itens_por_plano: dict, os_periodo: list, os_abertas: list,
    d_ini: date, d_fim: date, incluir_atrasadas: bool = True,
) -> list[dict]:
    """Monta a lista completa de ocorrências do período, já classificada e com recomendação."""
    hoje = ctx.hoje

    # 1) OS reais do período (+ OS ainda abertas de dias anteriores, se pedido)
    vistas: set = set()
    reais: list[dict] = []
    for o in os_periodo:
        oc = _ocorrencia_de_os(o, hoje)
        if oc and oc["id"] not in vistas:
            if d_ini <= oc["_dia"] <= d_fim:
                reais.append(oc)
                vistas.add(oc["id"])
    if incluir_atrasadas:
        for o in os_abertas:
            oc = _ocorrencia_de_os(o, hoje)
            if oc and oc["id"] not in vistas and oc["_dia"] < d_ini and oc["atrasada"]:
                reais.append(oc)
                vistas.add(oc["id"])

    # 2) projeções dos planos, sem as que já têm OS real
    projecoes = _casar_projecoes_com_os(reais, _ocorrencias_projetadas(planos, itens_por_plano, d_ini, d_fim, hoje))

    # 3) responsável atual das OS reais + registro na ocupação diária (sem dupla contagem)
    for oc in reais:
        status_resp, cadastro = classificar_responsavel(oc["responsavel_atual"], ctx, oc["_dia"])
        oc["responsavel_status"] = status_resp
        oc["responsavel_cadastro"] = cadastro
        if cadastro and oc["status"] != ST_CANCELADA and not limites.tipo_isento(oc["_tipo_id"]):
            ctx.ocupacao.registrar(cadastro, oc["_dia"], limites.chave_os(oc["os_vinculada"]))

    # 4) recomendações — ordem determinística: data, depois plano/equipamento
    andares: dict = defaultdict(set)
    carga_alta: dict = defaultdict(int)
    todas = reais + projecoes
    todas.sort(key=lambda x: (x["_dia"], x["plano"], x["equipamento"], x["setor"], x["id"]))
    for oc in todas:
        oc.setdefault("responsavel_status", "—")
        oc.setdefault("responsavel_cadastro", None)
        # "Sem OS gerada" (projeção de data passada) não é acionável: nada a recomendar
        precisa = oc["status"] in (ST_PENDENTE, ST_EM_ANDAMENTO, ST_PREVISTA)
        if oc["origem"] == "OS" and oc["responsavel_status"] == RESP_ATRIBUIDA:
            precisa = False   # já tem executante válido — não se reatribui nem se recomenda outro
        if precisa:
            oc.update(_recomendar(oc, ctx, andares, carga_alta))
        else:
            oc.update({"recomendado": None, "recomendados": [], "cargo": "", "escala": "", "score": -999,
                       "motivo_sem_candidato": None, "regra": None, "alertas": []})
        oc["revisao"] = bool(
            (oc["origem"] == "OS" and oc["status"] in (ST_PENDENTE, ST_EM_ANDAMENTO)
             and oc["responsavel_status"] != RESP_ATRIBUIDA)
        )
        oc["sem_candidato"] = bool(precisa and not oc["recomendado"])
        _finalizar_campos(oc)
    return todas


def _finalizar_campos(oc: dict) -> None:
    dia: date = oc["_dia"]
    oc["data_prev"] = dia.strftime("%d/%m/%Y")
    oc["data_iso"] = dia.isoformat()
    oc["dia_par"] = paridade_do_dia(dia)
    t = detectar_turno(oc["plano"])
    oc["turno"] = t or "—"
    # campos privados não vão para a API
    for k in [k for k in oc if k.startswith("_")]:
        del oc[k]


# ── filtros / totais / paginação ──────────────────────────────────────────────

def _lista(valor) -> list[str]:
    if valor is None:
        return []
    if isinstance(valor, (list, tuple, set)):
        return [str(v).strip() for v in valor if str(v).strip()]
    return [p.strip() for p in str(valor).split(",") if p.strip()]


def filtrar(itens: list[dict], f: dict) -> list[dict]:
    """Aplica os filtros combinados (todos opcionais; AND entre filtros).

    f: dias (ISO, lista/CSV) · data_ini/data_fim (date ISO) · status (lista) · atrasada (bool)
       turno (Diurno|Noturno|—) · paridade (Par|Ímpar) · responsavel (texto) · busca (texto)
       revisao (bool) · sem_candidato (bool) · origem (OS|Plano) · oficina (texto)"""
    dias = set(_lista(f.get("dias")))
    status = set(_lista(f.get("status")))
    ini, fim = f.get("data_ini") or "", f.get("data_fim") or ""
    resp = (f.get("responsavel") or "").strip().lower()
    busca = (f.get("busca") or "").strip().lower()
    oficina = (f.get("oficina") or "").strip().lower()

    def ok(it: dict) -> bool:
        d = it["data_iso"]
        if dias and d not in dias:
            return False
        if ini and d < ini:
            return False
        if fim and d > fim:
            return False
        if status and it["status"] not in status:
            return False
        if f.get("atrasada") is True and not it["atrasada"]:
            return False
        if f.get("turno") and it["turno"] != f["turno"]:
            return False
        if f.get("paridade") and it["dia_par"] != f["paridade"]:
            return False
        if f.get("origem") and it["origem"] != f["origem"]:
            return False
        if f.get("revisao") is True and not it["revisao"]:
            return False
        if f.get("sem_candidato") is True and not it["sem_candidato"]:
            return False
        if resp:
            alvo = " ".join([it.get("recomendado") or "", it.get("responsavel_atual") or "",
                             " ".join(it.get("recomendados") or [])]).lower()
            if resp not in alvo:
                return False
        if oficina and oficina not in (it.get("oficina") or "").lower():
            return False
        if busca:
            palheiro = " ".join(str(it.get(k) or "") for k in
                                ("plano", "tipo", "oficina", "equipamento", "setor", "os_vinculada")).lower()
            if busca not in palheiro:
                return False
        return True

    return [it for it in itens if ok(it)]


def totais(itens: list[dict]) -> dict:
    por_status = {s: 0 for s in STATUS_ORDEM}
    for it in itens:
        por_status[it["status"]] = por_status.get(it["status"], 0) + 1
    por_dia: dict[str, int] = defaultdict(int)
    for it in itens:
        por_dia[it["data_iso"]] += 1
    return {
        "total": len(itens),
        "por_status": por_status,
        "por_dia": dict(sorted(por_dia.items())),
        "atrasadas": sum(1 for it in itens if it["atrasada"]),
        "revisao": sum(1 for it in itens if it["revisao"]),
        "sem_candidato": sum(1 for it in itens if it["sem_candidato"]),
        "com_recomendacao": sum(1 for it in itens if it["recomendado"]),
    }


def paginar_lista(itens: list[dict], pagina: int, por_pagina: int) -> list[dict]:
    por_pagina = max(1, min(por_pagina, 500))
    pagina = max(1, pagina)
    return itens[(pagina - 1) * por_pagina: pagina * por_pagina]
