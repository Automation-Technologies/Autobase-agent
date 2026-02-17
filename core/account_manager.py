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
        storage[login] = {
            "password": password,
            "mafile_path": mafile_path,
            "api_key": api_key,
        }
        self._write_storage(storage)

    def get_password(self, login: str) -> Optional[str]:
        """Получить пароль аккаунта по логину."""
        storage = self._read_storage()
        account = storage.get(login)
        if account is None:
            return None
        return account.get("password")

    def get_mafile_path(self, login: str) -> Optional[str]:
        """Получить путь к maFile по логину."""
        storage = self._read_storage()
        account = storage.get(login)
        if account is None:
            return None
        return account.get("mafile_path")

    def get_api_key(self, login: str) -> Optional[str]:
        """Получить API key по логину."""
        storage = self._read_storage()
        account = storage.get(login)
        if account is None:
            return None
        return account.get("api_key")

    def remove_account(self, login: str) -> None:
        """Удалить запись аккаунта."""
        storage = self._read_storage()
        if login in storage:
            del storage[login]
            self._write_storage(storage)


