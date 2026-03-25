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

    async def _heartbeat_loop(self) -> None:
        """Фоновая отправка 'ping' сообщений чтобы соединение между агентом и сервером не разрывалось в простое."""
        while self.is_running and self.websocket:
            try:
                await self.websocket.send(json.dumps({"type": "ping"}))
                await asyncio.sleep(40)
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

        # Немного спагетти кода
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
            ws_url = f"{ws_url}/ws/{self.agent_token}"
        else:
            ws_url = f"{ws_url}ws/{self.agent_token}"

        headers = {"Authorization": self.agent_token}

        try:
            async with websockets.connect(
                    ws_url,
                    extra_headers=headers,
                    ping_interval=30,
                    ping_timeout=10
            ) as websocket:
                self.websocket = websocket
                self.on_status_change_callback(True)
                self.logger.info(f"Подключено к {ws_url}")

                # Отправляем манифест сразу после подключения
                manifest_msg = {
                    "type": "manifest",
                    "logins": manifest
                }
                try:
                    await websocket.send(json.dumps(manifest_msg))
                except websockets.exceptions.ConnectionClosed as e:
                    self.logger.error(
                        "Failed to send manifest: connection closed "
                        f"(type={type(e).__name__}, code={getattr(e, 'code', None)}, reason={getattr(e, 'reason', None)})"
                    )
                    self.on_status_change_callback(False)
                    return
                except Exception as e:
                    self.logger.error(f"Failed to send manifest: {type(e).__name__}: {e}", exc_info=True)
                    self.on_status_change_callback(False)
                    return
                self.logger.info(f"Манифест отправлен: {len(manifest)} логинов: {manifest}")

                asyncio.create_task(self._heartbeat_loop())

                # Слушаем команды
                await self._listen_loop()

        except websockets.exceptions.WebSocketException as e:
            self.logger.error(f"WebSocket ошибка: {type(e).__name__}: {e}", exc_info=True)
            self.on_status_change_callback(False)
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка: {type(e).__name__}: {e}", exc_info=True)
            self.on_status_change_callback(False)
        finally:
            self.is_running = False
            self.websocket = None

    async def _listen_loop(self) -> None:
        """Цикл прослушивания команд от сервера."""
        while self.is_running and self.websocket:
            try:
                message = await self.websocket.recv()
                command = json.loads(message)

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
