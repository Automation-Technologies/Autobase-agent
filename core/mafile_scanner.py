"""
Сканер maFiles.
Работает исключительно с in-memory словарём — диск не трогает.
"""
from typing import List, Dict, Optional


class MaFileScanner:
    """Предоставляет доступ к аккаунтам из in-memory словаря maFiles."""

    def __init__(self, mafiles_dict: Dict[str, dict]):
        self._mafiles_dict = mafiles_dict

    def scan_accounts(self) -> List[Dict[str, str]]:
        """
        Возвращает список аккаунтов из памяти.
        Формат: [{"login": "vasya", "steamid": "76561198...", "mafile_data": {...}}]
        """
        accounts: List[Dict] = []
        for login, data in self._mafiles_dict.items():
            accounts.append({
                "login": login,
                "steamid": data.get("Session", {}).get("SteamID", "Unknown"),
                "mafile_data": data,
            })
        return accounts

    def get_logins(self) -> List[str]:
        """Получить список логинов."""
        return list(self._mafiles_dict.keys())

    def get_mafile_data_by_login(self, login: str) -> Optional[dict]:
        """Получить данные maFile по логину."""
        login_lower = login.lower()
        for key, data in self._mafiles_dict.items():
            if key.lower() == login_lower:
                return data
        return None
