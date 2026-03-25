"""
Главный класс агента.
Координирует работу всех компонентов.
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

import aiohttp
from cryptography.fernet import Fernet

from core.account_manager import AccountManager
from core.command_executor import CommandExecutor
from core.config_manager import ConfigManager
from core.ingestion_client import IngestionClient
from core.server_settings import ServerSettings
from core.mafile_scanner import MaFileScanner
from core.mafile_steam_guard import MafileSteamGuard
from core.proxy_manager import ProxyManager
from core.websocket_client import WebSocketClient
from steampy.client import SteamClient
from steampy.models import Currency


class Agent:
    """Основной класс агента."""

    def __init__(
            self,
            config_path: str,
            proxies_path: str,
            mafiles_dir: str,
            fernet_key: bytes,
            mafiles_dict: Dict[str, dict],
            accounts_storage_path: Path,
    ):
        self._fernet = Fernet(fernet_key)
        self._mafiles_dir = Path(mafiles_dir)
        self._mafiles_dict = mafiles_dict

        self.config_manager = ConfigManager(config_path)
        self.proxy_manager = ProxyManager(proxies_path)
        self.mafile_scanner = MaFileScanner(mafiles_dict)
        self.account_manager = AccountManager(fernet_key, accounts_storage_path)

        self.command_executor = CommandExecutor(
            mafiles_dict,
            self.proxy_manager,
            self.account_manager
        )

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

        server_url = ServerSettings.WS_URL
        agent_token = self.config_manager.get_agent_token()

        if not agent_token:
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

        server_url = ServerSettings.HTTP_URL
        agent_token = self.config_manager.get_agent_token()

        if not agent_token:
            self._log("❌ Ошибка: заполните Agent Token в настройках")
            return

        ingestion_client = IngestionClient(server_url, agent_token)

        # CHECK_EXISTENCE
        check_payload = [
            {"login": acc["login"]}
            for acc in accounts
        ]

        self._log("📡 Отправка CHECK_EXISTENCE в AgentGateway...")
        try:
            check_result = await ingestion_client.check_existence(check_payload)
        except aiohttp.ClientResponseError as e:
            if e.status == 401:
                self._log("❌ Токен не рабочий")
                return
            raise

        existing = check_result.get("existing", [])
        new_logins = check_result.get("new", [])

        self._log(f"✅ Уже есть в системе: {len(existing)}")
        if existing:
            self._log(f"   Существующие логины: {existing}")
        self._log(f"🆕 Новых аккаунтов: {len(new_logins)}")
        if new_logins:
            self._log(f"   Новые логины: {new_logins}")

        if not new_logins:
            self._log("✅ Новых аккаунтов для регистрации нет")
            return

        # Для новых аккаунтов: получить баланс и зарегистрировать
        to_register: List[Dict[str, Any]] = []
        skipped_existing = 0

        for acc in accounts:
            login = acc["login"]
            if login not in new_logins:
                continue

            # Пропускаем аккаунты, которые уже существуют в системе
            if login in existing:
                self._log(f"⏭️ Пропускаем {login} - уже существует в системе")
                skipped_existing += 1
                continue

            self._log(f"💼 Получение баланса для {login} через логин по паролю и maFile...")

            client = None
            try:
                password = self.account_manager.get_password(login)
                if password is None:
                    self._log(f"❌ В maFiles/accounts.json нет пароля для {login}, пропускаем аккаунт")
                    continue

                api_key = self.account_manager.get_api_key(login)
                if api_key is None:
                    self._log(f"❌ В maFiles/accounts.json нет API key для {login}, пропускаем аккаунт")
                    continue

                ma_data = acc["mafile_data"]

                try:
                    steam_guard_data = MafileSteamGuard.build_dict(ma_data, login)
                except ValueError as e:
                    self._log(f"❌ {e}")
                    continue

                proxy_string = self.proxy_manager.get_proxy_for_login(login)
                if proxy_string is None or proxy_string == "":
                    self._log(f"🌐 Для {login} прокси не задан, логинимся по прямому IP")
                    client_proxies = None
                else:
                    self._log(f"🌐 Для {login} используется прокси: {proxy_string}")
                    client_proxies = {
                        "http": proxy_string,
                        "https": proxy_string,
                    }

                client = SteamClient(api_key, proxies=client_proxies)

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    client.login,
                    login,
                    password,
                    steam_guard_data,
                )

                is_alive = await loop.run_in_executor(None, client.is_session_alive)
                if not is_alive:
                    self._log(f"❌ Сессия неактивна после логина для {login}")
                    continue

                wallet_info = await loop.run_in_executor(
                    None, client.get_wallet_balance, True
                )

                balance = wallet_info.get("balance")
                currency_code = wallet_info.get("wallet_currency")

                currency_enum = Currency(currency_code)
                currency_name = currency_enum.name

                self._log(f"💰 Баланс {login}: {balance} (currency={currency_name})")

                to_register.append(
                    {
                        "login": login,
                        "balance": balance,
                        "currency": currency_name,
                        "bot_id": 3,
                        "is_active": 0,
                    }
                )

            except Exception as e:
                self._log(f"❌ Ошибка при получении баланса для {login}: {e}")
                continue
            finally:
                if client is not None and hasattr(client, "logout"):
                    try:
                        await asyncio.get_event_loop().run_in_executor(None, client.logout)
                    except Exception:
                        pass

        if not to_register:
            if skipped_existing > 0:
                self._log(f"✅ Все аккаунты уже существуют в системе (пропущено: {skipped_existing})")
            else:
                self._log("⚠️ Не удалось подготовить ни одного аккаунта к регистрации")
            return

        self._log(f"📡 Отправка REGISTER для {len(to_register)} аккаунтов...")
        try:
            register_result = await ingestion_client.register_accounts(to_register)
        except aiohttp.ClientResponseError as e:
            if e.status == 401:
                self._log("❌ Токен не рабочий")
                return
            raise

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

    def save_config(self, agent_token: str) -> None:
        """Сохранить конфигурацию."""
        self.config_manager.update_agent_token(agent_token)
        self._log("✅ Конфигурация сохранена")

    def save_account_credentials(self, login: str, password: str, mafile_path: str, api_key: str) -> None:
        """
        Сохранить данные аккаунта.
        Читает maFile с диска, добавляет в in-memory словарь,
        шифрует и сохраняет как .enc — plaintext на диске не остаётся.
        """
        source = Path(mafile_path)
        try:
            with open(source, "r", encoding="utf-8") as f:
                ma_data = json.load(f)
        except Exception as e:
            self._log(f"❌ Не удалось прочитать maFile {mafile_path}: {e}")
            return

        login_lower = login.lower()
        self._mafiles_dict[login_lower] = ma_data

        enc_path = self._mafiles_dir / (source.name + ".enc")
        json_bytes = json.dumps(ma_data, ensure_ascii=False, indent=2).encode("utf-8")
        enc_path.write_bytes(self._fernet.encrypt(json_bytes))

        # Удаляем plaintext если он лежит внутри mafiles_dir
        if source.parent.resolve() == self._mafiles_dir.resolve() and source.exists():
            source.unlink()

        self.account_manager.set_account(login_lower, password, api_key)
        self._log(f"✅ Данные аккаунта сохранены для {login}")

    def delete_account(self, login: str) -> None:
        """Полностью удалить аккаунт: .enc файл с диска, из памяти, прокси и запись в accounts.json.enc."""
        login_lower = login.lower()

        # Удаляем .enc файл с диска (ищем по совпадению account_name внутри)
        for enc_file in self._mafiles_dir.glob("*.maFile.enc"):
            try:
                decrypted = self._fernet.decrypt(enc_file.read_bytes())
                data = json.loads(decrypted.decode("utf-8"))
                if data.get("account_name", "").lower() == login_lower:
                    enc_file.unlink()
                    break
            except Exception:
                continue

        self._mafiles_dict.pop(login_lower, None)
        self.proxy_manager.remove_proxy_for_login(login)
        self.account_manager.remove_account(login)
        self._log(f"🗑️ Аккаунт {login} и все его данные удалены")

    def get_config(self) -> Dict[str, str]:
        """Получить текущую конфигурацию."""
        return {
            "agent_token": self.config_manager.get_agent_token()
        }

    async def _handle_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Обработать команду от сервера."""
        cmd_type = command.get("cmd")
        login = command.get("account_login")

        self._log(f"[{login}] 📥 Команда: {cmd_type}")

        # Выполняем команду
        result = await self.command_executor.execute_command(command)

        self._log(f"[{login}] 📤 Ответ: {result.get('status')}")

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
