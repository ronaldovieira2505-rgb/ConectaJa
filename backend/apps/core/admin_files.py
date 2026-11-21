"""Arquivos privados no painel admin.

O `PrivateMediaStorage` não tem URL pública de propósito (`url()` lança `ValueError`), então
o widget padrão de arquivo do admin quebrava a página com erro 500. No painel, o arquivo
aparece só como link para o endpoint da API que já confere a permissão (admin, dono ou público,
conforme o arquivo), e não se troca o arquivo por ali: o envio passa pelas validações da API.
"""

from django.utils.html import format_html


def private_file_link(url, label="Abrir arquivo"):
    if not url:
        return "—"
    return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>', url, label)
