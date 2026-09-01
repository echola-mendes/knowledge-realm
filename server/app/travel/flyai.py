"""飞猪 FlyAI skill 封装：CLI 单行 JSON 契约，免 Key trial 可用。

契约（对齐 alibaba-flyai/flyai-skill README）：
- `flyai search-flight --origin <city> --destination <city> --dep-date YYYY-MM-DD
   [--back-date YYYY-MM-DD] [--journey-type 1|2] [--seat-class-name 经济舱|公务舱|头等舱]
   [--adult-count N] [--max-price N] [--sort-type 3]`
- `flyai search-hotel --dest-name <city> --check-in-date ... --check-out-date ... [--poi-name ...]
   [--hotel-stars N] [--max-price N] [--sort N]`
- stdout 单行 JSON（机票含 itemList），stderr 为错误；trial 免 Key，配额受限可设 FLYAI_API_KEY。
"""
from __future__ import annotations

import json
import subprocess
from typing import Any

from app.config import get_settings


class FlyaiError(Exception):
    """flyai CLI 调用失败（未安装 / 超时 / 非零退出 / 输出不可解析）。"""


def _run_cli(args: list[str]) -> dict[str, Any]:
    settings = get_settings()
    env: dict[str, str] | None = None
    if settings.flyai_api_key:
        import os

        env = dict(os.environ)
        env["FLYAI_API_KEY"] = settings.flyai_api_key
    try:
        proc = subprocess.run(  # noqa: S603 - 路径来自本机 env 配置
            [settings.flyai_cli, *args],
            capture_output=True,
            text=True,
            timeout=settings.flyai_timeout,
            env=env,
        )
    except FileNotFoundError as exc:
        raise FlyaiError(f"未找到 flyai CLI（{settings.flyai_cli}），请安装 flyai-skill") from exc
    except subprocess.TimeoutExpired as exc:
        raise FlyaiError(f"flyai CLI 超时（>{settings.flyai_timeout}s）") from exc
    if proc.returncode != 0:
        hint = (proc.stderr or "").strip().splitlines()
        raise FlyaiError(f"flyai CLI 失败：{hint[-1] if hint else f'exit {proc.returncode}'}")
    stdout = (proc.stdout or "").strip()
    if not stdout:
        raise FlyaiError("flyai CLI 无输出")
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise FlyaiError("flyai CLI 输出不可解析为 JSON")


def search_flights(
    *,
    origin: str,
    destination: str,
    dep_date: str,
    back_date: str | None = None,
    seat_class: str | None = None,
    adult_count: int = 1,
    max_price: int | None = None,
) -> dict[str, Any]:
    """机票搜索；原样返回 flyai 响应（含 itemList），不做字段删改。"""
    if not origin or not destination or not dep_date:
        raise FlyaiError("机票搜索缺少必要参数：出发地/目的地/出发日期")
    args = [
        "search-flight",
        "--origin", origin,
        "--destination", destination,
        "--dep-date", dep_date,
        "--journey-type", "2" if back_date else "1",
    ]
    if back_date:
        args += ["--back-date", back_date]
    if seat_class:
        args += ["--seat-class-name", seat_class]
    if adult_count and adult_count > 0:
        args += ["--adult-count", str(adult_count)]
    if max_price:
        args += ["--max-price", str(max_price)]
    args += ["--sort-type", "3"]
    return _run_cli(args)


def search_hotels(
    *,
    dest_name: str,
    check_in_date: str,
    check_out_date: str,
    poi_name: str | None = None,
    hotel_stars: int | None = None,
    max_price: int | None = None,
) -> dict[str, Any]:
    """酒店搜索；原样返回 flyai 响应。"""
    if not dest_name or not check_in_date or not check_out_date:
        raise FlyaiError("酒店搜索缺少必要参数：城市/入住/离店日期")
    args = [
        "search-hotel",
        "--dest-name", dest_name,
        "--check-in-date", check_in_date,
        "--check-out-date", check_out_date,
    ]
    if poi_name:
        args += ["--poi-name", poi_name]
    if hotel_stars:
        args += ["--hotel-stars", str(hotel_stars)]
    if max_price:
        args += ["--max-price", str(max_price)]
    return _run_cli(args)
