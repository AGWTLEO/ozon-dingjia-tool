from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree


CBR_DAILY_XML_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
SOURCE_NAME = "俄罗斯央行 Bank of Russia"
DEFAULT_RATE = 12.5


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def today_text() -> str:
    return date.today().isoformat()


def load_exchange_cache(cache_path: Path, default_rate: float = DEFAULT_RATE) -> dict[str, Any]:
    if cache_path.exists():
        try:
            with cache_path.open("r", encoding="utf-8") as f:
                cache = json.load(f)
            if float(cache.get("cny_to_rub", 0)) > 0:
                return cache
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
    return {
        "cny_to_rub": default_rate,
        "source": "默认汇率",
        "updated_at": "",
        "date": "",
        "rate_date": "",
        "warning": "当前汇率不是实时汇率，请确认后再定价。",
    }


def save_exchange_cache(cache_path: Path, cache: dict[str, Any]) -> None:
    cache_path.parent.mkdir(exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def parse_cbr_date(raw: str) -> str:
    try:
        return datetime.strptime(raw, "%d.%m.%Y").date().isoformat()
    except (TypeError, ValueError):
        return raw or ""


def fetch_cbr_cny_rate(timeout: int = 10) -> dict[str, Any]:
    request = Request(
        CBR_DAILY_XML_URL,
        headers={"User-Agent": "OzonPricingTool/1.0"},
    )
    with urlopen(request, timeout=timeout) as response:
        body = response.read()

    root = ElementTree.fromstring(body)
    for valute in root.findall("Valute"):
        char_code = valute.findtext("CharCode", "").strip().upper()
        if char_code != "CNY":
            continue
        nominal = float((valute.findtext("Nominal", "1") or "1").replace(",", "."))
        value = float((valute.findtext("Value", "0") or "0").replace(",", "."))
        if nominal <= 0 or value <= 0:
            raise ValueError("Bank of Russia CNY rate is empty.")
        return {
            "cny_to_rub": round(value / nominal, 4),
            "source": SOURCE_NAME,
            "updated_at": now_text(),
            "date": today_text(),
            "rate_date": parse_cbr_date(root.attrib.get("Date", "")),
            "warning": "",
        }

    raise ValueError("Bank of Russia XML did not include CNY.")


def get_cny_to_rub_rate(
    cache_path: Path,
    default_rate: float = DEFAULT_RATE,
    force: bool = False,
) -> dict[str, Any]:
    cache = load_exchange_cache(cache_path, default_rate)
    today = today_text()

    if not force and cache.get("date") == today and float(cache.get("cny_to_rub", 0)) > 0:
        return {
            **cache,
            "from_cache": True,
            "ok": not bool(cache.get("warning")),
        }

    try:
        fresh = fetch_cbr_cny_rate()
        save_exchange_cache(cache_path, fresh)
        return {**fresh, "from_cache": False, "ok": True}
    except (OSError, URLError, TimeoutError, ValueError, ElementTree.ParseError):
        fallback = {
            **cache,
            "date": today,
            "last_attempt_at": now_text(),
            "warning": "自动汇率获取失败，当前使用上一次保存汇率，请手动检查。",
        }
        if not cache.get("updated_at"):
            fallback["warning"] = "当前汇率不是实时汇率，请确认后再定价。"
        save_exchange_cache(cache_path, fallback)
        return {**fallback, "from_cache": True, "ok": False}
