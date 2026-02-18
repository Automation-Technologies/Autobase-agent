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
        login = command.get("account_login")
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
            elif cmd_type == "is_session_alive":
                result = await self._is_session_alive(steam_client)
            elif cmd_type == "make_offer_with_url":
                result = await self._make_offer_with_url(steam_client, args)
            elif cmd_type == "market_fetch_price":
                result = await self._market_fetch_price(steam_client, args)
            elif cmd_type == "market_create_sell_order":
                result = await self._market_create_sell_order(steam_client, args)
            elif cmd_type == "market_cancel_sell_order":
                result = await self._market_cancel_sell_order(steam_client, args)
            elif cmd_type == "market_cancel_buy_order":
                result = await self._market_cancel_buy_order(steam_client, args)
            elif cmd_type == "market_get_my_buy_orders":
                result = await self._market_get_my_buy_orders(steam_client)
            elif cmd_type == "market_get_my_sell_listings":
                result = await self._market_get_my_sell_listings(steam_client)
            elif cmd_type == "market_get_my_recent_sell_listings":
                result = await self._market_get_my_recent_sell_listings(steam_client)
            elif cmd_type == "market_get_my_market_listings":
                result = await self._market_get_my_market_listings(steam_client)
            elif cmd_type == "market_get_history":
                result = await self._market_get_history(steam_client, args)
            elif cmd_type == "get_session_id":
                result = await self._get_session_id(steam_client)
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
        login_cookies = self.account_manager.get_login_cookies(login)

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

        loop = asyncio.get_event_loop()

        # Если есть сохранённые куки, сначала пробуем поднять сессию на них без повторного логина
        if login_cookies is not None:
            try:
                self.logger.info(f"Пробую восстановить сессию по сохранённым кукам для {login}")
                client_from_cookies = SteamClient(
                    api_key,
                    username=login,
                    password=password,
                    steam_guard=steam_guard_data,
                    login_cookies=login_cookies,
                    proxies=client_proxies,
                )
                is_alive = await loop.run_in_executor(None, client_from_cookies.is_session_alive)
                if is_alive:
                    self.steam_clients[login] = client_from_cookies
                    self.logger.info(f"✅ Использую сохранённую сессию Steam для {login} (без повторного логина)")
                    return client_from_cookies
                self.logger.warning(f"Сохранённая сессия для {login} неактивна, выполняю полный логин")
            except Exception as e:
                self.logger.warning(f"Не удалось восстановить сессию по кукам для {login}: {e}, выполняю полный логин")

        # Создаем клиента для полноценного логина
        client = SteamClient(api_key, proxies=client_proxies)

        # Логинимся (синхронно, но в executor)
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

            # Сохраняем куки после успешного логина
            try:
                cookies_dict = client._session.cookies.get_dict()
                self.account_manager.set_login_cookies(login, cookies_dict)
                self.logger.info(f"Сохранены login_cookies для {login} ({len(cookies_dict)} куков)")
            except Exception as e:
                self.logger.warning(f"Не удалось сохранить login_cookies для {login}: {e}")

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
        preserve_bbcode = args.get("preserve_bbcode", False)
        raw_asset_properties = args.get("raw_asset_properties", False)

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
                    merge,
                    count,
                    preserve_bbcode,
                    raw_asset_properties
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

    async def _make_offer_with_url(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Создать трейд-оффер по URL."""
        from steampy.models import Asset, GameOptions

        trade_offer_url = args.get("trade_offer_url")
        items_from_me = args.get("items_from_me", [])
        items_from_them = args.get("items_from_them", [])
        message = args.get("message", "")

        if not trade_offer_url:
            return {"status": "error", "message": "Не указан trade_offer_url"}

        # Преобразуем словари в Asset объекты
        assets_from_me = []
        for item in items_from_me:
            if isinstance(item, dict):
                app_id = item.get("appid") or item.get("app_id", "730")
                context_id = item.get("contextid") or item.get("context_id", "2")
                game = GameOptions(app_id, context_id)
                asset_id = item.get("assetid") or item.get("asset_id")
                amount = item.get("amount", 1)
                asset = Asset(asset_id, game, amount)
                assets_from_me.append(asset)

        assets_from_them = []
        for item in items_from_them:
            if isinstance(item, dict):
                app_id = item.get("appid") or item.get("app_id", "730")
                context_id = item.get("contextid") or item.get("context_id", "2")
                game = GameOptions(app_id, context_id)
                asset_id = item.get("assetid") or item.get("asset_id")
                amount = item.get("amount", 1)
                asset = Asset(asset_id, game, amount)
                assets_from_them.append(asset)

        loop = asyncio.get_event_loop()

        try:
            response = await loop.run_in_executor(
                None,
                client.make_offer_with_url,
                assets_from_me,
                assets_from_them,
                trade_offer_url,
                message
            )
            return {
                "status": "success",
                "result": response
            }
        except Exception as e:
            self.logger.error(f"Ошибка создания трейд-оффера: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    async def _market_fetch_price(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Получить цену предмета."""
        from steampy.models import GameOptions, Currency

        item_hash_name = args.get("item_hash_name")
        app_id = args.get("app_id")
        currency_value = args.get("currency")

        if not item_hash_name or not app_id or currency_value is None:
            return {"status": "error", "message": "Не указаны item_hash_name, app_id или currency"}

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
            game = GameOptions(app_id, "2")

        # Определяем Currency
        try:
            currency = Currency(currency_value)
        except (ValueError, TypeError):
            return {"status": "error", "message": f"Неверное значение валюты: {currency_value}"}

        loop = asyncio.get_event_loop()

        try:
            price_data = await loop.run_in_executor(
                None,
                client.market.fetch_price,
                item_hash_name,
                game,
                currency
            )
            return {
                "status": "success",
                "result": price_data
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения цены: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    async def _market_create_sell_order(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Создать ордер на продажу."""
        from steampy.models import GameOptions

        assetid = args.get("assetid")
        app_id = args.get("app_id")
        context_id = args.get("context_id")
        money_to_receive = args.get("money_to_receive")

        if not assetid or not app_id or not money_to_receive:
            return {"status": "error", "message": "Не указаны assetid, app_id или money_to_receive"}

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
            game = GameOptions(app_id, context_id or "2")

        loop = asyncio.get_event_loop()

        try:
            result = await loop.run_in_executor(
                None,
                client.market.create_sell_order,
                assetid,
                game,
                money_to_receive
            )
            return {
                "status": "success",
                "result": result
            }
        except Exception as e:
            self.logger.error(f"Ошибка создания ордера на продажу: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    async def _market_cancel_sell_order(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Отменить ордер на продажу."""
        sell_listing_id = args.get("sell_listing_id")

        if not sell_listing_id:
            return {"status": "error", "message": "Не указан sell_listing_id"}

        loop = asyncio.get_event_loop()

        try:
            await loop.run_in_executor(
                None,
                client.market.cancel_sell_order,
                sell_listing_id
            )
            return {
                "status": "success",
                "result": None
            }
        except Exception as e:
            self.logger.error(f"Ошибка отмены ордера на продажу: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    async def _market_cancel_buy_order(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Отменить ордер на покупку."""
        buy_order_id = args.get("buy_order_id")

        if not buy_order_id:
            return {"status": "error", "message": "Не указан buy_order_id"}

        loop = asyncio.get_event_loop()

        try:
            result = await loop.run_in_executor(
                None,
                client.market.cancel_buy_order,
                buy_order_id
            )
            return {
                "status": "success",
                "result": result
            }
        except Exception as e:
            self.logger.error(f"Ошибка отмены ордера на покупку: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    async def _market_get_my_buy_orders(self, client: SteamClient) -> Dict[str, Any]:
        """Получить мои ордера на покупку."""
        loop = asyncio.get_event_loop()

        try:
            buy_orders = await loop.run_in_executor(
                None,
                client.market.get_my_buy_orders
            )
            return {
                "status": "success",
                "result": buy_orders
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения ордеров на покупку: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    async def _market_get_my_sell_listings(self, client: SteamClient) -> Dict[str, Any]:
        """Получить мои листинги на продажу."""
        loop = asyncio.get_event_loop()

        try:
            sell_listings = await loop.run_in_executor(
                None,
                client.market.get_my_sell_listings
            )
            return {
                "status": "success",
                "result": sell_listings
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения листингов на продажу: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    async def _market_get_my_recent_sell_listings(self, client: SteamClient) -> Dict[str, Any]:
        """Получить последние 10 листингов на продажу."""
        loop = asyncio.get_event_loop()

        try:
            sell_listings = await loop.run_in_executor(
                None,
                client.market.get_my_recent_sell_listings
            )
            return {
                "status": "success",
                "result": sell_listings
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения последних листингов: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    async def _market_get_my_market_listings(self, client: SteamClient) -> Dict[str, Any]:
        """Получить все мои листинги на маркете (buy + sell)."""
        loop = asyncio.get_event_loop()

        try:
            listings = await loop.run_in_executor(
                None,
                client.market.get_my_market_listings
            )
            return {
                "status": "success",
                "result": listings
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения всех листингов: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }
    
    async def _market_get_history(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Получить историю покупок/продаж на Steam Market."""
        start = args.get("start", 0)
        count = args.get("count", 100)
        
        loop = asyncio.get_event_loop()
        
        try:
            result = await loop.run_in_executor(
                None,
                client.market.get_market_history,
                start,
                count
            )
            
            return {
                "status": "success",
                "result": result
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения истории маркета: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    async def _get_session_id(self, client: SteamClient) -> Dict[str, Any]:
        """Вернуть sessionid, как это делает SteamClient._get_session_id()."""
        loop = asyncio.get_event_loop()

        try:
            session_id = await loop.run_in_executor(
                None,
                client._get_session_id  # type: ignore[attr-defined]
            )
            return {
                "status": "success",
                "result": session_id
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения session_id: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    def cleanup(self) -> None:
        """Закрыть все соединения."""
        for login, client in self.steam_clients.items():
            try:
                client.logout()
                self.logger.info(f"Logout для {login}")
            except:
                pass
        self.steam_clients.clear()
