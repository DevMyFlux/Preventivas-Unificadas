"""
Armazenamento do overlay de colaboradores (status, datas de vínculo, bloqueio, habilidades).

Duas implementações com a mesma interface (`load`, `save`, `version`):

  * JsonStore — um arquivo JSON por pasta (comportamento original; usado nos testes e como
    fallback). Em hospedagem com disco efêmero (Railway sem volume) o arquivo é PERDIDO a
    cada deploy/reinício: um desligamento registrado pela tela voltaria a "elegível".
  * DbStore — tabela `colaborador_overlay` no banco da aplicação (PostgreSQL/Cloud SQL em
    produção): durável e compartilhada entre os workers do gunicorn. O JSON versionado no
    repositório vira apenas a SEMENTE: copiado uma única vez, quando a unidade ainda não tem
    nenhuma linha no banco (marcador `__seed__`). Depois disso, o banco é a fonte de verdade.

`version()` é um valor barato que muda a cada gravação — o carregador de colaboradores o usa
para invalidar o cache entre workers (uma alteração feita num worker aparece nos outros no
máximo na próxima requisição, em vez de depender do TTL de 10 min).
"""
import json
import logging
import os
import threading
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from core.db import agora_utc, sessao
from core.models import ColaboradorOverlay

log = logging.getLogger("myflux.overlay")
_ARQUIVO = "colaboradores_overlay.json"
_MARCADOR_SEMENTE = "__seed__"


class OverlayStore(Protocol):
    def load(self) -> dict: ...
    def update(self, chave: str, mutador, por: str | None = None): ...
    def version(self) -> str: ...


class JsonStore:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self._lock = threading.Lock()

    @property
    def caminho(self) -> str:
        return os.path.join(self.data_dir, _ARQUIVO)

    def load(self) -> dict:
        if not os.path.exists(self.caminho):
            return {}
        try:
            with open(self.caminho, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def update(self, chave: str, mutador, por: str | None = None):
        """Lê, aplica `mutador(entrada)` (muta o dict da entrada) e grava — sob trava do processo."""
        with self._lock:
            dados = self.load()
            entrada = dados.setdefault(chave, {})
            resultado = mutador(entrada)
            tmp = self.caminho + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, self.caminho)
            return resultado

    def version(self) -> str:
        try:
            return str(os.stat(self.caminho).st_mtime_ns)
        except OSError:
            return "0"


class DbStore:
    """Overlay de UMA unidade no banco. `seed_dir`: pasta com o JSON de sementes (opcional)."""

    def __init__(self, unidade: str, seed_dir: str | None = None):
        self.unidade = unidade
        self.seed_dir = seed_dir
        self._lock = threading.Lock()

    def _semente(self) -> dict:
        return JsonStore(self.seed_dir).load() if self.seed_dir else {}

    def _garantir_semente(self, s) -> None:
        marcado = s.scalar(select(ColaboradorOverlay.id).where(
            ColaboradorOverlay.unit == self.unidade, ColaboradorOverlay.chave == _MARCADOR_SEMENTE))
        if marcado:
            return
        agora = agora_utc()
        for chave, entrada in self._semente().items():
            s.add(ColaboradorOverlay(unit=self.unidade, chave=chave, dados=json.dumps(entrada, ensure_ascii=False),
                                     updated_at=agora, updated_by="semente"))
        s.add(ColaboradorOverlay(unit=self.unidade, chave=_MARCADOR_SEMENTE, dados="{}", updated_at=agora,
                                 updated_by="semente"))

    def load(self) -> dict:
        try:
            with self._lock, sessao() as s:
                self._garantir_semente(s)
                s.flush()
                linhas = s.scalars(select(ColaboradorOverlay).where(ColaboradorOverlay.unit == self.unidade)).all()
                return {r.chave: json.loads(r.dados) for r in linhas if r.chave != _MARCADOR_SEMENTE}
        except Exception:
            # Banco indisponível NÃO pode tornar desligados "elegíveis": usa a semente versionada
            # (somente leitura) enquanto o banco não volta.
            log.exception("Overlay de %s: falha ao ler o banco; usando a semente do repositório", self.unidade)
            return self._semente()

    def update(self, chave: str, mutador, por: str | None = None):
        try:
            return self._update(chave, mutador, por)
        except IntegrityError:   # semente/linha criada por outro worker no mesmo instante: repete uma vez
            return self._update(chave, mutador, por)

    def _update(self, chave: str, mutador, por: str | None = None):
        """Atualiza UMA entrada (linha) com bloqueio de linha onde o banco suporta — dois workers
        alterando colaboradores diferentes não se sobrescrevem."""
        agora = agora_utc()
        with self._lock, sessao() as s:
            self._garantir_semente(s)
            s.flush()
            linha = s.scalar(select(ColaboradorOverlay).where(
                ColaboradorOverlay.unit == self.unidade, ColaboradorOverlay.chave == chave).with_for_update())
            entrada = json.loads(linha.dados) if linha else {}
            resultado = mutador(entrada)
            if linha:
                linha.dados = json.dumps(entrada, ensure_ascii=False)
                linha.updated_at, linha.updated_by = agora, por
            else:
                s.add(ColaboradorOverlay(unit=self.unidade, chave=chave, dados=json.dumps(entrada, ensure_ascii=False),
                                         updated_at=agora, updated_by=por))
            return resultado

    def version(self) -> str:
        try:
            with sessao() as s:
                ultimo = s.scalar(select(func.max(ColaboradorOverlay.updated_at)).where(ColaboradorOverlay.unit == self.unidade))
                n = s.scalar(select(func.count()).select_from(ColaboradorOverlay).where(ColaboradorOverlay.unit == self.unidade))
                return f"{ultimo}:{n}"
        except Exception:
            return "indisponivel"


def como_store(destino) -> OverlayStore:
    """Aceita um caminho de pasta (JsonStore) ou um store pronto."""
    if isinstance(destino, (str, os.PathLike)):
        return JsonStore(str(destino))
    return destino
