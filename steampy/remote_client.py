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

from steampy.models import GameOptions

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
    def get_pool(cls, host: str, port: int, db: int) -> redis.ConnectionPool:
        """
        Возвращает пул соединений для текущего процесса.
        Если пула нет или сменился PID (после fork) — создает новый.
        
        Args:
            host: Хост Redis сервера
            port: Порт Redis сервера
            db: Номер базы данных Redis
            
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
                logger.debug(f"🔧 [PID={current_pid}] Инициализация нового Redis ConnectionPool")
                
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
                    socket_timeout=5,
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
        self.command_timeout = command_timeout
        
        # Получаем пул через RedisManager (профессиональный паттерн Singleton с PID-awareness)
        pool = RedisManager.get_pool(redis_host, redis_port, redis_db)
        
        # Создаем легковесный клиент, используя готовый пул соединений
        # Redis клиент сам по себе легковесный, тяжелый только ConnectionPool
        self.redis_client = redis.Redis(connection_pool=pool)
        
        # Эмуляция атрибутов оригинального SteamClient
        self.was_login_executed = True  # В Trustless режиме логин делает сам агент
    
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
    
    def get_trade_offers(self, merge: bool = True) -> dict:
        """
        Получить список трейд офферов
        
        Args:
            merge: Объединять ли предметы с описаниями
            
        Returns:
            Словарь с трейд офферами
        """
        return self._send_command_and_wait("get_trade_offers", merge=merge)
    
    def get_trade_offer(self, trade_offer_id: str, merge: bool = True) -> dict:
        """
        Получить информацию о конкретном трейд оффере
        
        Args:
            trade_offer_id: ID трейд оффера
            merge: Объединять ли предметы с описаниями
            
        Returns:
            Словарь с информацией о трейд оффере
        """
        return self._send_command_and_wait("get_trade_offer", trade_offer_id=trade_offer_id, merge=merge)
    
    def accept_trade_offer(self, trade_offer_id: str) -> dict:
        """
        Принять трейд оффер
        
        Args:
            trade_offer_id: ID трейд оффера
            
        Returns:
            Результат принятия оффера
        """
        return self._send_command_and_wait("accept_trade_offer", trade_offer_id=trade_offer_id)
    
    def decline_trade_offer(self, trade_offer_id: str) -> dict:
        """
        Отклонить трейд оффер
        
        Args:
            trade_offer_id: ID трейд оффера
            
        Returns:
            Результат отклонения оффера
        """
        return self._send_command_and_wait("decline_trade_offer", trade_offer_id=trade_offer_id)
    
    def cancel_trade_offer(self, trade_offer_id: str) -> dict:
        """
        Отменить отправленный трейд оффер
        
        Args:
            trade_offer_id: ID трейд оффера
            
        Returns:
            Результат отмены оффера
        """
        return self._send_command_and_wait("cancel_trade_offer", trade_offer_id=trade_offer_id)
    
    def make_offer(
        self,
        items_from_me: list,
        items_from_them: list,
        partner_steam_id: str,
        message: str
    ) -> dict:
        """
        Создать трейд оффер
        
        Args:
            items_from_me: Список предметов от меня
            items_from_them: Список предметов от партнера
            partner_steam_id: Steam ID партнера
            message: Сообщение к офферу
            
        Returns:
            Результат создания оффера
        """
        return self._send_command_and_wait(
            "make_offer",
            items_from_me=items_from_me,
            items_from_them=items_from_them,
            partner_steam_id=partner_steam_id,
            message=message
        )
    
    def get_my_inventory(self, game: GameOptions, merge: bool = True, count: int = 100) -> dict:
        """
        Получить мой инвентарь
        
        Args:
            game: Опции игры (app_id, context_id)
            merge: Объединять ли предметы с описаниями
            count: Количество предметов для загрузки
            
        Returns:
            Словарь с инвентарем
        """
        return self._send_command_and_wait(
            "get_my_inventory",
            app_id=game.app_id,
            context_id=game.context_id,
            merge=merge,
            count=count
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
    
    def get_wallet_balance(self) -> str:
        """
        Получить баланс кошелька Steam
        
        Returns:
            Строка с балансом (например "$5.00" или "5,00 pуб.")
        """
        return self._send_command_and_wait("get_wallet_balance")
    
    # ===== Market методы =====
    
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
            price_single_item: Цена за единицу
            quantity: Количество
            game: Опции игры
            currency: Валюта
            
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

