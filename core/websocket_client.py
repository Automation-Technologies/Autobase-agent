"""
WebSocket клиент для связи с AutoBase сервером.
"""
import asyncio
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
        manifest: список логинов, которые обслуживает этот агент.
        """
        self.is_running = True
        headers = {"Authorization": self.agent_token}
        
        try:
            async with websockets.connect(
                self.server_url,
                extra_headers=headers,
                ping_interval=30,
                ping_timeout=10
            ) as websocket:
                self.websocket = websocket
                self.on_status_change_callback(True)
                self.logger.info(f"Подключено к {self.server_url}")
                
                # Отправляем манифест
                manifest_msg = {
                    "type": "manifest",
                    "logins": manifest
                }
                await websocket.send(json.dumps(manifest_msg))
                self.logger.info(f"Манифест отправлен: {len(manifest)} логинов")
                
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
                self.logger.info(f"Получена команда: {command.get('cmd')}")
                
                # Передаем команду в обработчик
                response = await self.on_command_callback(command)
                
                # Отправляем ответ серверу
                await self.websocket.send(json.dumps(response))
                
            except websockets.exceptions.ConnectionClosed:
                self.logger.warning("Соединение закрыто сервером")
                self.on_status_change_callback(False)
                break
            except Exception as e:
                self.logger.error(f"Ошибка обработки команды: {e}")
    
    async def disconnect(self) -> None:
        """Отключиться от сервера."""
        self.is_running = False
        if self.websocket:
            await self.websocket.close()
            self.websocket = None
        self.on_status_change_callback(False)

