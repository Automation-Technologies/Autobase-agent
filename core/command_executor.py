"""
Обработчик команд от сервера.
Выполняет команды через steampy.
"""
import asyncio
import logging
from typing import Dict, Any, Optional

from core.account_manager import AccountManager
from core.mafile_steam_guard import MafileSteamGuard
from core.proxy_manager import ProxyManager
from steampy.client import SteamClient


class _GameOptionsResolver:
    """
    Жёсткий резолвер GameOptions по app_id на стороне агента.
    Использует только предопределённые игры из steampy.models.GameOptions
    без любых дефолтов, алиасов и fallback-логики.
    """

    @staticmethod
    def resolve(app_id: str):
        from steampy.models import GameOptions as GO

        mapping = {
            GO.CS.app_id: GO.CS,
            GO.DOTA2.app_id: GO.DOTA2,
            GO.TF2.app_id: GO.TF2,
            GO.STEAM.app_id: GO.STEAM,
            GO.RUST.app_id: GO.RUST,
        }

        if app_id not in mapping:
            raise ValueError(f"Неподдерживаемый app_id: {app_id}")

        return mapping[app_id]


class CommandExecutor:
    """Выполняет команды от сервера через Steam API."""

    def __init__(
            self,
            mafiles_dict: Dict[str, dict],
            proxy_manager: ProxyManager,
            account_manager: AccountManager
    ):
        self._mafiles_dict = mafiles_dict
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
                "error": "Некорректная команда: отсутствует cmd или login",
                "request_id": request_id,
            }

        try:
            # Получаем или создаем Steam клиента (с логином)
            steam_client = await self._get_steam_client(login)

            if steam_client is None:
                return {
                    "status": "error",
                    "error": f"Не удалось создать Steam клиент для {login}",
                    "request_id": request_id,
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
                result = {
                    "status": "error",
                    "error": "make_offer_with_url отключён в агентском режиме"
                }
            elif cmd_type == "market_fetch_price":
                result = await self._market_fetch_price(steam_client, args)
            elif cmd_type == "market_create_buy_order":
                result = await self._market_create_buy_order(steam_client, args)
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
            elif cmd_type == "market_fetch_price_history":
                result = await self._market_fetch_price_history(steam_client, args)
            elif cmd_type == "market_buy_listing":
                result = await self._market_buy_listing(steam_client, args)
            elif cmd_type == "market_get_listings_by_name":
                result = await self._market_get_listings_by_name(steam_client, args)
            else:
                result = {"status": "error", "error": f"Неизвестная команда: {cmd_type}"}

            # Добавляем request_id в результат
            result["request_id"] = request_id

            return result

        except Exception as e:
            self.logger.error(f"Ошибка выполнения команды {cmd_type} для {login}: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
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
        api_key = self.account_manager.get_api_key(login)
        login_cookies = self.account_manager.get_login_cookies(login)

        if not password:
            self.logger.error(f"Для {login} не найден пароль в accounts.json.enc")
            return None

        if not api_key:
            self.logger.error(f"Для {login} не найден API key в accounts.json.enc")
            return None

        # Читаем maFile из памяти
        login_lower = login.lower()
        ma_data = self._mafiles_dict.get(login_lower) or self._mafiles_dict.get(login)
        if ma_data is None:
            self.logger.error(f"maFile для {login} не найден в памяти")
            return None

        try:
            steam_guard_data = MafileSteamGuard.build_dict(ma_data, login)
        except ValueError as e:
            self.logger.error(str(e))
            return None

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
        """Получить мой инвентарь. Контракт: app_id, context_id, merge, count, preserve_bbcode, raw_asset_properties (все обязательны)."""
        from steampy.models import GameOptions

        app_id = args.get("app_id")
        context_id = args.get("context_id")
        merge = args.get("merge")
        count = args.get("count")
        preserve_bbcode = args.get("preserve_bbcode")
        raw_asset_properties = args.get("raw_asset_properties")

        if not app_id or not context_id:
            return {"status": "error", "error": "Не указаны app_id или context_id"}
        if merge is None or count is None or preserve_bbcode is None or raw_asset_properties is None:
            return {"status": "error", "error": "Не указаны merge, count, preserve_bbcode или raw_asset_properties"}

        # Используем строго GameOptions из steampy.models без дефолтов и алиасов
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
                int(count),
                preserve_bbcode,
                raw_asset_properties,
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

        return {"status": "error", "error": "Не удалось получить инвентарь после 5 попыток"}

    async def _get_partner_inventory(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Получить инвентарь партнера. Контракт: partner_steam_id, app_id, context_id, merge, count (все обязательны)."""
        from steampy.models import GameOptions

        partner_steam_id = args.get("partner_steam_id")
        app_id = args.get("app_id")
        context_id = args.get("context_id")
        merge = args.get("merge")
        count = args.get("count")

        if not partner_steam_id:
            return {"status": "error", "error": "Не указан partner_steam_id"}
        if not app_id or not context_id:
            return {"status": "error", "error": "Не указаны app_id или context_id"}
        if merge is None or count is None:
            return {"status": "error", "error": "Не указаны merge или count"}

        # Используем строго GameOptions из steampy.models без дефолтов и алиасов
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
                    int(count),
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

        return {"status": "error", "error": "Не удалось получить инвентарь партнера после 5 попыток"}

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
                "error": str(e)
            }


    async def _get_wallet_balance(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Получить баланс кошелька. Контракт: convert_to_decimal обязателен."""
        if "convert_to_decimal" not in args:
            return {"status": "error", "error": "Не указан convert_to_decimal"}
        convert_to_decimal = args["convert_to_decimal"]
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

        return {"status": "error", "error": "Не удалось получить баланс после 5 попыток"}

    async def _market_fetch_price(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Получить цену предмета."""
        from steampy.models import Currency

        item_hash_name = args.get("item_hash_name")
        app_id = args.get("app_id")
        currency_value = args.get("currency")

        if not item_hash_name or not app_id or currency_value is None:
            return {"status": "error", "error": "Не указаны item_hash_name, app_id или currency"}

        # Жёстко резолвим GameOptions через единый резолвер без копипасты и дефолтов
        try:
            game = _GameOptionsResolver.resolve(app_id)
        except ValueError as e:
            return {"status": "error", "error": str(e)}

        # Определяем Currency
        try:
            currency = Currency(currency_value)
        except (ValueError, TypeError):
            return {"status": "error", "error": f"Неверное значение валюты: {currency_value}"}

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
                "error": str(e)
            }

    async def _market_create_buy_order(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Создать ордер на покупку через SteamMarket.create_buy_order."""
        from steampy.models import Currency

        market_name = args.get("market_name")
        price_single_item = args.get("price_single_item")
        quantity = args.get("quantity")
        app_id = args.get("app_id")
        currency_value = args.get("currency")

        if not market_name or price_single_item is None or quantity is None or not app_id or currency_value is None:
            return {
                "status": "error",
                "error": "Не указаны market_name, price_single_item, quantity, app_id или currency"
            }

        # Жёстко резолвим GameOptions через единый резолвер без копипасты и дефолтов
        try:
            game = _GameOptionsResolver.resolve(app_id)
        except ValueError as e:
            return {"status": "error", "error": str(e)}

        # Определяем Currency
        try:
            currency = Currency(currency_value)
        except (ValueError, TypeError):
            return {"status": "error", "error": f"Неверное значение валюты: {currency_value}"}

        loop = asyncio.get_event_loop()

        try:
            result = await loop.run_in_executor(
                None,
                client.market.create_buy_order,
                market_name,
                price_single_item,
                int(quantity),
                game,
                currency
            )
            return {
                "status": "success",
                "result": result
            }
        except Exception as e:
            self.logger.error(f"Ошибка создания ордера на покупку: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e)
            }

    async def _market_create_sell_order(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Создать ордер на продажу. app_id и context_id берутся из args (1-в-1 с steam_bot)."""
        from steampy.models import GameOptions

        assetid = args.get("assetid")
        app_id = args.get("app_id")
        context_id = args.get("context_id")
        money_to_receive = args.get("money_to_receive")

        if not assetid or not app_id or context_id is None or not money_to_receive:
            return {"status": "error", "error": "Не указаны assetid, app_id, context_id или money_to_receive"}

        game = GameOptions(app_id, context_id)

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
                "error": str(e)
            }

    async def _market_cancel_sell_order(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Отменить ордер на продажу."""
        sell_listing_id = args.get("sell_listing_id")

        if not sell_listing_id:
            return {"status": "error", "error": "Не указан sell_listing_id"}

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
                "error": str(e)
            }

    async def _market_cancel_buy_order(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Отменить ордер на покупку."""
        buy_order_id = args.get("buy_order_id")

        if not buy_order_id:
            return {"status": "error", "error": "Не указан buy_order_id"}

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
                "error": str(e)
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
                "error": str(e)
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
                "error": str(e)
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
                "error": str(e)
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
                "error": str(e)
            }
    
    async def _market_get_history(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Получить историю покупок/продаж на Steam Market на стороне агента."""
        from steampy.models import SteamUrl
        from steampy.exceptions import ApiException

        if "start" not in args or "count" not in args:
            return {"status": "error", "error": "Не указаны start или count"}

        start = int(args["start"])
        count = int(args["count"])

        loop = asyncio.get_event_loop()

        def _request_history() -> Dict[str, Any]:
            url = "/".join([SteamUrl.COMMUNITY_URL, "market", "myhistory", "render"])
            params = {
                "query": "",
                "start": start,
                "count": count,
            }

            response = client._session.get(url, params=params)  # type: ignore[attr-defined]
            response.encoding = "utf-8-sig"

            if response.status_code != 200:
                raise ApiException(
                    f"get_market_history failed. HTTP code: {response.status_code}"
                )

            data = response.json()
            if not data.get("success"):
                raise ApiException("get_market_history: Steam API returned success=false")

            return data

        try:
            result = await loop.run_in_executor(None, _request_history)
            return {
                "status": "success",
                "result": result,
            }
        except Exception as e:
            self.logger.error(f"Ошибка получения истории маркета: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
            }

    async def _market_fetch_price_history(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Получить историю цен предмета (market/pricehistory)."""
        item_hash_name = args.get("item_hash_name")
        app_id = args.get("app_id")

        if not item_hash_name or not app_id:
            return {"status": "error", "error": "Не указаны item_hash_name или app_id"}

        try:
            game = _GameOptionsResolver.resolve(app_id)
        except ValueError as e:
            return {"status": "error", "error": str(e)}

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                client.market.fetch_price_history,
                item_hash_name,
                game
            )
            return {"status": "success", "result": result}
        except Exception as e:
            self.logger.error(f"Ошибка получения истории цен: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    async def _market_buy_listing(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Покупка конкретного листинга с поддержкой мобильного подтверждения на стороне агента."""
        import time
        import urllib.parse
        from steampy.exceptions import ApiException
        from steampy.models import SteamUrl
        from steampy.confirmation import ConfirmationExecutor

        market_name = args.get("market_name")
        market_id = args.get("market_id")
        price = args.get("price")
        fee = args.get("fee")
        app_id = args.get("app_id")
        currency_value = args.get("currency")

        if not all([market_name, market_id, price is not None, fee is not None, app_id, currency_value is not None]):
            return {"status": "error", "error": "Не хватает обязательных параметров: market_name, market_id, price, fee, app_id, currency"}

        loop = asyncio.get_event_loop()

        def _do_buy():
            session_id = client._get_session_id()
            data = {
                'sessionid': session_id,
                'currency': currency_value,
                'subtotal': price - fee,
                'fee': fee,
                'total': price,
                'quantity': '1',
                'confirmation': '0'
            }
            headers = {
                'Referer': f'{SteamUrl.COMMUNITY_URL}/market/listings/{app_id}/{urllib.parse.quote(market_name)}',
            }
            url = f'{SteamUrl.COMMUNITY_URL}/market/buylisting/{market_id}'

            resp = client._session.post(url, data=data, headers=headers)
            time.sleep(5.4)
            response = resp.json()

            if response.get("need_confirmation") or response.get("success") == 22:
                steam_guard_data = client.steam_guard
                if not steam_guard_data:
                    raise ApiException("Требуется мобильное подтверждение, но данные steam_guard отсутствуют")

                if isinstance(steam_guard_data, str):
                    import json as _json
                    steam_guard_data = _json.loads(steam_guard_data)

                confirmation_id = response["confirmation"]["confirmation_id"]
                confirmation_executor = ConfirmationExecutor(
                    steam_guard_data['identity_secret'],
                    steam_guard_data['steamid'],
                    client._session
                )
                time.sleep(5.4)
                if not confirmation_executor.confirm_by_id(confirmation_id):
                    raise ApiException("Не удалось подтвердить действие через Steam Guard")

                data["confirmation"] = confirmation_id
                time.sleep(5.4)
                second_resp = client._session.post(url, data=data, headers=headers)
                second_response = second_resp.json()

                if second_response.get("wallet_info", {}).get("success") == 1:
                    return second_response
                else:
                    raise ApiException(f"Buy_item failed after confirmation: {second_response}")

            return response

        try:
            result = await loop.run_in_executor(None, _do_buy)
            return {"status": "success", "result": result}
        except Exception as e:
            self.logger.error(f"Ошибка покупки листинга: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    async def _market_get_listings_by_name(self, client: SteamClient, args: Dict[str, Any]) -> Dict[str, Any]:
        """Получить сырые данные листингов по имени предмета для MarketIdResolver."""
        import urllib.parse

        market_name = args.get("market_name")
        app_id = args.get("app_id")
        currency_value = args.get("currency")

        if not market_name or not app_id or currency_value is None:
            return {"status": "error", "error": "Не указаны market_name, app_id или currency"}

        loop = asyncio.get_event_loop()

        def _do_get():
            encoded_skin = urllib.parse.quote(market_name, safe='')
            url = f"https://steamcommunity.com/market/listings/{app_id}/{encoded_skin}/render/"
            params = {'query': '', 'start': 0, 'count': 10, 'currency': currency_value}
            resp = client._session.get(url, params=params)
            return resp.json()

        try:
            result = await loop.run_in_executor(None, _do_get)
            return {"status": "success", "result": result}
        except Exception as e:
            self.logger.error(f"Ошибка получения листингов: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    def cleanup(self) -> None:
        """Закрыть все соединения."""
        for login, client in self.steam_clients.items():
            try:
                client.logout()
                self.logger.info(f"Logout для {login}")
            except:
                pass
        self.steam_clients.clear()
