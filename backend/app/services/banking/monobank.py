"""Monobank provider implementation."""
import asyncio
import logging
from typing import List, Optional

import aiohttp
from app.services import BankProvider, BankAccount, BankTransaction

logger = logging.getLogger(__name__)

MONOBANK_API = "https://api.monobank.ua"


class MonobankProvider(BankProvider):
    async def _request(self, token: str, method: str, path: str, json_data=None, timeout=15) -> Optional[dict]:
        headers = {"X-Token": token}
        url = f"{MONOBANK_API}{path}"
        for attempt in range(2):
            try:
                async with aiohttp.ClientSession() as session:
                    coro = session.request(method, url, headers=headers, json=json_data)
                    async with asyncio.timeout(timeout):
                        async with coro as resp:
                            if resp.status == 200:
                                return await resp.json()
                            if resp.status == 429:
                                logger.warning(f"Monobank rate limited, attempt {attempt + 1}")
                                await asyncio.sleep(2)
                                continue
                            body = (await resp.text())[:200]
                            logger.error(f"Monobank {method} {path} -> HTTP {resp.status}: {body}")
                            return None
            except asyncio.TimeoutError:
                logger.error(f"Monobank timeout: {method} {path}")
                return None
            except Exception as e:
                logger.error(f"Monobank error: {method} {path}: {e}")
                if attempt >= 1:
                    return None
                await asyncio.sleep(1)
        return None

    _ci_cache: dict = {}

    async def get_client_info(self, token: str, ttl: int = 60) -> Optional[dict]:
        """/personal/client-info is rate limited (1/min per token) — share one cached response
        between balances and jars."""
        import hashlib
        import time
        key = hashlib.sha256(token.encode()).hexdigest()
        hit = self._ci_cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        data = await self._request(token, "GET", "/personal/client-info")
        if data:
            self._ci_cache[key] = (time.time(), data)
        return data or (hit[1] if hit else None)

    async def get_jars(self, token: str) -> list:
        data = await self.get_client_info(token)
        return (data or {}).get("jars", []) or []

    async def get_accounts(self, token: str) -> List[BankAccount]:
        data = await self.get_client_info(token)
        if not data:
            return []
        accounts = []
        for acc in data.get("accounts", []):
            accounts.append(BankAccount(
                external_id=str(acc.get("id")),
                name=f"{acc.get('type', 'unknown')} ({acc.get('currencyCode', 980)})",
                balance=acc.get("balance", 0) / 100.0,
                credit_limit=acc.get("creditLimit", 0) / 100.0,
            ))
        return accounts

    async def get_balance(self, token: str) -> float:
        accounts = await self.get_accounts(token)
        return sum(a.balance - a.credit_limit for a in accounts)

    async def register_webhook(self, token: str, webhook_url: str) -> bool:
        resp = await self._request(token, "POST", "/personal/webhook", json_data={"webHookUrl": webhook_url})
        return resp is not None

    async def get_recent_transactions(self, token: str, account_id: str, limit: int = 50) -> List[BankTransaction]:
        now = int(asyncio.get_event_loop().time())
        week_ago = now - 7 * 86400
        data = await self._request(token, "GET", f"/personal/statement/{account_id}/{week_ago}/{now}")
        if not data:
            return []
        txs = []
        for item in data[:limit]:
            txs.append(BankTransaction(
                external_id=str(item.get("id", "")),
                amount=abs(item.get("amount", 0)) / 100.0,
                description=item.get("description", "Без опису"),
                timestamp=str(item.get("time", "")),
            ))
        return txs


monobank = MonobankProvider()
