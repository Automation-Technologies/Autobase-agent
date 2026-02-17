"""
Главный класс агента.
Координирует работу всех компонентов.
"""
import asyncio
import logging
from typing import Dict, Any, List

from steampy.client import SteamClient
from steampy.models import GameOptions

from core.config_manager import ConfigManager
from core.proxy_manager import ProxyManager
from core.mafile_scanner import MaFileScanner
from core.websocket_client import WebSocketClient
from core.command_executor import CommandExecutor
from core.ingestion_client import IngestionClient


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
        """Запустить процесс добавления новых аккаунтов (Smart Ingestion)."""
        self._log("🔍 Сканирование новых аккаунтов...")

        # Сканируем maFiles
        accounts = self.mafile_scanner.scan_accounts()

        if not accounts:
            self._log("⚠️ Нет аккаунтов в папке maFiles")
            return

        self._log(f"Найдено {len(accounts)} аккаунтов в maFiles")

        # Конфиг для связи с AgentGateway (используем server_ip как HTTP URL)
        server_url = self.config_manager.get_server_ip()
        agent_token = self.config_manager.get_agent_token()

        if not server_url or not agent_token:
            self._log("❌ Ошибка: заполните Server IP и Agent Token в настройках")
            return

        ingestion_client = IngestionClient(server_url, agent_token)

        # CHECK_EXISTENCE
        check_payload = [
            {"login": acc["login"]}
            for acc in accounts
        ]

        self._log("📡 Отправка CHECK_EXISTENCE в AgentGateway...")
        check_result = await ingestion_client.check_existence(check_payload)

        existing = check_result.get("existing", [])
        new_logins = check_result.get("new", [])

        self._log(f"✅ Уже есть в системе: {len(existing)}")
        self._log(f"🆕 Новых аккаунтов: {len(new_logins)}")

        if not new_logins:
            self._log("✅ Новых аккаунтов для регистрации нет")
            return

        # Для новых аккаунтов: получить баланс и зарегистрировать
        to_register: List[Dict[str, Any]] = []

        for acc in accounts:
            login = acc["login"]
            if login not in new_logins:
                continue

            self._log(f"💼 Получение баланса для {login}...")

            try:
                mafile_path = acc["filepath"]

                # Инициализируем локальный SteamClient по maFile без пароля,
                # используя сохраненную сессию и steamid
                client = SteamClient(api_key="", username=login, password=None, steam_guard=None)

                # Загружаем maFile
                import json
                from pathlib import Path

                with open(Path(mafile_path), "r", encoding="utf-8") as f:
                    ma_data = json.load(f)

                client.steam_guard = {
                    "steamid": ma_data.get("Session", {}).get("SteamID"),
                }

                # Проставляем куки сессии из maFile
                session_data = ma_data.get("Session", {})
                session_id = session_data.get("SessionID")
                steam_login_secure = session_data.get("SteamLoginSecure")

                if not session_id or not steam_login_secure:
                    self._log(f"❌ maFile для {login} не содержит валидной сессии")
                    continue

                domain_community = "steamcommunity.com"
                domain_store = "store.steampowered.com"

                client._session.cookies.set("sessionid", session_id, domain=domain_community)
                client._session.cookies.set("steamLoginSecure", steam_login_secure, domain=domain_community)
                client._session.cookies.set("sessionid", session_id, domain=domain_store)
                client._session.cookies.set("steamLoginSecure", steam_login_secure, domain=domain_store)

                client.was_login_executed = True

                # Получаем баланс
                wallet_info = client.get_wallet_balance(convert_to_decimal=True)

                balance = wallet_info.get("balance")
                currency = wallet_info.get("wallet_currency")

                self._log(f"💰 Баланс {login}: {balance} (currency={currency})")

                to_register.append(
                    {
                        "login": login,
                        "balance": balance,
                        "currency": currency,
                    }
                )

            except Exception as e:
                self._log(f"❌ Ошибка при получении баланса для {login}: {e}")
                continue

        if not to_register:
            self._log("⚠️ Не удалось подготовить ни одного аккаунта к регистрации")
            return

        self._log(f"📡 Отправка REGISTER для {len(to_register)} аккаунтов...")
        register_result = await ingestion_client.register_accounts(to_register)

        created = register_result.get("created", [])
        skipped = register_result.get("skipped", [])

        self._log(f"✅ Зарегистрировано: {len(created)}")
        if skipped:
            self._log(f"⚠️ Пропущено (уже существуют или ошибка): {len(skipped)}")
    
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

