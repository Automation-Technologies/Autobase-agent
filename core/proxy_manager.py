"""
Менеджер прокси.
Управляет proxies.json - привязка логинов к прокси.
"""
import json
from pathlib import Path
from typing import Dict, Optional, List


class ProxyManager:
    """Управление proxies.json - привязки аккаунтов к прокси."""
    
    def __init__(self, proxies_path: str):
        self.proxies_path = Path(proxies_path)
        self._ensure_proxies_exists()
    
    def _ensure_proxies_exists(self) -> None:
        """Создает файл прокси если его нет."""
        if not self.proxies_path.exists():
            self.proxies_path.parent.mkdir(parents=True, exist_ok=True)
            self.save_proxies({})
    
    def load_proxies(self) -> Dict[str, str]:
        """Загружает привязки прокси из файла."""
        with open(self.proxies_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def save_proxies(self, proxies: Dict[str, str]) -> None:
        """Сохраняет привязки прокси в файл."""
        with open(self.proxies_path, 'w', encoding='utf-8') as f:
            json.dump(proxies, f, indent=2, ensure_ascii=False)
    
    def get_proxy_for_login(self, login: str) -> Optional[str]:
        """Получить прокси для логина. None = Direct IP."""
        proxies = self.load_proxies()
        return proxies.get(login)
    
    def set_proxy_for_login(self, login: str, proxy: str) -> None:
        """Установить прокси для логина."""
        proxies = self.load_proxies()
        proxies[login] = proxy
        self.save_proxies(proxies)
    
    def remove_proxy_for_login(self, login: str) -> None:
        """Удалить прокси для логина (перейти на Direct IP)."""
        proxies = self.load_proxies()
        if login in proxies:
            del proxies[login]
            self.save_proxies(proxies)
    
    def get_all_logins(self) -> List[str]:
        """Получить список всех логинов с настроенными прокси."""
        proxies = self.load_proxies()
        return list(proxies.keys())

