"""
WebSocket клиент для связи с AutoBase сервером.
"""
import asyncio
import json
import logging
from decimal import Decimal
from typing import Callable, Optional, List

import websockets
from websockets.client import WebSocketClientProtocol


class DecimalEncoder(json.JSONEncoder):
    """JSON энкодер с поддержкой Decimal"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super(DecimalEncoder, self).default(obj)


class WebSocketClient:
    """WebSocket клиент агента."""

    def __init__(
            self,
            server_url: str,
            agent_token: str,
            on_command_callback: Callable,
            on_status_change_callback: Callable
    ):
        self.server_url = server_url
        self.agent_token = agent_token
        self.on_command_callback = on_command_callback
        self.on_status_change_callback = on_status_change_callback

        self.websocket: Optional[WebSocketClientProtocol] = None
        self.is_running = False
        self.logger = logging.getLogger("WebSocketClient")
        self._backoff_seconds = 2
        self._max_backoff_seconds = 60

    async def _heartbeat_loop(self) -> None:
        """Фоновая отправка 'ping' сообщений чтобы соединение между агентом и сервером не разрывалось в простое."""
        while self.is_running and self.websocket:
            try:
                await self.websocket.send(json.dumps({"type": "ping"}))
                await asyncio.sleep(15)
            except websockets.exceptions.ConnectionClosed as e:
                self.logger.warning(
                    "Heartbeat: connection closed "
                    f"(type={type(e).__name__}, code={getattr(e, 'code', None)}, reason={getattr(e, 'reason', None)})"
                )
                break
            except Exception as e:
                self.logger.error(f"Heartbeat error: {type(e).__name__}: {e}", exc_info=True)
                break

    async def connect(self, manifest: List[str]) -> None:
        """
        Подключиться к серверу и отправить манифест.
        Manifest: список логинов, которые обслуживает этот агент.
        """
        self.is_running = True
        ws_url = self._build_ws_url()
        headers = {"Authorization": self.agent_token}
        backoff = self._backoff_seconds

        while self.is_running:
            try:
                self.logger.info(f"Попытка подключения к {ws_url}")
                async with websockets.connect(
                        ws_url,
                        extra_headers=headers,
                        ping_interval=20,
                        ping_timeout=20
                ) as websocket:
                    self.websocket = websocket
                    self.on_status_change_callback(True)
                    self.logger.info(f"Подключено к {ws_url}")

                    # Отправляем манифест сразу после подключения
                    manifest_msg = {
                        "type": "manifest",
                        "logins": manifest
                    }
                    await websocket.send(json.dumps(manifest_msg))
                    self.logger.info(f"Манифест отправлен: {len(manifest)} логинов: {manifest}")

                    asyncio.create_task(self._heartbeat_loop())
                    backoff = self._backoff_seconds

                    # Слушаем команды
                    await self._listen_loop()

            except websockets.exceptions.WebSocketException as e:
                self.logger.error(f"WebSocket ошибка: {type(e).__name__}: {e}", exc_info=True)
                self.on_status_change_callback(False)
            except OSError as e:
                self.logger.error(f"Сетевая ошибка сокета: {type(e).__name__}: {e}", exc_info=True)
                self.on_status_change_callback(False)
            except Exception as e:
                self.logger.error(f"Неожиданная ошибка: {type(e).__name__}: {e}", exc_info=True)
                self.on_status_change_callback(False)
            finally:
                self.websocket = None

            if self.is_running:
                self.logger.info(f"Переподключение через {backoff} сек")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff_seconds)

        self.websocket = None

    async def _listen_loop(self) -> None:
        """Цикл прослушивания команд от сервера."""
        while self.is_running and self.websocket:
            try:
                message = await self.websocket.recv()
                command = json.loads(message)
                msg_type = command.get("type")

                if msg_type == "ack":
                    ack_request_id = command.get("request_id")
                    self.logger.info(f"ACK received from server (request_id={ack_request_id})")
                    continue

                # Извлекаем request_id из команды для ответа
                request_id = command.get("request_id")
                cmd_type = command.get("cmd")
                login = command.get("account_login")

                self.logger.info(f"Получена команда: {cmd_type} для {login} (request_id={request_id})")

                # Передаем команду в обработчик
                response = await self.on_command_callback(command)

                # Добавляем request_id в ответ, если его нет
                if "request_id" not in response:
                    response["request_id"] = request_id

                # Отправляем ответ серверу (с поддержкой Decimal через DecimalEncoder)
                self.logger.info(
                    "Sending response to server "
                    f"(cmd_type={cmd_type}, login={login}, request_id={request_id}, response_status={response.get('status')})"
                )
                try:
                    await self.websocket.send(json.dumps(response, cls=DecimalEncoder))
                except websockets.exceptions.ConnectionClosed as e:
                    self.logger.error(
                        "Send failed: connection closed "
                        f"(type={type(e).__name__}, code={getattr(e, 'code', None)}, reason={getattr(e, 'reason', None)}) "
                        f"for request_id={request_id}, cmd_type={cmd_type}, login={login}"
                    )
                    self.on_status_change_callback(False)
                    break
                except Exception as e:
                    self.logger.error(
                        f"Send failed for request_id={request_id}, cmd_type={cmd_type}, login={login}: "
                        f"{type(e).__name__}: {e}",
                        exc_info=True
                    )
                    self.on_status_change_callback(False)
                    break
                self.logger.info(f"Response sent to server (request_id={request_id})")

            except websockets.exceptions.ConnectionClosed as e:
                self.logger.warning(
                    "Connection closed while waiting for server message "
                    f"(type={type(e).__name__}, code={getattr(e, 'code', None)}, reason={getattr(e, 'reason', None)})"
                )
                self.on_status_change_callback(False)
                break
            except Exception as e:
                self.logger.error(f"Ошибка обработки команды: {type(e).__name__}: {e}", exc_info=True)

    async def disconnect(self) -> None:
        """Отключиться от сервера."""
        self.is_running = False
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                self.logger.error(f"Error during websocket close: {type(e).__name__}: {e}", exc_info=True)
            self.websocket = None
        self.on_status_change_callback(False)

    def _build_ws_url(self) -> str:
        """Собрать полный ws/wss URL для подключения агента."""
        # Формируем правильный WebSocket URL: ws://server_ip/ws/{token}
        # Если server_url уже содержит ws:// или wss://, используем как есть
        # Иначе добавляем ws://
        if not self.server_url.startswith(("ws://", "wss://")):
            # Если server_url содержит http:// или https://, заменяем на ws:// или wss://
            if self.server_url.startswith("https://"):
                ws_url = self.server_url.replace("https://", "wss://", 1)
            elif self.server_url.startswith("http://"):
                ws_url = self.server_url.replace("http://", "ws://", 1)
            else:
                ws_url = f"ws://{self.server_url}"
        else:
            ws_url = self.server_url

        # Добавляем путь /ws/{token}
        if not ws_url.endswith("/"):
            return f"{ws_url}/ws/{self.agent_token}"
        return f"{ws_url}ws/{self.agent_token}"
