"""Testes de units.grand_massif.routes._nomes_batem — compara o "responsável" de uma
OS real da Neovero contra um nome da planilha interna, tolerando pequenas variações
de grafia entre os dois cadastros (sistemas independentes, dados digitados por
pessoas diferentes)."""
import pytest

from units.grand_massif.routes import _nomes_batem


# ── Bug real: "Willian Miranda de Morais" (Neovero) x "William Miranda de Moraes"
# (planilha) — confirmado por auditoria (HETRIN, set/2026). O 1º nome exigia
# igualdade EXATA (sem a mesma tolerância de prefixo dos demais), então nunca batia.

def test_nomes_batem_variacao_de_grafia_real_willian_william():
    assert _nomes_batem("WILLIAN  MIRANDA DE MORAIS", "William Miranda de Moraes") is True


def test_nomes_batem_com_sobrenome_extra():
    """Neovero às vezes tem um sobrenome a mais que a planilha (ex: nome do meio da
    família materna) — confirmado real: "Carlos Aurélio de Carvalho Oliveira" (Neovero)
    x "Carlos Aurélio de Carvalho" (planilha)."""
    assert _nomes_batem("CARLOS AURÉLIO DE CARVALHO OLIVEIRA", "Carlos Aurélio de Carvalho") is True


def test_nomes_batem_identico():
    assert _nomes_batem("Maikon Jonathas Gomes Bessa", "Maikon Jonathas Gomes Bessa") is True


@pytest.mark.parametrize("nome_api, nome_planilha", [
    ("Ana Paula Souza", "Carlos Eduardo Lima"),
    ("Ricardo Alves", "Fernanda Alves"),  # mesmo sobrenome, primeiro nome bem diferente
    ("", "Fulano de Tal"),
    ("Fulano de Tal", ""),
])
def test_nomes_batem_pessoas_diferentes_nao_batem(nome_api, nome_planilha):
    assert _nomes_batem(nome_api, nome_planilha) is False


def test_nomes_batem_nao_e_permissivo_demais_com_1_palavra_so():
    """Um nome de uma palavra só não deve bater com qualquer sobrenome parecido —
    a defesa contra falso-positivo (maioria das palavras batendo) ainda precisa valer."""
    assert _nomes_batem("Maria", "Maria Pureza Pereira Ramos") is False
