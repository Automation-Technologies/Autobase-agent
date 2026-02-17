"""
Клиент Smart Ingestion для связи с AgentGateway (steam_bot).

Задачи:
- CHECK_EXISTENCE: узнать, какие логины уже есть в steam_accounts
- REGISTER: зарегистрировать новые аккаунты с балансом
"""

from typing import List, Dict, Any

import aiohttp


class IngestionClient:
    """HTTP‑клиент для Smart Ingestion."""

    def __init__(self, base_url: str, agent_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._agent_token = agent_token

    async def check_existence(self, accounts: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Проверка существования аккаунтов.

        Request:
            POST {base_url}/ingestion/check
            {
              "token": "<agent_token>",
              "accounts": [{"login": "..."}]
            }
        Response:
            {
              "existing": ["login1", ...],
              "new": ["login2", ...]
            }
        """
        url = f"{self._base_url}/ingestion/check"
        payload = {
            "token": self._agent_token,
            "accounts": accounts,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                return data

    async def register_accounts(self, accounts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Регистрация новых аккаунтов в steam_accounts.

        Request:
            POST {base_url}/ingestion/register
            {
              "token": "<agent_token>",
              "accounts": [
                {
                  "login": "...",
                  "steamid": "...",
                  "balance": 0.0,
                  "currency": "RUB"
                }
              ]
            }
        Response:
            {
              "created": ["login1", ...],
              "skipped": ["login2", ...]
            }
        """
        url = f"{self._base_url}/ingestion/register"
        payload = {
            "token": self._agent_token,
            "accounts": accounts,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                return data


