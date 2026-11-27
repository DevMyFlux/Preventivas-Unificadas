"""
Fila de conferência e (opcionalmente) escrita do executante das OS no Neovero — item 5.7.

VIABILIDADE (investigação com a API real, somente leitura):
  * O Neovero não publica documentação/Swagger (`/swagger`, `/docs`, `/openapi.json` → 404).
  * O endpoint de uma OS (`/api/ordensservico/{id}`) responde a OPTIONS com
    `Allow: DELETE, GET, PATCH, PUT` — ou seja, atualização existe tecnicamente. Porém é a
    API interna do cliente web (NeoveroWeb), não uma integração oficial/suportada; o
    formato do corpo aceito, as permissões da conta de serviço e os efeitos colaterais
    (histórico, notificações, versão do registro) NÃO foram validados contra um ambiente
    de teste, e nenhuma requisição de escrita foi feita durante o desenvolvimento.
  * Cada OS nasce no Neovero com `responsavelId` = responsável PADRÃO do plano
    (`planoManutencao.responsavelId`) — na HMB, 57 de 120 planos têm o gestor como padrão
    e 227 de 847 preventivas de 01–13/10/2026 nasceram em nome dele. É o passo manual que a
    supervisão quer eliminar.

POR ISSO a automação é entregue em camadas, seguras por padrão:
  1. FILA (sempre disponível): lista as OS abertas cujo responsável é gestão/genérico/
     desligado/vazio, com o executante proposto pelo motor (regras, escala, limites).
  2. PROPOSTAS + APROVAÇÃO: cada item vira uma proposta persistida (idempotente) que um
     usuário da unidade confere e aprova/rejeita.
  3. APLICAÇÃO — desligada por padrão (`NEOVERO_WRITE_ENABLED=false`). Ligada, ainda roda em
     SIMULAÇÃO (`NEOVERO_WRITE_DRY_RUN=true`): faz todas as validações contra o Neovero
     (OS existe, é da unidade, está aberta, responsável ainda é o original, vaga no dia) e
     registra o que SERIA enviado, sem enviar. Só com as duas chaves explicitamente
     alteradas a requisição PATCH sai — e o contrato dela precisa ser validado antes.

Garantias da aplicação: compare-and-set (nunca sobrescreve um responsável que mudou desde a
proposta), idempotência por chave (OS, executante, data), conferência da unidade
(empresa.id da OS), re-checagem do limite diário e leitura de volta após escrever.
"""
import hashlib
from datetime import date

from sqlalchemy import select

from core import audit
from core.db import agora_utc, sessao
from core.models import AtribuicaoProposta
from core.neovero_client import NeoveroIndisponivelError, _requisitar, buscar_os
from core.regras import limites
from core.regras.nomes import nomes_batem
from core.settings import settings

STATUS_FINAIS = ("aplicada", "simulada", "rejeitada")
RESPONSAVEIS_ELEGIVEIS_PARA_FILA = ("Gestão", "Genérico", "Desligado", "Bloqueado", "Sem responsável")


class EscritaDesabilitada(RuntimeError):
    pass


def chave_idempotencia(unidade: str, os_id: int, funcionario: str, data_iso: str) -> str:
    return hashlib.sha256(f"{unidade}|{os_id}|{funcionario.strip().lower()}|{data_iso}".encode()).hexdigest()


# ── mapeamento funcionário (cadastro interno) → id no Neovero ─────────────────

def mapa_funcionarios_neovero(registros_os: list[dict]) -> dict[int, str]:
    """{id: nome} dos responsáveis vistos nas OS reais (a única fonte de ids que a
    integração atual expõe — não há endpoint de listagem de funcionários liberado)."""
    mapa: dict[int, str] = {}
    for o in registros_os:
        r = o.get("responsavel") or {}
        if r.get("id") and r.get("nome"):
            mapa[int(r["id"])] = r["nome"]
    return mapa


def resolver_id_neovero(nome_cadastro: str, ids_neovero: dict[int, str]) -> tuple[int | None, str | None]:
    """(id, motivo_se_falhou). Exige exatamente UM id plausível; zero ou vários → não automatiza."""
    candidatos = {i for i, n in ids_neovero.items() if nomes_batem(n, nome_cadastro)}
    if len(candidatos) == 1:
        return next(iter(candidatos)), None
    if not candidatos:
        return None, "Colaborador sem correspondência entre as OS do Neovero (id desconhecido)."
    return None, "Mais de um funcionário do Neovero corresponde a este nome — resolução manual."


# ── fila ──────────────────────────────────────────────────────────────────────

def montar_fila(ocorrencias: list[dict], ids_neovero: dict[int, str]) -> list[dict]:
    """OS reais abertas/em andamento que precisam de executante, com a proposta do motor."""
    fila = []
    for oc in ocorrencias:
        if oc["origem"] != "OS" or oc["status"] not in ("Pendente", "Em andamento"):
            continue
        if oc["responsavel_status"] not in RESPONSAVEIS_ELEGIVEIS_PARA_FILA:
            continue
        item = {
            "os_id": oc["os_id"], "os_numero": oc["os_vinculada"], "data_iso": oc["data_iso"], "plano": oc["plano"],
            "responsavel_atual": oc["responsavel_atual"], "responsavel_status": oc["responsavel_status"],
            "proposto": oc["recomendado"], "propostos": oc["recomendados"], "cargo": oc["cargo"],
            "neovero_funcionario_id": None, "automatizavel": False, "motivo": None, "alertas": oc.get("alertas", []),
        }
        if not oc["recomendado"]:
            item["motivo"] = oc.get("motivo_sem_candidato") or "Sem executante apto — intervenção necessária."
        elif len(oc["recomendados"]) > 1:
            item["motivo"] = ("A regra define mais de um responsável; o Neovero guarda um único responsável "
                              "principal por OS — preencher o(s) demais manualmente.")
            fid, _ = resolver_id_neovero(oc["recomendado"], ids_neovero)
            item["neovero_funcionario_id"] = fid
            item["automatizavel"] = fid is not None
        else:
            fid, motivo = resolver_id_neovero(oc["recomendado"], ids_neovero)
            item["neovero_funcionario_id"] = fid
            item["motivo"] = motivo
            item["automatizavel"] = fid is not None
        fila.append(item)
    return fila


# ── propostas (persistência) ──────────────────────────────────────────────────

def serializar(p: AtribuicaoProposta) -> dict:
    return {
        "id": p.id, "unit": p.unit, "os_id": p.os_id, "os_numero": p.os_numero, "data_prevista": p.data_prevista,
        "plano": p.plano, "responsavel_original": p.responsavel_original,
        "responsavel_original_id": p.responsavel_original_id, "funcionario_proposto": p.funcionario_proposto,
        "neovero_funcionario_id": p.neovero_funcionario_id, "status": p.status, "mensagem": p.mensagem,
        "criado_por": p.criado_por, "criado_em": p.criado_em.isoformat() + "Z",
        "aprovado_por": p.aprovado_por, "aprovado_em": (p.aprovado_em.isoformat() + "Z") if p.aprovado_em else None,
        "processado_em": (p.processado_em.isoformat() + "Z") if p.processado_em else None,
    }


def criar_propostas(unidade: str, itens: list[dict], usuario: str, responsavel_original_ids: dict[int, int | None]) -> list[dict]:
    """Cria propostas a partir de itens da fila. Idempotente: a mesma (OS, executante, data)
    nunca gera duas propostas. Itens não automatizáveis são ignorados e devolvidos como tal."""
    saida = []
    with sessao() as s:
        for it in itens:
            if not it.get("automatizavel") or not it.get("neovero_funcionario_id") or not it.get("proposto"):
                saida.append({"os_numero": it.get("os_numero"), "criada": False,
                              "motivo": it.get("motivo") or "Item não automatizável."})
                continue
            chave = chave_idempotencia(unidade, it["os_id"], it["proposto"], it["data_iso"])
            atual = s.scalar(select(AtribuicaoProposta).where(AtribuicaoProposta.chave_idempotencia == chave))
            if atual:
                if atual.status in ("rejeitada", "falha", "conflito"):
                    atual.status, atual.mensagem, atual.processado_em = "proposta", None, None
                    atual.aprovado_por = atual.aprovado_em = None
                    saida.append({"os_numero": it["os_numero"], "criada": True, "reaberta": True, "id": atual.id})
                else:
                    saida.append({"os_numero": it["os_numero"], "criada": False, "id": atual.id,
                                  "motivo": f"Já existe proposta ({atual.status}) para esta OS e executante."})
                continue
            p = AtribuicaoProposta(
                unit=unidade, chave_idempotencia=chave, os_id=int(it["os_id"]), os_numero=str(it["os_numero"]),
                data_prevista=it["data_iso"], plano=(it.get("plano") or "")[:255],
                responsavel_original_id=responsavel_original_ids.get(int(it["os_id"])),
                responsavel_original=it.get("responsavel_atual"), funcionario_proposto=it["proposto"],
                neovero_funcionario_id=int(it["neovero_funcionario_id"]), status="proposta", criado_por=usuario)
            s.add(p)
            s.flush()
            saida.append({"os_numero": it["os_numero"], "criada": True, "id": p.id})
    return saida


def listar_propostas(unidade: str | None, status: str | None = None, limite: int = 500) -> list[dict]:
    with sessao() as s:
        stmt = select(AtribuicaoProposta)
        if unidade:
            stmt = stmt.where(AtribuicaoProposta.unit == unidade)
        if status:
            stmt = stmt.where(AtribuicaoProposta.status == status)
        return [serializar(p) for p in s.scalars(stmt.order_by(AtribuicaoProposta.id.desc()).limit(limite)).all()]


def decidir(unidade: str, ids: list[int], aprovar: bool, usuario: str) -> int:
    n = 0
    with sessao() as s:
        for p in s.scalars(select(AtribuicaoProposta).where(
                AtribuicaoProposta.id.in_(ids), AtribuicaoProposta.unit == unidade)).all():
            if p.status != "proposta":
                continue
            p.status = "aprovada" if aprovar else "rejeitada"
            p.aprovado_por, p.aprovado_em = usuario, agora_utc()
            n += 1
    return n


# ── aplicação ─────────────────────────────────────────────────────────────────

def _contar_os_do_dia(headers: dict, empresa_id: int, funcionario_id: int, dia: date) -> int:
    """Quantas OS não canceladas o funcionário tem no dia — recontagem FRESCA no Neovero."""
    payload = {
        "limit": 100, "offset": 0,
        "filterGroups": [{"combineOperator": "AND", "filters": [
            {"property": "empresa.id", "value": [empresa_id]},
            {"property": "responsavel.id", "value": [funcionario_id]},
            {"property": "periodoAbertura", "value": {
                "rangeType": "CUSTOM",
                "customStart": dia.strftime("%Y-%m-%dT00:00:00"), "customEnd": dia.strftime("%Y-%m-%dT23:59:59")}},
        ]}],
    }
    from core.neovero_client import paginar
    return sum(1 for o in paginar(headers, payload, "/api/ordensservico/query") if o.get("situacao") != 4)


def _validar_e_preparar(p: AtribuicaoProposta, headers: dict, empresa_id: int, cargo_executante: str | None) -> tuple[str, str]:
    """('ok'|'conflito'|'falha', mensagem). Só leitura."""
    os_ = buscar_os(headers, p.os_id)
    if os_ is None:
        return "falha", "OS não encontrada no Neovero."
    if str((os_.get("empresa") or {}).get("id")) != str(empresa_id):
        return "falha", "A OS pertence a outra unidade/empresa — bloqueado."
    if str(os_.get("numero")) != str(p.os_numero):
        return "falha", "Número da OS divergente do registrado na proposta — bloqueado."
    if os_.get("situacao") not in (1, 2):
        return "conflito", "A OS não está mais Aberta/Em andamento."
    atual = os_.get("responsavelId")
    if atual != p.responsavel_original_id:
        return "conflito", "O responsável da OS mudou desde a proposta — não será sobrescrito."
    limite = limites.limite_do_cargo(cargo_executante)
    if limite is not None:
        dia = date.fromisoformat(p.data_prevista)
        ocupados = _contar_os_do_dia(headers, empresa_id, int(p.neovero_funcionario_id), dia)
        if ocupados >= limite:
            return "falha", f"Limite diário atingido ({ocupados}/{limite}) para o executante em {p.data_prevista}."
    return "ok", "Validações concluídas."


def processar(unidade: str, empresa_id: int, ids: list[int], usuario: str, headers: dict,
              cargos_por_nome: dict[str, str], modo: str = "aplicar", user_obj=None) -> list[dict]:
    """Valida (e, se permitido, aplica) propostas APROVADAS. `modo`: 'simular' | 'aplicar'."""
    if modo == "aplicar" and not settings.neovero_escrita_habilitada:
        raise EscritaDesabilitada(
            "Escrita no Neovero desabilitada (NEOVERO_WRITE_ENABLED=false). Use 'simular' para validar.")
    escrever = modo == "aplicar" and not settings.neovero_escrita_simulada
    resultados = []
    eventos = []  # gravados DEPOIS do commit (evita travar o SQLite com duas conexões escrevendo)
    with sessao() as s:
        propostas = s.scalars(select(AtribuicaoProposta).where(
            AtribuicaoProposta.id.in_(ids), AtribuicaoProposta.unit == unidade)).all()
        for p in propostas:
            if p.status != "aprovada":
                resultados.append({"id": p.id, "status": p.status, "mensagem": "Só propostas aprovadas são processadas."})
                continue
            try:
                estado, msg = _validar_e_preparar(p, headers, empresa_id, cargos_por_nome.get(p.funcionario_proposto))
                if estado == "ok":
                    if escrever:
                        r = _requisitar("PATCH", f"/api/ordensservico/{p.os_id}",
                                        {**headers, "content-type": "application/json"},
                                        json_body={"responsavelId": int(p.neovero_funcionario_id)}, tentativas=1)
                        if r.status_code >= 400:
                            estado, msg = "falha", f"Neovero recusou a atualização (HTTP {r.status_code})."
                        else:
                            lido = buscar_os(headers, p.os_id) or {}
                            if lido.get("responsavelId") == p.neovero_funcionario_id:
                                estado, msg = "aplicada", "Responsável atualizado e confirmado por leitura."
                            else:
                                estado, msg = "falha", "Atualização enviada, mas a leitura de volta não confirmou o responsável."
                    else:
                        estado, msg = "simulada", ("Simulação: tudo validado; nenhuma escrita enviada ao Neovero "
                                                   "(NEOVERO_WRITE_DRY_RUN=true ou modo simular).")
            except NeoveroIndisponivelError as exc:
                estado, msg = "falha", f"Neovero indisponível: {exc}"
            p.status, p.mensagem, p.processado_em = estado, msg, agora_utc()
            eventos.append(dict(
                user=user_obj, unit=unidade, module="distribuicao", action="update", resource=p.os_numero,
                result="success" if estado in ("aplicada", "simulada") else "failure",
                details={"proposta": p.id, "estado": estado, "de": p.responsavel_original,
                         "para": p.funcionario_proposto, "dia": p.data_prevista, "mensagem": msg,
                         "escreveu": bool(estado == "aplicada")}))
            resultados.append({"id": p.id, "os_numero": p.os_numero, "status": estado, "mensagem": msg})
    for ev in eventos:
        audit.registrar("assignment_apply", **ev)
    return resultados
