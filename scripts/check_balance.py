import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request


BASE_URL = os.getenv("UPTIME_BASE_URL", "https://uptime.maolaoapi.com").rstrip("/")
THRESHOLD = float(os.getenv("BALANCE_THRESHOLD", "30"))
COOLDOWN_HOURS = float(os.getenv("NOTIFY_COOLDOWN_HOURS", "12"))
DOCS_DIR = Path("docs")
STATUS_PATH = DOCS_DIR / "status.json"
STATE_PATH = DOCS_DIR / "alert-state.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def http_json(path_or_url: str, method: str = "GET", body: Any = None, token: str | None = None) -> Any:
    url = path_or_url if path_or_url.startswith("http") else f"{BASE_URL}{path_or_url}"
    payload = None
    headers = {"Accept": "application/json"}
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = request.Request(url, data=payload, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail[:500]}") from exc


def login() -> str:
    username = os.getenv("UPTIME_USERNAME")
    password = os.getenv("UPTIME_PASSWORD")
    token = os.getenv("UPTIME_TOKEN")
    if token:
        return token
    if not username or not password:
        raise RuntimeError("缺少 UPTIME_USERNAME / UPTIME_PASSWORD，或 UPTIME_TOKEN。")
    data = http_json("/api/auth/login", method="POST", body={"userName": username, "password": password})
    if not isinstance(data, dict) or not data.get("token"):
        raise RuntimeError("登录成功响应中没有 token。")
    return str(data["token"])


def extract_channels(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("channels"), list):
        return data["channels"]
    if isinstance(data, list):
        return data
    raise RuntimeError("接口返回格式不符合预期，没有找到 channels 列表。")


def to_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_channel(item: dict[str, Any]) -> dict[str, Any]:
    balance = to_number(item.get("balance"))
    threshold_override = to_number(item.get("lowBalanceThresholdOverride"))
    threshold = threshold_override if threshold_override is not None else THRESHOLD
    channel_id = item.get("id") or item.get("channelId") or item.get("name")
    return {
        "id": channel_id,
        "name": str(item.get("name") or item.get("channelName") or channel_id),
        "platform": item.get("platform"),
        "baseUrl": item.get("baseUrl"),
        "balance": balance,
        "threshold": threshold,
        "tokenCount": item.get("tokenCount"),
        "lastSyncedAt": item.get("lastSyncedAt"),
        "lastSyncError": item.get("lastSyncError"),
        "isLow": balance is not None and balance < threshold,
        "needsLogin": bool(item.get("lastSyncError")),
    }


def should_notify(channel: dict[str, Any], state: dict[str, Any], checked_at: str) -> bool:
    key = str(channel["id"])
    previous = state.get(key, {}) if isinstance(state.get(key), dict) else {}
    if not channel["isLow"]:
        state[key] = {"isLow": False, "lastRecoveredAt": checked_at, "lastNotifiedAt": previous.get("lastNotifiedAt")}
        return False

    last_notified = previous.get("lastNotifiedAt")
    if not last_notified:
        state[key] = {"isLow": True, "lastNotifiedAt": checked_at}
        return True

    try:
        last_time = datetime.fromisoformat(last_notified.replace("Z", "+00:00"))
        elapsed_hours = (datetime.fromisoformat(checked_at) - last_time).total_seconds() / 3600
    except Exception:
        elapsed_hours = COOLDOWN_HOURS + 1

    if elapsed_hours >= COOLDOWN_HOURS:
        state[key] = {"isLow": True, "lastNotifiedAt": checked_at}
        return True

    state[key] = {**previous, "isLow": True}
    return False


def send_telegram(message: str) -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("未配置 Telegram，跳过通知。")
        return

    api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = parse.urlencode({"chat_id": chat_id, "text": message, "disable_web_page_preview": "true"}).encode("utf-8")
    req = request.Request(api_url, data=payload, method="POST")
    with request.urlopen(req, timeout=30) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"Telegram 通知失败：HTTP {resp.status}")


def format_message(channels: list[dict[str, Any]], checked_at: str) -> str:
    lines = ["渠道余额提醒", f"检查时间：{checked_at}", ""]
    for channel in channels:
        balance = "未知" if channel["balance"] is None else f"{channel['balance']:.4g}"
        lines.append(f"- {channel['name']}：余额 {balance}，阈值 {channel['threshold']:.4g}")
    lines.append("")
    lines.append(f"后台：{BASE_URL}/dashboard")
    return "\n".join(lines)


def main() -> int:
    checked_at = now_iso()
    status: dict[str, Any] = {
        "ok": False,
        "checkedAt": checked_at,
        "baseUrl": BASE_URL,
        "threshold": THRESHOLD,
        "channels": [],
        "lowChannels": [],
        "error": None,
    }

    try:
        token = login()
        data = http_json("/api/channels/search", token=token)
        channels = [normalize_channel(item) for item in extract_channels(data)]
        low_channels = [channel for channel in channels if channel["isLow"]]
        state = read_json(STATE_PATH, {})
        notify_channels = [channel for channel in low_channels if should_notify(channel, state, checked_at)]

        if notify_channels:
            send_telegram(format_message(notify_channels, checked_at))

        status.update({"ok": True, "channels": channels, "lowChannels": low_channels, "notifiedChannels": notify_channels})
        write_json(STATE_PATH, state)
        write_json(STATUS_PATH, status)
        print(f"检查完成：{len(channels)} 个渠道，{len(low_channels)} 个低余额。")
        return 0
    except Exception as exc:
        status["error"] = str(exc)
        write_json(STATUS_PATH, status)
        print(f"检查失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
