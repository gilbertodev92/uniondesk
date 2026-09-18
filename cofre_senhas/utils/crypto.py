import base64
import os

from django.conf import settings
from cryptography.fernet import Fernet

# nome da var de ambiente
ENV_KEY_NAME = "COFRE_MASTER_KEY"


def get_master_key() -> bytes:
    """
    Retorna a chave mestra em bytes, buscando primeiro no ambiente
    e depois no settings.py.

    Se não existir, lança RuntimeError.
    """
    # 1) tenta ambiente
    key = os.getenv(ENV_KEY_NAME)

    # 2) se não tiver no ambiente, tenta no settings
    if not key:
        key = getattr(settings, ENV_KEY_NAME, None)

    if not key:
        # aqui é exatamente o erro que você viu
        raise RuntimeError(f"Chave mestra não encontrada. Defina {ENV_KEY_NAME}.")

    # a chave que você gerou já está em base64 (Fernet.generate_key())
    # então precisamos garantir que está em bytes
    if isinstance(key, str):
        key = key.encode()

    return key


def get_fernet_for_record(record_salt: str | None = None) -> Fernet:
    """
    Se quiser no futuro fazer uma chave 'por registro' (usando salt),
    dá pra derivar aqui. Por enquanto vamos usar a mesma chave mestra.
    """
    master = get_master_key()

    # se um dia quiser usar salt, dá pra compor aqui
    # por enquanto: usa direto
    return Fernet(master)


def encrypt_text(plaintext: str, record_salt: str | None = None) -> str:
    if plaintext is None:
        return ""
    f = get_fernet_for_record(record_salt)
    token = f.encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_text(ciphertext: str, record_salt: str | None = None) -> str:
    if not ciphertext:
        return ""
    f = get_fernet_for_record(record_salt)
    value = f.decrypt(ciphertext.encode("utf-8"))
    return value.decode("utf-8")
