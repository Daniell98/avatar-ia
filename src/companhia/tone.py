"""Pedidos diretos de tom; nenhuma classificação paga ou inferência de humor."""

import re
import unicodedata


def tone_request(text: str) -> str | None:
    value = unicodedata.normalize("NFKD", text.casefold())
    value = "".join(c for c in value if not unicodedata.combining(c)).strip(" .!?\n")
    if re.fullmatch(
        r"(?:pode |pode voltar a |volta a |volte a )?(?:me zoar|me provocar|tom normal)", value
    ) or re.fullmatch(r"(?:volta|volte|retorne|voltar) (?:ao |para o )?tom normal", value):
        return "normal"
    if (
        re.fullmatch(r"(?:por favor[, ]+)?(?:menos|sem) (?:zoeira|piadas|provocacao|provocacoes)", value)
        or re.fullmatch(
            r"(?:pega|pegue) mais leve(?: (?:na|nas|com as|com a) "
            r"(?:zoeira|piadas|provocacao|provocacoes))?",
            value,
        )
        or re.fullmatch(r"nao gostei (?:dessa|desta|da sua) (?:provocacao|piada|zoeira)", value)
    ):
        return "gentle"
    return None


def apply_tone(store, tone: str):
    store.set_meta("gentle", "1" if tone == "gentle" else "")
