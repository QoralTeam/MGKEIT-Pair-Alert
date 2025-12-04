import aiohttp
import requests

from bot.config import settings

BASE_URL = settings.BASE_URL
HEADERS = {"Authorization": f"Bearer {settings.API_KEY}"}


async def fetch_timetable(group: str, week: str = "current"):
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_URL}/timetable"
        params = {"group": group, "week": week}
        async with session.get(url, headers=HEADERS, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            return None


def fetch_schedule(group, week="current"):
    url = f"{BASE_URL}/timetable"
    params = {"group": group, "week": week}
    response = requests.get(url, headers=HEADERS, params=params)
    if response.status_code == 200:
        return response.json()
    return None


def fetch_groups():
    url = f"{BASE_URL}/groups"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    return None
