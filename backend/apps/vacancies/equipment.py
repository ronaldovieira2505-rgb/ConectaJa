"""EPIs, uniforme e ferramentas da vaga (US22): o que o prestador leva e o que a empresa fornece."""

from apps.core.exceptions import DomainError

# Lista fixa, na ordem em que aparece para a empresa e para o prestador.
ITEMS = {
    "CAPACETE": "Capacete",
    "LUVAS": "Luvas",
    "BOTINA": "Botina",
    "OCULOS_PROTECAO": "Óculos de proteção",
    "PROTETOR_AURICULAR": "Protetor auricular",
    "COLETE_REFLETIVO": "Colete refletivo",
    "UNIFORME": "Uniforme",
    "CALCA_PRETA": "Calça preta",
    "CAMISA_BRANCA": "Camisa branca",
    "SAPATO_SOCIAL": "Sapato social",
    "FERRAMENTAS_PROPRIAS": "Ferramentas próprias",
}
WORKER, COMPANY = "PRESTADOR", "EMPRESA"
PROVIDERS = {WORKER: "o prestador leva", COMPANY: "a empresa fornece"}
NOTES_MAX_LENGTH = 300


def clean_equipment(value):
    """Lista de `{"item", "provider"}`, sem repetição, na ordem da lista fixa."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise DomainError("Envie os itens como uma lista.")
    chosen = {}
    for entry in value:
        if not isinstance(entry, dict):
            raise DomainError("Cada item precisa de nome e de quem providencia.")
        item, provider = entry.get("item"), entry.get("provider")
        if item not in ITEMS:
            raise DomainError("Item fora da lista de EPIs, uniforme e ferramentas.")
        if provider not in PROVIDERS:
            raise DomainError("Informe se o prestador leva ou se a empresa fornece o item.")
        if item in chosen:
            raise DomainError("Cada item só pode aparecer uma vez.")
        chosen[item] = provider
    return [{"item": item, "provider": chosen[item]} for item in ITEMS if item in chosen]


def clean_notes(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise DomainError("Observações inválidas.")
    value = value.strip()
    if len(value) > NOTES_MAX_LENGTH:
        raise DomainError(f"As observações podem ter no máximo {NOTES_MAX_LENGTH} caracteres.")
    return value


def equipment_text(equipment):
    """Texto legível para a auditoria da edição: "Luvas (a empresa fornece); Botina (...)"."""
    if not equipment:
        return ""
    return "; ".join(
        f"{ITEMS.get(e['item'], e['item'])} ({PROVIDERS.get(e['provider'], e['provider'])})"
        for e in equipment
    )


def for_worker(vacancy):
    """O que o prestador vê: "Você precisa levar", "Fornecido pela empresa" e as observações."""
    equipment = vacancy.equipment or []
    return {
        "bring": [ITEMS[e["item"]] for e in equipment if e["provider"] == WORKER],
        "provided": [ITEMS[e["item"]] for e in equipment if e["provider"] == COMPANY],
        "notes": vacancy.equipment_notes,
    }
