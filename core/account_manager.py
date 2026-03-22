"""
Менеджер хранения данных аккаунтов (пароли, API ключи, куки сессий).
Все данные хранятся в оперативной памяти. Сброс на диск — только в зашифрованном виде.
"""
import json
from pathlib import Path
from typing import Dict, Optional

from cryptography.fernet import Fernet


class AccountManager:
    """Управление данными аккаунтов с in-memory кешем и Fernet-шифрованием при записи."""

    def __init__(self, fernet_key: bytes, storage_path: Path):
        self._fernet = Fernet(fernet_key)
        self._storage_path = storage_path
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, Dict] = self._load_from_disk()

    def _load_from_disk(self) -> Dict[str, Dict]:
        """Загружает данные с диска в кеш при старте."""
        if not self._storage_path.exists():
            return {}
        try:
            encrypted = self._storage_path.read_bytes()
            decrypted = self._fernet.decrypt(encrypted)
            data = json.loads(decrypted.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _flush(self, data: Dict) -> None:
        """Шифрует переданный словарь и атомарно пишет на диск."""
        json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self._storage_path.write_bytes(self._fernet.encrypt(json_bytes))

    def _save(self) -> None:
        """Сбрасывает текущий кеш на диск в зашифрованном виде."""
        self._flush(self._cache)

    def set_account(self, login: str, password: str, api_key: str) -> None:
        """Создать или обновить запись аккаунта."""
        login_lower = login.lower()
        for key in list(self._cache.keys()):
            if key.lower() == login_lower:
                del self._cache[key]
        self._cache[login_lower] = {
            "password": password,
            "api_key": api_key,
        }
        self._save()

    def get_password(self, login: str) -> Optional[str]:
        """Получить пароль аккаунта по логину."""
        login_lower = login.lower()
        for key, account in self._cache.items():
            if key.lower() == login_lower:
                return account.get("password")
        return None

    def get_api_key(self, login: str) -> Optional[str]:
        """Получить API key по логину."""
        login_lower = login.lower()
        for key, account in self._cache.items():
            if key.lower() == login_lower:
                return account.get("api_key")
        return None

    def get_login_cookies(self, login: str) -> Optional[Dict[str, str]]:
        """Получить сохранённые login_cookies по логину."""
        login_lower = login.lower()
        for key, account in self._cache.items():
            if key.lower() == login_lower:
                cookies = account.get("login_cookies")
                return cookies if isinstance(cookies, dict) else None
        return None

    def set_login_cookies(self, login: str, cookies: Dict[str, str]) -> None:
        """Сохранить login_cookies для логина и сбросить кеш на диск."""
        login_lower = login.lower()
        for key in list(self._cache.keys()):
            if key.lower() == login_lower:
                self._cache[key]["login_cookies"] = cookies
                self._save()
                return

    def remove_account(self, login: str) -> None:
        """Удалить запись аккаунта."""
        login_lower = login.lower()
        for key in list(self._cache.keys()):
            if key.lower() == login_lower:
                del self._cache[key]
                self._save()
                return
