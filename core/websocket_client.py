"""
WebSocket клиент для связи с AutoBase сервером.
"""
import json
import logging
from typing import Callable, Optional, List

import websockets
from websockets.client import WebSocketClientProtocol


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
                await websocket.send(json.dumps(manifest_msg))
                self.logger.info(f"Манифест отправлен: {len(manifest)} логинов: {manifest}")

                # Слушаем команды
                await self._listen_loop()

        except websockets.exceptions.WebSocketException as e:
            self.logger.error(f"WebSocket ошибка: {e}")
            self.on_status_change_callback(False)
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка: {e}")
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

                # Отправляем ответ серверу
                await self.websocket.send(json.dumps(response))
                self.logger.debug(f"Ответ отправлен для request_id={request_id}")

            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("Соединение закрыто сервером")
                self.on_status_change_callback(False)
                break
            except Exception as e:
                self.logger.error(f"Ошибка обработки команды: {e}", exc_info=True)

    async def disconnect(self) -> None:
        """Отключиться от сервера."""
        self.is_running = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        self.on_status_change_callback(False)
