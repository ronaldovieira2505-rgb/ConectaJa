"""Imagens enviadas pelos usuários (foto do local, logo): formato e tamanho aceitos."""

from apps.core.exceptions import DomainError

MAX_IMAGE_BYTES = 5 * 1024 * 1024

INVALID_FORMAT = "Envie a imagem em JPG, PNG ou WebP."
TOO_LARGE = "A imagem pode ter no máximo 5 MB."
MISSING = "Selecione uma imagem."

CONTENT_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def detect_format(head):
    """Identifica o formato pelos primeiros bytes; a extensão do arquivo não é confiável."""
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def validate_image(uploaded):
    """Confere tamanho e formato e devolve a extensão a usar no nome do arquivo."""
    if uploaded is None:
        raise DomainError(MISSING)
    if uploaded.size > MAX_IMAGE_BYTES:
        raise DomainError(TOO_LARGE)
    extension = detect_format(uploaded.read(12))
    uploaded.seek(0)
    if extension is None:
        raise DomainError(INVALID_FORMAT)
    return extension


def content_type_of(name):
    return CONTENT_TYPES.get(name.rsplit(".", 1)[-1].lower(), "application/octet-stream")


def version_of(name):
    """Parte do nome que muda a cada envio; vai no endereço para evitar o cache antigo."""
    return name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
