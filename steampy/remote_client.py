"""
RemoteSteamClient - Класс для удаленного управления Steam клиентом через WebSocket Gateway

Этот класс имитирует интерфейс SteamClient, но вместо прямого доступа к Steam API
отправляет команды через Redis в AgentGateway, который пересылает их в WebSocket клиент на ПК пользователя.
"""

import json
import logging
import os
import threading
import uuid
from decimal import Decimal
from typing import Any, Optional, Dict

import redis

from steampy.models import GameOptions, Currency

logger = logging.getLogger(__name__)


class RemoteSteamClientException(Exception):
    """Исключение для ошибок RemoteSteamClient"""
    pass


class RemoteSteamClientTimeoutException(RemoteSteamClientException):
    """Исключение для таймаутов при ожидании ответа от агента"""
    pass


class DecimalEncoder(json.JSONEncoder):
    """JSON энкодер с поддержкой Decimal"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super(DecimalEncoder, self).default(obj)


class RemoteMarket:
    """
    Эмуляция объекта market для RemoteSteamClient
    Позволяет вызывать методы как client.market.fetch_price()
    """
    
    def __init__(self, remote_client: 'RemoteSteamClient'):
        self._client = remote_client
    
    def fetch_price(self, item_hash_name: str, game: GameOptions, currency: Currency) -> dict:
        """
        Получить цену предмета
        
        Args:
            item_hash_name: Hash название предмета
            game: Опции игры
            currency: Валюта
            
        Returns:
            Словарь с информацией о цене
        """
        return self._client._send_command_and_wait(
            "market_fetch_price",
            item_hash_name=item_hash_name,
            app_id=game.app_id,
            currency=currency.value
        )
    
    def create_sell_order(self, assetid: str, game: GameOptions, money_to_receive: str) -> dict:
        """
        Создать ордер на продажу
        
        Args:
            assetid: ID предмета
            game: Опции игры
            money_to_receive: Сумма к получению
            
        Returns:
            Результат создания ордера
        """
        return self._client._send_command_and_wait(
            "market_create_sell_order",
            assetid=assetid,
            app_id=game.app_id,
            context_id=game.context_id,
            money_to_receive=money_to_receive
        )
    
    def cancel_sell_order(self, sell_listing_id: str) -> None:
        """
        Отменить ордер на продажу
        
        Args:
            sell_listing_id: ID листинга на продажу
        """
        self._client._send_command_and_wait("market_cancel_sell_order", sell_listing_id=sell_listing_id)
    
    def cancel_buy_order(self, buy_order_id: str) -> dict:
        """
        Отменить ордер на покупку
        
        Args:
            buy_order_id: ID ордера на покупку
            
        Returns:
            Результат отмены
        """
        return self._client._send_command_and_wait("market_cancel_buy_order", buy_order_id=buy_order_id)
    
    def get_my_buy_orders(self) -> dict:
        """
        Получить мои ордера на покупку
        
        Returns:
            Словарь с ордерами на покупку
        """
        return self._client._send_command_and_wait("market_get_my_buy_orders")
    
    def get_my_sell_listings(self) -> dict:
        """
        Получить мои листинги на продажу
        
        Returns:
            Словарь с листингами
        """
        return self._client._send_command_and_wait("market_get_my_sell_listings")
    
    def get_my_recent_sell_listings(self) -> dict:
        """
        Получить последние 10 листингов на продажу
        
        Returns:
            Словарь с листингами
        """
        return self._client._send_command_and_wait("market_get_my_recent_sell_listings")
    
    def get_my_market_listings(self) -> dict:
        """
        Получить все мои листинги на маркете (buy + sell)
        
        Returns:
            Словарь со всеми листингами
        """
        return self._client._send_command_and_wait("market_get_my_market_listings")
    
    def get_market_history(self, start: int = 0, count: int = 100) -> dict:
        """
        Получить историю покупок/продаж на Steam Market
        
        Args:
            start: Начальная позиция (по умолчанию 0)
            count: Количество записей для получения (по умолчанию 100)
        
        Returns:
            Словарь с сырыми данными истории от Steam API
        """
        return self._client._send_command_and_wait("market_get_history", start=start, count=count)


class RedisManager:
    """
    Профессиональный менеджер соединений Redis.
    Реализует паттерн Singleton с учетом PID процесса.
    
    Гарантирует, что для каждого процесса (PID) существует ровно один ConnectionPool.
    При fork (создании дочернего процесса) автоматически создается новый пул.
    
    Потокобезопасен: использует threading.Lock для синхронизации создания пулов.
    """
    _instances: Dict[int, redis.ConnectionPool] = {}
    _lock = threading.Lock()

    @classmethod
    def get_pool(cls, host: str, port: int, db: int, socket_timeout: int = 120) -> redis.ConnectionPool:
        """
        Возвращает пул соединений для текущего процесса.
        Если пула нет или сменился PID (после fork) — создает новый.
        
        Args:
            host: Хост Redis сервера
            port: Порт Redis сервера
            db: Номер базы данных Redis
            socket_timeout: Таймаут сокета в секундах (по умолчанию 120 для поддержки длительных blpop)
            
        Returns:
            ConnectionPool для текущего процесса
        """
        current_pid = os.getpid()
        
        # Быстрая проверка без блокировки (для производительности)
        if current_pid in cls._instances:
            return cls._instances[current_pid]

        with cls._lock:
            # Двойная проверка внутри блокировки (Thread-safe Singleton)
            if current_pid not in cls._instances:
                logger.debug(f"🔧 [PID={current_pid}] Инициализация нового Redis ConnectionPool (socket_timeout={socket_timeout}s)")
                
                # Очистка старых пулов от родительских процессов
                # (в дочернем процессе словарь скопирован, но старые пулы невалидны)
                old_pids = list(cls._instances.keys())
                if old_pids:
                    logger.debug(f"🧹 [PID={current_pid}] Очистка пулов старых процессов: {old_pids}")
                    cls._instances.clear()
                
                pool = redis.ConnectionPool(
                    host=host,
                    port=port,
                    db=db,
                    decode_responses=True,
                    socket_timeout=socket_timeout,
                    socket_connect_timeout=5,
                    max_connections=10
                )
                cls._instances[current_pid] = pool
            
            return cls._instances[current_pid]


class RemoteSteamClient:
    """
    Удаленный Steam клиент для Trustless режима
    
    Отправляет команды через Redis -> AgentGateway -> WebSocket -> User PC Agent
    Использует RedisManager для эффективного управления соединениями в multiprocessing окружении.
    """
    
    def __init__(
        self,
        agent_token: str,
        login: str,
        redis_host: str,
        redis_port: int,
        redis_db: int,
        command_timeout: int
    ):
        """
        Инициализация удаленного Steam клиента
        
        Args:
            agent_token: Токен агента для маршрутизации команд
            login: Логин Steam аккаунта
            redis_host: Хост Redis сервера
            redis_port: Порт Redis сервера
            redis_db: Номер базы данных Redis
            command_timeout: Таймаут ожидания ответа от агента (секунды)
        """
        self.agent_token = agent_token
        self.login = login
        self.username = login  # Для совместимости с интерфейсом SteamClient
        self.command_timeout = command_timeout
        
        # Получаем пул через RedisManager (профессиональный паттерн Singleton с PID-awareness)
        # Устанавливаем socket_timeout больше command_timeout + запас для блокирующих операций blpop
        socket_timeout = max(command_timeout + 10, 120)
        pool = RedisManager.get_pool(redis_host, redis_port, redis_db, socket_timeout=socket_timeout)
        
        # Создаем легковесный клиент, используя готовый пул соединений
        # Redis клиент сам по себе легковесный, тяжелый только ConnectionPool
        self.redis_client = redis.Redis(connection_pool=pool)
        
        # Эмуляция атрибутов оригинального SteamClient
        self.was_login_executed = True  # В Trustless режиме логин делает сам агент
        self.market = RemoteMarket(self)  # Эмуляция объекта market
        # steam_guard нужен для совместимости с InventoryDataScrapper
        # В Trustless режиме steamid получается через агента при первом запросе
        self.steam_guard = None  # Будет установлен при первом использовании через агента
    
    def _send_command_and_wait(self, action: str, **kwargs) -> Any:
        """
        Отправка команды агенту и ожидание ответа
        
        Args:
            action: Название команды (соответствует методу SteamClient)
            **kwargs: Аргументы команды
            
        Returns:
            Результат выполнения команды
            
        Raises:
            RemoteSteamClientTimeoutException: Если агент не ответил в течение таймаута
            RemoteSteamClientException: Если агент вернул ошибку
        """
        request_id = str(uuid.uuid4())
        
        payload = {
            "target_token": self.agent_token,
            "request_id": request_id,
            "cmd": action,
            "account_login": self.login,
            "args": kwargs
        }
        
        # Отправляем команду в канал для AgentGateway (с поддержкой Decimal через DecimalEncoder)
        self.redis_client.publish("to_agent_gateway", json.dumps(payload, cls=DecimalEncoder))
        
        # Блокирующее ожидание ответа из списка response:{request_id}
        response_data = self.redis_client.blpop(
            f"response:{request_id}",
            timeout=self.command_timeout
        )
        
        if not response_data:
            logger.error(
                f"❌ Agent не ответил в течение {self.command_timeout} секунд для команды '{action}' "
                f"(login={self.login}, token={self.agent_token[:8]}...). "
                f"Завершаем процесс бота."
            )
            os._exit(1)
        
        # response_data это tuple: (key, value)
        result = json.loads(response_data[1])
        
        if result.get("status") == "error":
            error_message = result.get("error", "Unknown error")
            
            # Если агент недоступен - завершаем процесс
            if "Agent is offline" in error_message or "Failed to send command" in error_message:
                logger.error(
                    f"❌ Agent недоступен для команды '{action}' (login={self.login}): {error_message}. "
                    f"Завершаем процесс бота."
                )
                os._exit(1)
            
            raise RemoteSteamClientException(f"Agent error for command '{action}': {error_message}")
        
        return result.get("result")
    
    # ===== Эмуляция методов SteamClient =====
    
    def login(self, username: str, password: str, steam_guard: dict) -> None:
        """
        Логин не требуется в Trustless режиме
        Агент на ПК пользователя сам управляет авторизацией
        """
        pass
    
    def logout(self) -> None:
        """Выход не требуется в Trustless режиме"""
        pass
    
    def is_session_alive(self) -> bool:
        """
        Проверка жизни сессии через агента
        
        Returns:
            True если агент онлайн и сессия активна
        """
        return self._send_command_and_wait("is_session_alive")
    
    # ===== Совместимость с интерфейсом SteamClient =====
    
    def _get_session_id(self) -> str:
        """
        Получить текущий sessionid из сессии Steam на агенте.
        
        Нужен для модулей вроде Ординатора, которые ожидают у клиента приватный
        метод `_get_session_id`, как у обычного SteamClient.
        """
        result = self._send_command_and_wait("get_session_id")
        if not isinstance(result, str):
            raise RemoteSteamClientException(f"Invalid session_id from agent: {result!r}")
        return result
    
    def make_offer_with_url(
        self,
        items_from_me: list,
        items_from_them: list,
        trade_offer_url: str,
        message: str = ""
    ) -> dict:
        """
        Создать трейд оффер по URL
        
        Args:
            items_from_me: Список предметов от меня (список Asset или словарей)
            items_from_them: Список предметов от партнера (список Asset или словарей)
            trade_offer_url: URL трейд оффера
            message: Сообщение к офферу
            
        Returns:
            Результат создания оффера
        """
        # Преобразуем Asset объекты в словари, если нужно
        items_from_me_dict = []
        for item in items_from_me:
            if hasattr(item, 'to_dict'):
                items_from_me_dict.append(item.to_dict())
            elif isinstance(item, dict):
                items_from_me_dict.append(item)
            else:
                items_from_me_dict.append({
                    'assetid': str(item.assetid) if hasattr(item, 'assetid') else str(item),
                    'appid': item.game.app_id if hasattr(item, 'game') else None,
                    'contextid': item.game.context_id if hasattr(item, 'game') else None,
                    'amount': item.amount if hasattr(item, 'amount') else 1
                })
        
        items_from_them_dict = []
        for item in items_from_them:
            if hasattr(item, 'to_dict'):
                items_from_them_dict.append(item.to_dict())
            elif isinstance(item, dict):
                items_from_them_dict.append(item)
            else:
                items_from_them_dict.append({
                    'assetid': str(item.assetid) if hasattr(item, 'assetid') else str(item),
                    'appid': item.game.app_id if hasattr(item, 'game') else None,
                    'contextid': item.game.context_id if hasattr(item, 'game') else None,
                    'amount': item.amount if hasattr(item, 'amount') else 1
                })
        
        return self._send_command_and_wait(
            "make_offer_with_url",
            items_from_me=items_from_me_dict,
            items_from_them=items_from_them_dict,
            trade_offer_url=trade_offer_url,
            message=message
        )
    
    def get_my_inventory(self, game: GameOptions, merge: bool = True, count: int = 5000,
                         preserve_bbcode: bool = False, raw_asset_properties: bool = False) -> dict:
        """
        Получить мой инвентарь
        
        Args:
            game: Опции игры (app_id, context_id)
            merge: Объединять ли предметы с описаниями
            count: Количество предметов для загрузки
            preserve_bbcode: Сохранять ли BBCode в описаниях
            raw_asset_properties: Получать ли сырые свойства ассетов
            
        Returns:
            Словарь с инвентарем
        """
        return self._send_command_and_wait(
            "get_my_inventory",
            app_id=game.app_id,
            context_id=game.context_id,
            merge=merge,
            count=count,
            preserve_bbcode=preserve_bbcode,
            raw_asset_properties=raw_asset_properties
        )
    
    def get_partner_inventory(
        self,
        partner_steam_id: str,
        game: GameOptions,
        merge: bool = True,
        count: int = 5000
    ) -> dict:
        """
        Получить инвентарь партнера
        
        Args:
            partner_steam_id: Steam ID партнера
            game: Опции игры
            merge: Объединять ли предметы с описаниями
            count: Количество предметов
            
        Returns:
            Словарь с инвентарем партнера
        """
        return self._send_command_and_wait(
            "get_partner_inventory",
            partner_steam_id=partner_steam_id,
            app_id=game.app_id,
            context_id=game.context_id,
            merge=merge,
            count=count
        )
    
    def get_wallet_balance(self, convert_to_decimal: bool = True, timeout: int = 15) -> dict:
        """
        Получить баланс кошелька Steam
        
        Args:
            convert_to_decimal: Конвертировать баланс в десятичное число (делить на 100)
            timeout: Таймаут запроса (не используется в RemoteSteamClient, оставлен для совместимости)
        
        Returns:
            Словарь с балансом:
            {
                "balance": float - баланс кошелька,
                "wallet_currency": int - валюта кошелька,
                "delayed_balance": float - отложенный баланс
            }
        """
        return self._send_command_and_wait("get_wallet_balance", convert_to_decimal=convert_to_decimal)

    # ===== Market методы (1-в-1 с агентом) =====

    def market_create_buy_order(
        self,
        market_name: str,
        price_single_item: str,
        quantity: int,
        game: GameOptions,
        currency: int
    ) -> dict:
        """
        Создать ордер на покупку на маркете
        
        Args:
            market_name: Название предмета
            price_single_item: Цена за единицу (в минимальных единицах валюты, например, центы)
            quantity: Количество
            game: Опции игры
            currency: Валюта (целое значение Enum Currency)
            
        Returns:
            Результат создания ордера
        """
        return self._send_command_and_wait(
            "market_create_buy_order",
            market_name=market_name,
            price_single_item=price_single_item,
            quantity=quantity,
            app_id=game.app_id,
            currency=currency
        )

    def market_cancel_buy_order(self, buy_order_id: str) -> dict:
        """
        Отменить ордер на покупку
        
        Args:
            buy_order_id: ID ордера на покупку
            
        Returns:
            Результат отмены
        """
        return self._send_command_and_wait("market_cancel_buy_order", buy_order_id=buy_order_id)

    def market_create_sell_order(
        self,
        assetid: str,
        game: GameOptions,
        money_to_receive: str
    ) -> dict:
        """
        Создать ордер на продажу
        
        Args:
            assetid: ID предмета
            game: Опции игры
            money_to_receive: Сумма к получению
            
        Returns:
            Результат создания ордера
        """
        return self._send_command_and_wait(
            "market_create_sell_order",
            assetid=assetid,
            app_id=game.app_id,
            context_id=game.context_id,
            money_to_receive=money_to_receive
        )

    def market_cancel_sell_order(self, sell_listing_id: str) -> None:
        """
        Отменить ордер на продажу
        
        Args:
            sell_listing_id: ID листинга на продажу
        """
        self._send_command_and_wait("market_cancel_sell_order", sell_listing_id=sell_listing_id)

    def market_get_my_buy_orders(self) -> dict:
        """
        Получить мои ордера на покупку
        
        Returns:
            Словарь с ордерами на покупку
        """
        return self._send_command_and_wait("market_get_my_buy_orders")

    def market_get_my_sell_listings(self) -> dict:
        """
        Получить мои листинги на продажу
        
        Returns:
            Словарь с листингами
        """
        return self._send_command_and_wait("market_get_my_sell_listings")

    def market_get_my_market_listings(self) -> dict:
        """
        Получить все мои листинги на маркете
        
        Returns:
            Словарь со всеми листингами
        """
        return self._send_command_and_wait("market_get_my_market_listings")

    def market_fetch_price(
        self,
        item_hash_name: str,
        game: GameOptions,
        currency: int
    ) -> dict:
        """
        Получить цену предмета
        
        Args:
            item_hash_name: Hash название предмета
            game: Опции игры
            currency: Валюта
            
        Returns:
            Словарь с информацией о цене
        """
        return self._send_command_and_wait(
            "market_fetch_price",
            item_hash_name=item_hash_name,
            app_id=game.app_id,
            currency=currency
        )

    def market_fetch_price_history(
        self,
        item_hash_name: str,
        game: GameOptions
    ) -> dict:
        """
        Получить историю цен предмета
        
        Args:
            item_hash_name: Hash название предмета
            game: Опции игры
            
        Returns:
            Словарь с историей цен
        """
        return self._send_command_and_wait(
            "market_fetch_price_history",
            item_hash_name=item_hash_name,
            app_id=game.app_id
        )

