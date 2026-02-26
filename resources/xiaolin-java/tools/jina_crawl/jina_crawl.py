#!/usr/bin/env python3
"""
Jina Reader API 网页爬取脚本
按 r.jina.ai 规范请求，将指定 URL 爬取为 Markdown 并保存。
运行环境：conda 环境 alphafrog
"""

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

JINA_BASE = "https://r.jina.ai/"
DEFAULTS = {
    "env_file": ".env",
    "api_key_env": "JINA_API_KEY",
    "urls": [],
    "output_dir": "./output",
    "timeout": 60,
    "retries": 3,
}

console = Console()


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    out = DEFAULTS.copy()
    for k, v in (cfg or {}).items():
        if k in out and v is not None:
            out[k] = v
    return out


def ensure_output_dir(output_dir: str) -> Path:
    p = Path(output_dir).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def url_to_safe_filename(url: str) -> str:
    """从 URL 生成安全的文件名（不含扩展名）"""
    parsed = urlparse(url)
    netloc = parsed.netloc.replace(":", "_").replace(".", "_")
    path = parsed.path.strip("/") or "index"
    path = re.sub(r"[^\w\-/]", "_", path).replace("/", "_")
    if not path or path == "_":
        path = "index"
    return f"{netloc}_{path}"[:120]


def crawl_url(
    url: str,
    api_key: str | None,
    timeout: int,
    retries: int,
) -> str:
    """请求 r.jina.ai 爬取指定 URL，返回 Markdown 文本。"""
    # 使用 path 形式: https://r.jina.ai/{encoded_url}
    encoded = quote(url, safe="")
    req_url = f"{JINA_BASE.rstrip('/')}/{encoded}"

    headers = {
        "X-Respond-With": "markdown",
        "Accept": "text/plain; charset=utf-8",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(req_url, headers=headers, timeout=timeout)
            r.raise_for_status()

            ct = r.headers.get("Content-Type", "")
            if "application/json" in ct:
                data = r.json()
                if isinstance(data, dict) and "data" in data:
                    return data["data"] or ""
                return str(data)
            return r.text
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                console.print(f"  重试 {attempt}/{retries}...")
    raise last_err or RuntimeError("request failed")


def main():
    parser = argparse.ArgumentParser(
        description="使用 Jina Reader API 爬取网页为 Markdown"
    )
    parser.add_argument(
        "-c", "--config",
        default="configs/example.yml",
        help="YAML 配置文件路径（默认 configs/example.yml）",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=None,
        help="覆盖配置中的 output_dir",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path(__file__).resolve().parent / config_path
    if not config_path.exists():
        console.print(f"[red]配置文件不存在: {config_path}[/red]")
        sys.exit(1)

    cfg = load_config(str(config_path))

    env_file = cfg.get("env_file") or ".env"
    env_path = Path(env_file)
    if not env_path.is_absolute():
        # 相对路径：优先脚本所在目录，再尝试上级
        script_dir = Path(__file__).resolve().parent
        env_path = (script_dir / env_file).resolve()
        if not env_path.exists():
            env_path = (script_dir.parent / env_file).resolve()
    if env_path.exists():
        load_dotenv(env_path)

    api_key = os.environ.get(cfg.get("api_key_env", "JINA_API_KEY") or "")

    urls = cfg.get("urls") or []
    if not urls:
        console.print("[yellow]配置中 urls 为空，请编辑 YAML 添加待爬取链接[/yellow]")
        sys.exit(0)

    output_dir = args.output_dir or cfg.get("output_dir") or DEFAULTS["output_dir"]
    out_path = ensure_output_dir(output_dir)
    timeout = int(cfg.get("timeout") or DEFAULTS["timeout"])
    retries = int(cfg.get("retries") or DEFAULTS["retries"])

    console.print(f"[bold]输出目录:[/bold] {out_path}")
    console.print(f"[bold]待爬取:[/bold] {len(urls)} 个链接\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("爬取中...", total=len(urls))
        for i, url in enumerate(urls):
            progress.update(task, description=f"[{i+1}/{len(urls)}] {url[:60]}...")
            try:
                md = crawl_url(url, api_key, timeout, retries)
                fname = url_to_safe_filename(url) + ".md"
                out_file = out_path / fname
                out_file.write_text(md, encoding="utf-8")
                progress.console.print(f"  [green]✓[/green] {out_file.name}")
            except Exception as e:
                progress.console.print(f"  [red]✗[/red] {url}: {e}")
            progress.advance(task)

    console.print("\n[bold green]完成[/bold green]")


if __name__ == "__main__":
    main()
