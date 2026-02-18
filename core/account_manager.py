"""
Менеджер хранения данных аккаунтов (пароли, путь к maFile).
"""
import json
from pathlib import Path
from typing import Dict, Optional


class AccountManager:
    """Управление данными аккаунтов (пароль, путь к maFile, API key)."""

    def __init__(self, storage_path: str):
        self.storage_file = Path(storage_path)
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_file.exists():
            self._write_storage({})

    def _read_storage(self) -> Dict[str, Dict[str, str]]:
        """Прочитать файл с данными аккаунтов."""
        try:
            with open(self.storage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
                return {}
        except Exception:
            return {}

    def _write_storage(self, data: Dict[str, Dict[str, str]]) -> None:
        """Записать данные аккаунтов в файл."""
        with open(self.storage_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def set_account(self, login: str, password: str, mafile_path: str, api_key: str) -> None:
        """Создать или обновить запись аккаунта."""
        storage = self._read_storage()
        login_lower = login.lower()
        for key in list(storage.keys()):
            if key.lower() == login_lower:
                del storage[key]
        storage[login_lower] = {
            "password": password,
            "mafile_path": mafile_path,
            "api_key": api_key,
        }
        self._write_storage(storage)

    def get_password(self, login: str) -> Optional[str]:
        """Получить пароль аккаунта по логину."""
        storage = self._read_storage()
        login_lower = login.lower()
        for key, account in storage.items():
            if key.lower() == login_lower:
                return account.get("password")
        return None

    def get_mafile_path(self, login: str) -> Optional[str]:
        """Получить путь к maFile по логину."""
        storage = self._read_storage()
        login_lower = login.lower()
        for key, account in storage.items():
            if key.lower() == login_lower:
                return account.get("mafile_path")
        return None

    def get_api_key(self, login: str) -> Optional[str]:
        """Получить API key по логину."""
        storage = self._read_storage()
        login_lower = login.lower()
        for key, account in storage.items():
            if key.lower() == login_lower:
                return account.get("api_key")
        return None

    def get_login_cookies(self, login: str) -> Optional[Dict[str, str]]:
        """Получить сохранённые login_cookies по логину."""
        storage = self._read_storage()
        login_lower = login.lower()
        for key, account in storage.items():
            if key.lower() == login_lower:
                cookies = account.get("login_cookies")
                if isinstance(cookies, dict):
                    return cookies
                return None
        return None

    def set_login_cookies(self, login: str, cookies: Dict[str, str]) -> None:
        """Сохранить login_cookies для логина (перезаписывает только этот ключ)."""
        storage = self._read_storage()
        login_lower = login.lower()
        for key in list(storage.keys()):
            if key.lower() == login_lower:
                account = storage[key]
                account["login_cookies"] = cookies
                storage[key] = account
                self._write_storage(storage)
                return

    def remove_account(self, login: str) -> None:
        """Удалить запись аккаунта."""
        storage = self._read_storage()
        login_lower = login.lower()
        for key in list(storage.keys()):
            if key.lower() == login_lower:
                del storage[key]
                self._write_storage(storage)
                break


