"""
Менеджер конфигурации агента.
Управляет config.json (связь с сервером).
"""
import json
import os
from pathlib import Path
from typing import Dict


class ConfigManager:
    """Управление config.json - параметры подключения к серверу."""
    
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self._ensure_config_exists()
    
    def _ensure_config_exists(self) -> None:
        """Создает конфиг если его нет."""
        if not self.config_path.exists():
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            default_config = {
                "server_ip": "",
                "agent_token": ""
            }
            self.save_config(default_config)
    
    def load_config(self) -> Dict[str, str]:
        """Загружает конфигурацию из файла."""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def save_config(self, config: Dict[str, str]) -> None:
        """Сохраняет конфигурацию в файл."""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    
    def get_server_ip(self) -> str:
        """Получить IP сервера."""
        config = self.load_config()
        return config["server_ip"]
    
    def get_agent_token(self) -> str:
        """Получить токен агента."""
        config = self.load_config()
        return config["agent_token"]
    
    def update_server_ip(self, server_ip: str) -> None:
        """Обновить IP сервера."""
        config = self.load_config()
        config["server_ip"] = server_ip
        self.save_config(config)
    
    def update_agent_token(self, token: str) -> None:
        """Обновить токен агента."""
        config = self.load_config()
        config["agent_token"] = token
        self.save_config(config)

