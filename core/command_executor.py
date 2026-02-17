"""
Обработчик команд от сервера.
Выполняет команды через steampy.
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from core.account_manager import AccountManager
from core.proxy_manager import ProxyManager
from steampy.client import SteamClient


class CommandExecutor:
    """Выполняет команды от сервера через Steam API."""

    def __init__(
            self,
            mafiles_dir: str,
            proxy_manager: ProxyManager,
            account_manager: AccountManager
    ):
        self.mafiles_dir = mafiles_dir
        self.proxy_manager = proxy_manager
        self.account_manager = account_manager
        self.logger = logging.getLogger("CommandExecutor")
        self.steam_clients: Dict[str, SteamClient] = {}

    async def execute_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Выполняет команду от сервера.
        command: {"cmd": "get_inventory", "account_login": "vasya", "args": {...}, "request_id": "..."}
        """
        cmd_type = command.get("cmd")
        login = command.get("account_login") or command.get("login")
        request_id = command.get("request_id")

        if not cmd_type or not login:
            return {
                "status": "error",
                "message": "Некорректная команда: отсутствует cmd или login",
                "request_id": request_id
            }

        try:
            # Получаем или создаем Steam клиента (с логином)
            steam_client = await self._get_steam_client(login)

            if steam_client is None:
                return {
                    "status": "error",
                    "message": f"Не удалось создать Steam клиент для {login}",
                    "request_id": request_id
                }

            # Маршрутизация команды
            args = command.get("args", {})

            if cmd_type == "get_my_inventory":
                result = await self._get_my_inventory(steam_client, args)
            elif cmd_type == "get_partner_inventory":
                result = await self._get_partner_inventory(steam_client, args)
            elif cmd_type == "get_wallet_balance":
                result = await self._get_wallet_balance(steam_client, args)
            elif cmd_type == "send_trade_offer" or cmd_type == "make_offer":
                result = await self._send_trade_offer(steam_client, args)
            elif cmd_type == "is_session_alive":
                result = await self._is_session_alive(steam_client)
            elif cmd_type == "get_trade_offers":
                result = await self._get_trade_offers(steam_client, args)
            elif cmd_type == "get_trade_offer":
                result = await self._get_trade_offer(steam_client, args)
            else:
                result = {"status": "error", "message": f"Неизвестная команда: {cmd_type}"}

            # Добавляем request_id в результат
            result["request_id"] = request_id

            return result

        except Exception as e:
            self.logger.error(f"Ошибка выполнения команды {cmd_type} для {login}: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e),
                "request_id": request_id
            }

    async def _get_steam_client(self, login: str) -> Optional[SteamClient]:
        """Получить или создать Steam клиента для логина."""
        # Если клиент уже создан и залогинен, возвращаем его
        if login in self.steam_clients:
            client = self.steam_clients[login]
            # Проверяем, что сессия жива
            try:
                loop = asyncio.get_event_loop()
                is_alive = await loop.run_in_executor(None, client.is_session_alive)
                if is_alive:
                    return client
                else:
                    # Сессия мертва, удаляем и перелогиниваемся
                    self.logger.warning(f"Сессия для {login} неактивна, перелогиниваемся")
                    del self.steam_clients[login]
            except Exception as e:
                self.logger.warning(f"Ошибка проверки сессии для {login}: {e}, перелогиниваемся")
                del self.steam_clients[login]

        # Получаем данные аккаунта
        password = self.account_manager.get_password(login)
        mafile_path = self.account_manager.get_mafile_path(login)
        api_key = self.account_manager.get_api_key(login)

        if not password:
            self.logger.error(f"Для {login} не найден пароль в accounts.json")
            return None

        if not mafile_path:
            self.logger.error(f"Для {login} не найден путь к maFile в accounts.json")
            return None

        if not api_key:
            self.logger.error(f"Для {login} не найден API key в accounts.json")
            return None

        # Проверяем, что maFile существует
        mafile_path_obj = Path(mafile_path)
        if not mafile_path_obj.exists():
            self.logger.error(f"maFile не найден по пути: {mafile_path}")
            return None

        # Читаем maFile
        try:
            with open(mafile_path_obj, "r", encoding="utf-8") as f:
                ma_data = json.load(f)
        except Exception as e:
            self.logger.error(f"Ошибка чтения maFile для {login}: {e}")
            return None

        steamid = ma_data.get("Session", {}).get("SteamID")
        shared_secret = ma_data.get("shared_secret")
        identity_secret = ma_data.get("identity_secret")

        if not steamid or not shared_secret or not identity_secret:
            self.logger.error(
                f"maFile для {login} не содержит необходимых полей (steamid/shared_secret/identity_secret)")
            return None

        steam_guard_data = {
            "steamid": steamid,
            "shared_secret": shared_secret,
            "identity_secret": identity_secret,
        }

        # Получаем прокси
        proxy_string = self.proxy_manager.get_proxy_for_login(login)
        client_proxies = None
        if proxy_string and proxy_string != "":
            client_proxies = {
                "http": proxy_string,
                "https": proxy_string,
            }
            self.logger.info(f"Для {login} используется прокси: {proxy_string}")
        else:
            self.logger.info(f"Для {login} используется прямое подключение (без прокси)")

        # Создаем клиента
        client = SteamClient(api_key, proxies=client_proxies)

        # Логинимся (синхронно, но в executor)
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None,
                client.login,
                login,
                password,
                steam_guard_data
            )

            # Проверяем, что логин успешен
            is_alive = await loop.run_in_executor(None, client.is_session_alive)
            if not is_alive:
                self.logger.error(f"Логин для {login} выполнен, но сессия неактивна")
                return None

            self.steam_clients[login] = client
            self.logger.info(f"✅ Steam клиент создан и залогинен для {login}")

            return client

        except Exception as e:
            self.logger.error(f"Ошибка логина для {login}: {e}", exc_info=True)
            return None

    async def _get_my_inventory(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Получить мой инвентарь."""
        from steampy.models import GameOptions

        # Получаем параметры из args (формат из RemoteSteamClient)
        app_id = args.get("app_id", "730")  # CS2 по умолчанию
        context_id = args.get("context_id", "2")
        merge = args.get("merge", True)
        count = args.get("count", 5000)

        # Определяем GameOptions
        if app_id == "730":
            game = GameOptions.CS
        elif app_id == "570":
            game = GameOptions.DOTA2
        elif app_id == "440":
            game = GameOptions.TF2
        elif app_id == "753":
            game = GameOptions.STEAM
        else:
            # Создаем кастомный GameOptions
            game = GameOptions(app_id, context_id)

        loop = asyncio.get_event_loop()

        # Retry loop
        for attempt in range(1, 6):
            try:
                inventory = await loop.run_in_executor(
                    None,
                    client.get_my_inventory,
                    game,
                    merge
                )
                return {
                    "status": "success",
                    "result": inventory
                }
            except Exception as e:
                if attempt < 5:
                    wait_time = attempt  # 1s, 2s, 3s, 4s, 5s
                    self.logger.warning(f"Попытка {attempt} не удалась: {e}. Жду {wait_time}с...")
                    await asyncio.sleep(wait_time)
                else:
                    raise

        return {"status": "error", "message": "Не удалось получить инвентарь после 5 попыток"}

    async def _get_partner_inventory(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Получить инвентарь партнера."""
        from steampy.models import GameOptions

        partner_steam_id = args.get("partner_steam_id")
        app_id = args.get("app_id", "730")
        context_id = args.get("context_id", "2")
        merge = args.get("merge", True)
        count = args.get("count", 5000)

        if not partner_steam_id:
            return {"status": "error", "message": "Не указан partner_steam_id"}

        # Определяем GameOptions
        if app_id == "730":
            game = GameOptions.CS
        elif app_id == "570":
            game = GameOptions.DOTA2
        elif app_id == "440":
            game = GameOptions.TF2
        elif app_id == "753":
            game = GameOptions.STEAM
        else:
            game = GameOptions(app_id, context_id)

        loop = asyncio.get_event_loop()

        for attempt in range(1, 6):
            try:
                inventory = await loop.run_in_executor(
                    None,
                    client.get_partner_inventory,
                    partner_steam_id,
                    game,
                    merge,
                    count
                )
                return {
                    "status": "success",
                    "result": inventory
                }
            except Exception as e:
                if attempt < 5:
                    wait_time = attempt
                    self.logger.warning(f"Попытка {attempt} не удалась: {e}. Жду {wait_time}с...")
                    await asyncio.sleep(wait_time)
                else:
                    raise

        return {"status": "error", "message": "Не удалось получить инвентарь партнера после 5 попыток"}

    async def _is_session_alive(self, client: SteamClient) -> Dict[str, Any]:
        """Проверить, активна ли сессия."""
        loop = asyncio.get_event_loop()

        try:
            is_alive = await loop.run_in_executor(None, client.is_session_alive)
            return {
                "status": "success",
                "result": is_alive
            }
        except Exception as e:
            self.logger.error(f"Ошибка проверки сессии: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    async def _get_trade_offers(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Получить список трейд офферов."""
        merge = args.get("merge", True)
        loop = asyncio.get_event_loop()

        try:
            offers = await loop.run_in_executor(
                None,
                client.get_trade_offers,
                merge
            )
            return {
                "status": "success",
                "result": offers
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения трейд офферов: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    async def _get_trade_offer(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Получить информацию о конкретном трейд оффере."""
        trade_offer_id = args.get("trade_offer_id")
        merge = args.get("merge", True)

        if not trade_offer_id:
            return {"status": "error", "message": "Не указан trade_offer_id"}

        loop = asyncio.get_event_loop()

        try:
            offer = await loop.run_in_executor(
                None,
                client.get_trade_offer,
                trade_offer_id,
                merge
            )
            return {
                "status": "success",
                "result": offer
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения трейд оффера: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    async def _get_wallet_balance(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Получить баланс кошелька."""
        convert_to_decimal = args.get("convert_to_decimal", True)
        loop = asyncio.get_event_loop()

        for attempt in range(1, 6):
            try:
                balance_response = await loop.run_in_executor(
                    None,
                    client.get_wallet_balance,
                    convert_to_decimal
                )
                return {
                    "status": "success",
                    "result": {
                        "balance": balance_response["balance"],
                        "wallet_currency": balance_response["wallet_currency"],
                        "delayed_balance": balance_response.get("delayed_balance", 0)
                    }
                }
            except Exception as e:
                if attempt < 5:
                    wait_time = attempt
                    self.logger.warning(f"Попытка {attempt} не удалась: {e}. Жду {wait_time}с...")
                    await asyncio.sleep(wait_time)
                else:
                    raise

        return {"status": "error", "message": "Не удалось получить баланс после 5 попыток"}

    async def _send_trade_offer(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Отправить трейд-оффер."""
        from steampy.models import Asset, GameOptions

        partner_id = args.get("partner_id")
        trade_offer_url = args.get("trade_offer_url")
        items_to_give = args.get("items_to_give", [])
        items_to_receive = args.get("items_to_receive", [])
        message = args.get("message", "")

        # Преобразуем items в Asset объекты
        assets_to_give = []
        for item in items_to_give:
            game = GameOptions(item.get("app_id", "730"), item.get("context_id", "2"))
            asset = Asset(item["asset_id"], game, item.get("amount", 1))
            assets_to_give.append(asset)

        assets_to_receive = []
        for item in items_to_receive:
            game = GameOptions(item.get("app_id", "730"), item.get("context_id", "2"))
            asset = Asset(item["asset_id"], game, item.get("amount", 1))
            assets_to_receive.append(asset)

        loop = asyncio.get_event_loop()

        try:
            if trade_offer_url:
                response = await loop.run_in_executor(
                    None,
                    client.make_offer_with_url,
                    assets_to_give,
                    assets_to_receive,
                    trade_offer_url,
                    message
                )
            elif partner_id:
                response = await loop.run_in_executor(
                    None,
                    client.make_offer,
                    assets_to_give,
                    assets_to_receive,
                    partner_id,
                    message
                )
            else:
                return {"status": "error", "message": "Не указан partner_id или trade_offer_url"}

            return {
                "status": "success",
                "result": {
                    "trade_offer_id": response.get("tradeofferid"),
                    "needs_mobile_confirmation": response.get("needs_mobile_confirmation", False)
                }
            }
        except Exception as e:
            self.logger.error(f"Ошибка отправки трейд-оффера: {e}", exc_info=True)
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
