"""
Обработчик команд от сервера.
Выполняет команды через steampy.
"""
import logging
import time
from typing import Dict, Any

from core.proxy_manager import ProxyManager
from steampy.client import SteamClient


class CommandExecutor:
    """Выполняет команды от сервера через Steam API."""
    
    def __init__(self, mafiles_dir: str, proxy_manager: ProxyManager):
        self.mafiles_dir = mafiles_dir
        self.proxy_manager = proxy_manager
        self.logger = logging.getLogger("CommandExecutor")
        self.steam_clients: Dict[str, SteamClient] = {}
    
    async def execute_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Выполняет команду от сервера.
        command: {"cmd": "get_inventory", "login": "vasya", ...}
        """
        cmd_type = command.get("cmd")
        login = command.get("login")
        
        if not cmd_type or not login:
            return {"status": "error", "message": "Некорректная команда"}
        
        try:
            # Получаем или создаем Steam клиента
            steam_client = self._get_steam_client(login)
            
            # Маршрутизация команды
            if cmd_type == "get_inventory":
                result = self._get_inventory(steam_client, command)
            elif cmd_type == "get_wallet_balance":
                result = self._get_wallet_balance(steam_client)
            elif cmd_type == "send_trade_offer":
                result = self._send_trade_offer(steam_client, command)
            else:
                result = {"status": "error", "message": f"Неизвестная команда: {cmd_type}"}
            
            return result
            
        except Exception as e:
            self.logger.error(f"Ошибка выполнения команды {cmd_type} для {login}: {e}")
            return {"status": "error", "message": str(e)}
    
    def _get_steam_client(self, login: str) -> SteamClient:
        """Получить или создать Steam клиента для логина."""
        if login in self.steam_clients:
            return self.steam_clients[login]
        
        # Проверяем прокси
        proxy = self.proxy_manager.get_proxy_for_login(login)
        
        # Создаем клиента
        client = SteamClient("")  # API key не нужен для базовых операций
        
        # Логинимся (упрощенно, нужна полная реализация с maFile)
        # client.login(login, password, mafile_path)
        
        self.steam_clients[login] = client
        self.logger.info(f"Создан Steam клиент для {login} (proxy: {proxy or 'Direct'})")
        
        return client
    
    def _get_inventory(self, client: SteamClient, command: Dict[str, Any]) -> Dict[str, Any]:
        """Получить инвентарь."""
        game_id = command.get("game_id", "730")  # CS2 по умолчанию
        
        # Retry loop
        for attempt in range(1, 6):
            try:
                inventory = client.get_my_inventory(game_id)
                return {
                    "status": "success",
                    "inventory": inventory
                }
            except Exception as e:
                if attempt < 5:
                    wait_time = attempt  # 1s, 2s, 3s, 4s, 5s
                    self.logger.warning(f"Попытка {attempt} не удалась: {e}. Жду {wait_time}с...")
                    time.sleep(wait_time)
                else:
                    raise
        
        return {"status": "error", "message": "Не удалось получить инвентарь после 5 попыток"}
    
    def _get_wallet_balance(self, client: SteamClient) -> Dict[str, Any]:
        """Получить баланс кошелька."""
        for attempt in range(1, 6):
            try:
                balance_response = client.get_wallet_balance()
                return {
                    "status": "success",
                    "balance": balance_response["wallet_balance"],
                    "currency": balance_response["wallet_currency"]
                }
            except Exception as e:
                if attempt < 5:
                    wait_time = attempt
                    self.logger.warning(f"Попытка {attempt} не удалась: {e}. Жду {wait_time}с...")
                    time.sleep(wait_time)
                else:
                    raise
        
        return {"status": "error", "message": "Не удалось получить баланс после 5 попыток"}
    
    def _send_trade_offer(self, client: SteamClient, command: Dict[str, Any]) -> Dict[str, Any]:
        """Отправить трейд-оффер."""
        partner_id = command.get("partner_id")
        items = command.get("items", [])
        message = command.get("message", "")
        
        try:
            response = client.make_offer_with_url(
                items_to_give=items,
                items_to_receive=[],
                trade_offer_url=partner_id,
                message=message
            )
            return {
                "status": "success",
                "trade_offer_id": response.get("tradeofferid")
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def cleanup(self) -> None:
        """Закрыть все соединения."""
        for login, client in self.steam_clients.items():
            try:
                client.logout()
                self.logger.info(f"Logout для {login}")
            except:
                pass
        self.steam_clients.clear()

