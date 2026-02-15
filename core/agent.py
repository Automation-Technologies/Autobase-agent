"""
Главный класс агента.
Координирует работу всех компонентов.
"""
import asyncio
import logging
from typing import Dict, Any, List
from core.config_manager import ConfigManager
from core.proxy_manager import ProxyManager
from core.mafile_scanner import MaFileScanner
from core.websocket_client import WebSocketClient
from core.command_executor import CommandExecutor


class Agent:
    """Основной класс агента."""
    
    def __init__(
        self,
        config_path: str,
        proxies_path: str,
        mafiles_dir: str
    ):
        self.config_manager = ConfigManager(config_path)
        self.proxy_manager = ProxyManager(proxies_path)
        self.mafile_scanner = MaFileScanner(mafiles_dir)
        
        self.command_executor = CommandExecutor(mafiles_dir, self.proxy_manager)
        
        self.websocket_client: WebSocketClient = None
        self.is_running = False
        
        self.logger = logging.getLogger("Agent")
        
        # Callback для UI
        self.on_status_change_callback = None
        self.on_log_callback = None
    
    def set_callbacks(self, on_status_change, on_log) -> None:
        """Установить callback'и для UI."""
        self.on_status_change_callback = on_status_change
        self.on_log_callback = on_log
    
    async def start(self) -> None:
        """Запустить агента (Worker Mode)."""
        if self.is_running:
            self._log("Агент уже запущен")
            return
        
        self._log("Запуск агента...")
        
        # Загружаем конфиг
        server_url = self.config_manager.get_server_ip()
        agent_token = self.config_manager.get_agent_token()
        
        if not server_url or not agent_token:
            self._log("❌ Ошибка: Заполните настройки подключения")
            return
        
        # Сканируем аккаунты
        logins = self.mafile_scanner.get_logins()
        if not logins:
            self._log("⚠️ Нет аккаунтов в папке maFiles")
            return
        
        self._log(f"Найдено {len(logins)} аккаунтов")
        
        # Создаем WebSocket клиент
        self.websocket_client = WebSocketClient(
            server_url,
            agent_token,
            self._handle_command,
            self._on_connection_status_changed
        )
        
        # Подключаемся
        try:
            await self.websocket_client.connect(logins)
        except Exception as e:
            self._log(f"❌ Ошибка подключения: {e}")
            self.is_running = False
    
    async def stop(self) -> None:
        """Остановить агента."""
        if not self.is_running:
            self._log("Агент не запущен")
            return
        
        self._log("Остановка агента...")
        
        if self.websocket_client:
            await self.websocket_client.disconnect()
        
        self.command_executor.cleanup()
        self.is_running = False
        self._log("✅ Агент остановлен")
    
    async def trigger_ingestion(self) -> None:
        """Запустить процесс добавления новых аккаунтов."""
        self._log("🔍 Сканирование новых аккаунтов...")
        
        # Сканируем maFiles
        accounts = self.mafile_scanner.scan_accounts()
        logins = [acc["login"] for acc in accounts]
        
        if not logins:
            self._log("⚠️ Нет аккаунтов в папке maFiles")
            return
        
        self._log(f"Найдено {len(logins)} аккаунтов")
        
        # TODO: Отправить CHECK_EXISTENCE на сервер
        # TODO: Получить список новых аккаунтов
        # TODO: Для каждого нового аккаунта:
        #   - Залогиниться через steampy
        #   - Получить баланс с retry
        #   - Отправить REGISTER на сервер
        
        self._log("⚠️ Ingestion процесс требует реализации серверной части")
    
    def get_accounts_with_proxies(self) -> List[Dict[str, str]]:
        """Получить список аккаунтов с информацией о прокси."""
        accounts = self.mafile_scanner.scan_accounts()
        
        for account in accounts:
            login = account["login"]
            proxy = self.proxy_manager.get_proxy_for_login(login)
            account["proxy"] = proxy
        
        return accounts
    
    def save_proxy(self, login: str, proxy: str) -> None:
        """Сохранить прокси для аккаунта."""
        self.proxy_manager.set_proxy_for_login(login, proxy)
        self._log(f"✅ Прокси сохранен для {login}")
    
    def remove_proxy(self, login: str) -> None:
        """Удалить прокси для аккаунта."""
        self.proxy_manager.remove_proxy_for_login(login)
        self._log(f"✅ Прокси удален для {login} (Direct IP)")
    
    def save_config(self, server_ip: str, agent_token: str) -> None:
        """Сохранить конфигурацию."""
        self.config_manager.update_server_ip(server_ip)
        self.config_manager.update_agent_token(agent_token)
        self._log("✅ Конфигурация сохранена")
    
    def get_config(self) -> Dict[str, str]:
        """Получить текущую конфигурацию."""
        return {
            "server_ip": self.config_manager.get_server_ip(),
            "agent_token": self.config_manager.get_agent_token()
        }
    
    async def _handle_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Обработать команду от сервера."""
        cmd_type = command.get("cmd")
        login = command.get("login")
        
        self._log(f"📥 Команда: {cmd_type} для {login}")
        
        # Выполняем команду
        result = await self.command_executor.execute_command(command)
        
        self._log(f"📤 Ответ: {result.get('status')}")
        
        return result
    
    def _on_connection_status_changed(self, connected: bool) -> None:
        """Callback изменения статуса подключения."""
        self.is_running = connected
        
        if self.on_status_change_callback:
            self.on_status_change_callback(connected)
        
        if connected:
            self._log("✅ Подключено к серверу")
        else:
            self._log("❌ Отключено от сервера")
    
    def _log(self, message: str) -> None:
        """Логирование."""
        self.logger.info(message)
        
        if self.on_log_callback:
            self.on_log_callback(message)

