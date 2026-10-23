"""Finavia's Public Flights API: an airport's departures as XML.

Every request needs a key of the user's own, free from Finavia's API portal. The gateway is Azure API Management,
which answers a missing or wrong key with 401.
"""

from __future__ import annotations

import aiohttp

from .const import API_KEY_HEADER, API_URL

TIMEOUT = aiohttp.ClientTimeout(total=30)


class FinaviaError(Exception):
    """The API couldn't be reached, or it answered with an error or something that isn't its XML."""


class FinaviaAuthError(FinaviaError):
    """The key is wrong or its subscription is no longer active."""


class FinaviaClient:
    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def departures_xml(self, airport: str) -> bytes:
        try:
            async with self._session.get(
                API_URL.format(airport=airport), headers={API_KEY_HEADER: self._api_key}, timeout=TIMEOUT
            ) as response:
                if response.status == 401:
                    raise FinaviaAuthError("Finavia refused the API key")
                if response.status != 200:
                    raise FinaviaError(f"Finavia's flights API answered with status {response.status}")
                # Bytes, so the XML declaration decides the encoding: Finavia's content type names no charset.
                return await response.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            # A timeout's message is empty, and the coordinator logs only the first failure, so the type is the cause.
            raise FinaviaError(f"Finavia's flights API couldn't be reached: {str(err) or type(err).__name__}") from err
