import keyring

SERVICE = "MacooiiDesktop"


def get_api_key() -> str:
    return keyring.get_password(SERVICE, "gemini") or ""


def set_api_key(value: str):
    if value.strip():
        keyring.set_password(SERVICE, "gemini", value.strip())
    else:
        try:
            keyring.delete_password(SERVICE, "gemini")
        except keyring.errors.PasswordDeleteError:
            pass
