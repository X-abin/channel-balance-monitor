import json
import os
import sys
import time
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib import error, parse, request


BASE_URL = os.getenv("UPTIME_BASE_URL", "https://uptime.maolaoapi.com").rstrip("/")
THRESHOLD = float(os.getenv("BALANCE_THRESHOLD", "30"))
COOLDOWN_HOURS = float(os.getenv("NOTIFY_COOLDOWN_HOURS", "12"))
UPSTREAM_BALANCE_ENABLED = os.getenv("UPSTREAM_BALANCE_ENABLED", "true").strip().lower() not in {"0", "false", "no"}
UPSTREAM_BALANCE_ONLY = os.getenv("UPSTREAM_BALANCE_ONLY", "true").strip().lower() not in {"0", "false", "no"}
MONITOR_STARRED_ONLY = os.getenv("MONITOR_STARRED_ONLY", "true").strip().lower() not in {"0", "false", "no"}
DOCS_DIR = Path("docs")
STATUS_PATH = DOCS_DIR / "status.json"
STATE_PATH = DOCS_DIR / "alert-state.json"
DEFAULT_NEWAPI_QUOTA_PER_UNIT = float(os.getenv("NEWAPI_DEFAULT_QUOTA_PER_UNIT", "500000"))
DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0 Safari/537.36",
}


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


def http_json(
    path_or_url: str,
    method: str = "GET",
    body: Any = None,
    token: str | None = None,
    extra_headers: dict[str, str] | None = None,
    opener: Any = None,
    timeout: int = 30,
    max_attempts: int = 3,
) -> Any:
    url = path_or_url if path_or_url.startswith("http") else f"{BASE_URL}{path_or_url}"
    payload = None
    headers = dict(DEFAULT_HEADERS)
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)

    transient_codes = {502, 503, 504}
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        req = request.Request(url, data=payload, method=method, headers=headers)
        try:
            open_request = opener.open if opener else request.urlopen
            with open_request(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"HTTP {exc.code} {url}: {detail[:500]}")
            if exc.code not in transient_codes or attempt == max_attempts:
                raise last_error from exc
        except error.URLError as exc:
            last_error = RuntimeError(f"请求失败 {url}: {exc.reason}")
            if attempt == max_attempts:
                raise last_error from exc
        time.sleep(attempt * 5)

    raise last_error or RuntimeError(f"请求失败 {url}")


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


def unwrap_api_data(data: Any) -> Any:
    if isinstance(data, dict) and "success" in data:
        if data.get("success") is True:
            return data.get("data")
        raise RuntimeError(str(data.get("message") or data.get("error") or "上游接口返回错误"))
    if isinstance(data, dict) and "code" in data:
        if data.get("code") in {0, "0"}:
            return data.get("data")
        raise RuntimeError(str(data.get("message") or data.get("error") or "上游接口返回错误"))
    if isinstance(data, dict) and "data" in data and len(data) <= 3:
        return data.get("data")
    return data


def find_number(data: Any, preferred_keys: tuple[str, ...]) -> float | None:
    if isinstance(data, dict):
        for key in preferred_keys:
            if key in data:
                number = to_number(data[key])
                if number is not None:
                    return number
        for value in data.values():
            number = find_number(value, preferred_keys)
            if number is not None:
                return number
    elif isinstance(data, list):
        for value in data:
            number = find_number(value, preferred_keys)
            if number is not None:
                return number
    return None


def join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def get_detail_value(detail: dict[str, Any], channel: dict[str, Any], preferred_keys: tuple[str, ...]) -> str | None:
    channel_data = detail.get("channel") if isinstance(detail.get("channel"), dict) else {}
    for source in (detail, channel_data, channel):
        value = find_text(source, preferred_keys)
        if value:
            return value
    return None


def get_detail_token(detail: dict[str, Any], channel: dict[str, Any]) -> str | None:
    return get_detail_value(
        detail,
        channel,
        (
            "savedToken",
            "savedAccessToken",
            "accessToken",
            "authToken",
            "token",
            "apiToken",
        ),
    )


def fetch_sub2api_balance(base_url: str, username: str, password: str, access_token: str | None = None) -> float:
    if access_token is None:
        login_data = unwrap_api_data(
            http_json(
                join_url(base_url, "/api/v1/auth/login"),
                method="POST",
                body={"email": username, "password": password},
            )
        )
        if not isinstance(login_data, dict) or not login_data.get("access_token"):
            raise RuntimeError("上游登录成功响应中没有 access_token")
        access_token = str(login_data["access_token"])

    profile_data = unwrap_api_data(
        http_json(
            join_url(base_url, "/api/v1/user/profile"),
            token=access_token,
            extra_headers={"X-User-UI-Request": "1"},
        )
    )
    balance = find_number(profile_data, ("balance", "remaining_balance", "available_balance"))
    if balance is None:
        raise RuntimeError("上游用户信息中没有找到余额字段")
    return balance


def find_text(data: Any, preferred_keys: tuple[str, ...]) -> str | None:
    if isinstance(data, dict):
        for key in preferred_keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in data.values():
            text = find_text(value, preferred_keys)
            if text:
                return text
    elif isinstance(data, list):
        for value in data:
            text = find_text(value, preferred_keys)
            if text:
                return text
    return None


def find_identifier(data: Any, preferred_keys: tuple[str, ...]) -> str | None:
    text = find_text(data, preferred_keys)
    if text:
        return text
    number = find_number(data, preferred_keys)
    if number is None:
        return None
    return str(int(number)) if number.is_integer() else str(number)


def newapi_quota_to_balance(quota: float, status_data: Any) -> float:
    status = status_data if isinstance(status_data, dict) else {}
    quota_per_unit = find_number(status, ("quota_per_unit",)) or DEFAULT_NEWAPI_QUOTA_PER_UNIT
    if quota_per_unit <= 0:
        quota_per_unit = DEFAULT_NEWAPI_QUOTA_PER_UNIT

    balance = quota / quota_per_unit
    display_type = str(status.get("quota_display_type") or "USD").upper()
    if display_type == "CNY":
        balance *= find_number(status, ("usd_exchange_rate",)) or 1
    elif display_type == "CUSTOM":
        balance *= find_number(status, ("custom_currency_exchange_rate",)) or 1
    return balance


def extract_newapi_balance(self_data: Any, status_data: Any) -> float:
    direct_balance = find_number(
        self_data,
        (
            "balance",
            "remaining_balance",
            "available_balance",
            "money",
            "amount",
            "credit",
            "credits",
        ),
    )
    if direct_balance is not None:
        return direct_balance

    quota = find_number(self_data, ("quota", "remain_quota", "remaining_quota"))
    if quota is None:
        raise RuntimeError("上游用户信息中没有找到余额或 quota 字段")
    return newapi_quota_to_balance(quota, status_data)


def logout_newapi_session(
    base_url: str,
    opener: Any,
    auth_token: str | None,
    user_id: str | None,
    session_id: str | None,
) -> None:
    if not auth_token:
        return

    extra_headers: dict[str, str] = {}
    if user_id:
        extra_headers["New-Api-User"] = user_id
    if session_id:
        extra_headers["X-Auth-Session"] = session_id

    try:
        http_json(
            join_url(base_url, "/api/user/auth/logout"),
            method="POST",
            token=auth_token,
            extra_headers=extra_headers,
            opener=opener,
            timeout=5,
            max_attempts=1,
        )
        return
    except Exception:
        pass

    try:
        http_json(
            join_url(base_url, "/api/user/logout"),
            token=auth_token,
            extra_headers=extra_headers,
            opener=opener,
            timeout=5,
            max_attempts=1,
        )
    except Exception:
        pass


def fetch_newapi_balance(base_url: str, username: str, password: str, auth_token: str | None = None, user_id: str | None = None) -> float:
    cookie_jar = CookieJar()
    opener = request.build_opener(request.HTTPCookieProcessor(cookie_jar))
    should_logout = auth_token is None

    status_data: Any = {}
    try:
        status_data = unwrap_api_data(http_json(join_url(base_url, "/api/status"), opener=opener))
    except Exception:
        status_data = {}

    if auth_token is None:
        login_data = unwrap_api_data(
            http_json(
                join_url(base_url, "/api/user/login"),
                method="POST",
                body={"username": username, "email": username, "password": password},
                opener=opener,
            )
        )
        auth_token = find_text(login_data, ("token", "access_token", "auth_token"))
        user_id = user_id or find_identifier(login_data, ("id", "user_id", "userId"))
        session_id = find_text(login_data, ("sid", "session_id", "sessionId"))
    else:
        session_id = None
    extra_headers = {"New-Api-User": user_id} if user_id else None

    try:
        self_data = unwrap_api_data(
            http_json(
                join_url(base_url, "/api/user/self"),
                token=auth_token,
                extra_headers=extra_headers,
                opener=opener,
            )
        )
        return extract_newapi_balance(self_data, status_data)
    finally:
        if should_logout:
            logout_newapi_session(base_url, opener, auth_token, user_id, session_id)


def get_detail_credentials(detail: dict[str, Any], channel: dict[str, Any]) -> tuple[str | None, str | None]:
    saved_username = detail.get("savedUserName")
    saved_password = detail.get("savedPassword")
    channel_data = detail.get("channel") if isinstance(detail.get("channel"), dict) else {}
    username = saved_username or channel_data.get("accountName") or channel.get("accountName") or channel.get("credentialUserName")
    password = saved_password or channel.get("savedPassword")
    return (str(username).strip() if username else None, str(password).strip() if password else None)


def refresh_upstream_balance(channel: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    if not UPSTREAM_BALANCE_ENABLED:
        if UPSTREAM_BALANCE_ONLY:
            channel["balanceSource"] = "upstream_failed"
            channel["upstreamBalanceError"] = "上游实时余额读取已关闭"
        return channel

    channel_data = detail.get("channel") if isinstance(detail.get("channel"), dict) else {}
    base_url = channel_data.get("baseUrl") or channel.get("baseUrl")
    platform = str(channel_data.get("platform") or channel.get("platform") or "").lower()
    username, password = get_detail_credentials(detail, channel_data or channel)
    token = get_detail_token(detail, channel_data or channel)
    if not base_url:
        channel["balanceSource"] = "upstream_failed"
        channel["upstreamBalanceError"] = "缺少上游地址、账号或密码"
        return channel
    if not token and (not username or not password):
        channel["balanceSource"] = "upstream_failed"
        channel["upstreamBalanceError"] = "缺少上游地址、账号或密码"
        return channel

    try:
        if "sub2" in platform:
            upstream_balance = fetch_sub2api_balance(str(base_url), username, password, access_token=token)
        elif "newapi" in platform or "new_api" in platform or "new api" in platform:
            upstream_balance = fetch_newapi_balance(str(base_url), username, password, auth_token=token)
        else:
            channel["balanceSource"] = "upstream_failed"
            channel["upstreamBalanceError"] = "暂未支持该平台类型的上游实时余额"
            return channel
        channel["balance"] = upstream_balance
        channel["balanceSource"] = "upstream"
        channel["isLow"] = upstream_balance < float(channel["threshold"])
    except Exception as exc:
        channel["balanceSource"] = "upstream_failed"
        channel["upstreamBalanceError"] = str(exc)
    return channel


def normalize_channel(item: dict[str, Any]) -> dict[str, Any]:
    dashboard_balance = to_number(item.get("balance"))
    balance = None if UPSTREAM_BALANCE_ONLY else dashboard_balance
    threshold_override = to_number(item.get("lowBalanceThresholdOverride"))
    threshold = threshold_override if threshold_override is not None else THRESHOLD
    channel_id = item.get("id") or item.get("channelId") or item.get("name")
    channel = {
        "id": channel_id,
        "name": str(item.get("name") or item.get("channelName") or channel_id),
        "platform": item.get("platform"),
        "baseUrl": item.get("baseUrl"),
        "isStarred": bool(item.get("isStarred")),
        "balance": balance,
        "balanceSource": "upstream_pending" if UPSTREAM_BALANCE_ONLY else "dashboard",
        "threshold": threshold,
        "tokenCount": item.get("tokenCount"),
        "lastSyncedAt": item.get("lastSyncedAt"),
        "lastSyncError": item.get("lastSyncError"),
        "isLow": balance is not None and balance < threshold,
        "needsLogin": bool(item.get("lastSyncError")),
    }
    if not UPSTREAM_BALANCE_ONLY:
        channel["dashboardBalance"] = dashboard_balance
    return channel


def channel_priority(channel: dict[str, Any]) -> tuple[int, float, str]:
    balance = channel["balance"]
    balance_value = float("inf") if balance is None else float(balance)
    return (0 if channel.get("isStarred") else 1, balance_value, str(channel["name"]).lower())


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
        star = "[星标] " if channel.get("isStarred") else ""
        source = "上游实时" if channel.get("balanceSource") == "upstream" else "后台同步"
        lines.append(f"- {star}{channel['name']}：余额 {balance}，阈值 {channel['threshold']:.4g}，来源 {source}")
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
        "skippedChannels": 0,
        "upstreamBalanceOnly": UPSTREAM_BALANCE_ONLY,
        "error": None,
    }

    try:
        token = login()
        data = http_json("/api/channels/search", token=token)
        all_channels = [normalize_channel(item) for item in extract_channels(data)]
        channels = [channel for channel in all_channels if channel["isStarred"]] if MONITOR_STARRED_ONLY else all_channels
        for channel in channels:
            try:
                detail = http_json(f"/api/channels/{channel['id']}", token=token)
                if isinstance(detail, dict):
                    refresh_upstream_balance(channel, detail)
            except Exception as exc:
                channel["upstreamBalanceError"] = str(exc)
        low_channels = sorted([channel for channel in channels if channel["isLow"]], key=channel_priority)
        failed_channels = sorted([channel for channel in channels if channel.get("balanceSource") == "upstream_failed"], key=channel_priority)
        state = read_json(STATE_PATH, {})
        notify_channels = sorted([channel for channel in low_channels if should_notify(channel, state, checked_at)], key=channel_priority)

        if notify_channels:
            send_telegram(format_message(notify_channels, checked_at))

        status.update({
            "ok": True,
            "channels": channels,
            "lowChannels": low_channels,
            "notifiedChannels": notify_channels,
            "failedChannels": failed_channels,
            "monitorStarredOnly": MONITOR_STARRED_ONLY,
            "upstreamBalanceOnly": UPSTREAM_BALANCE_ONLY,
            "totalChannels": len(all_channels),
            "skippedChannels": len(all_channels) - len(channels),
        })
        write_json(STATE_PATH, state)
        write_json(STATUS_PATH, status)
        print(f"检查完成：监测 {len(channels)} 个渠道，跳过 {len(all_channels) - len(channels)} 个未星标渠道，{len(low_channels)} 个低余额，{len(failed_channels)} 个实时读取失败。")
        return 0
    except Exception as exc:
        status["error"] = str(exc)
        write_json(STATUS_PATH, status)
        print(f"检查失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
