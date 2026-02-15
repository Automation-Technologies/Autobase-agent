"""
Сканер maFiles.
Находит все аккаунты в папке maFiles.
"""
import json
from pathlib import Path
from typing import List, Dict


class MaFileScanner:
    """Сканирование папки maFiles."""
    
    def __init__(self, mafiles_dir: str):
        self.mafiles_dir = Path(mafiles_dir)
    
    def scan_accounts(self) -> List[Dict[str, str]]:
        """
        Сканирует папку maFiles и возвращает список аккаунтов.
        Возвращает: [{"login": "vasya", "steamid": "76561198...", "filepath": "..."}]
        """
        if not self.mafiles_dir.exists():
            self.mafiles_dir.mkdir(parents=True, exist_ok=True)
            return []
        
        accounts = []
        for mafile_path in self.mafiles_dir.glob("*.maFile"):
            try:
                with open(mafile_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    accounts.append({
                        "login": data.get("account_name", "Unknown"),
                        "steamid": data.get("Session", {}).get("SteamID", "Unknown"),
                        "filepath": str(mafile_path)
                    })
            except Exception as e:
                # Пропускаем битые файлы
                continue
        
        return accounts
    
    def get_logins(self) -> List[str]:
        """Получить список логинов."""
        accounts = self.scan_accounts()
        return [acc["login"] for acc in accounts]

