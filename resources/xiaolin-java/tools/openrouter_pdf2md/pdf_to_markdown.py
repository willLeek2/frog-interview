import argparse
import base64
import concurrent.futures
import io
import json
import os
import sys
import threading
import time

import requests
import yaml
from PIL import Image
import fitz
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn


DEFAULTS = {
    "pdf": {
        "root": None,
        "path": None,
        "page_start": 1,
        "page_end": None,
    },
    "render": {
        "dpi": 200,
        "format": "jpeg",
        "jpeg_quality": 85,
        "max_side_px": 2200,
        "crop": None,
    },
    "openrouter": {
        "env_file": ".env",
        "api_key_env": "OPENROUTER_API_KEY",
        "model": None,
        "provider": None,
        "headers": {},
        "timeout_sec": 120,
        "max_tokens": 8192,
        "temperature": 0,
        "retries": 5,
        "rate_limit_qps": 0,
    },
    "prompt": {
        "system": (
            "You are an OCR and formatting assistant.\n"
            "Convert the provided page image into Markdown source that preserves the visual structure\n"
            "(headings, lists, tables, code blocks, bold/italic). Output only the Markdown source.\n"
            "Do not add explanations or wrap the answer in code fences.\n"
            "Only include the main body content. Exclude headers/footers, page numbers, watermarks,\n"
            "sidebars, navigation, and any non-body text.\n"
            "If some characters are unclear, keep placeholders like [UNK] rather than guessing."
        ),
        "user_template": (
            "Page {page_number} of {total_pages}.\n"
            "Transcribe the main body as Markdown source."
        ),
    },
    "output": {
        "root": None,
        "prefix": "out",
        "markdown_path": None,
        "pages_dir": None,
        "include_page_separators": True,
        "page_separator": "\n\n---\n\n<!-- page:{n} -->\n\n",
        "print_progress": True,
        "preview_chars": 0,
        "preview_compact": True,
    },
    "concurrency": {
        "workers": 1,
    },
}


RETRY_STATUS = {408, 429, 500, 502, 503}
RETRY_ERROR_CODES = {408, 429, 500, 502, 503}
FATAL_STATUS = {400, 401, 402, 403}


class SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def safe_format(template, **kwargs):
    if template is None:
        return ""
    return template.format_map(SafeDict(**kwargs))


def deep_merge(base, override):
    if not isinstance(override, dict):
        return override
    result = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def resolve_path(base_dir, path):
    if path is None:
        return None
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(base_dir, path))


def load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("YAML root must be a mapping.")
    cfg = deep_merge(DEFAULTS, raw)
    base_dir = os.path.dirname(os.path.abspath(config_path))

    cfg["pdf"]["root"] = resolve_path(base_dir, cfg["pdf"].get("root"))
    cfg["pdf"]["path"] = resolve_path(base_dir, cfg["pdf"].get("path"))
    cfg["output"]["root"] = resolve_path(base_dir, cfg["output"].get("root"))
    cfg["output"]["markdown_path"] = resolve_path(
        base_dir, cfg["output"].get("markdown_path")
    )
    cfg["output"]["pages_dir"] = resolve_path(
        base_dir, cfg["output"].get("pages_dir")
    )
    env_file = cfg["openrouter"].get("env_file")
    if env_file:
        cfg["openrouter"]["env_file"] = resolve_path(base_dir, env_file)
    else:
        cfg["openrouter"]["env_file"] = None

    render_fmt = str(cfg["render"].get("format", "jpeg")).lower()
    if render_fmt == "jpg":
        render_fmt = "jpeg"
    cfg["render"]["format"] = render_fmt

    return cfg


def validate_config(cfg):
    pdf_root = cfg["pdf"].get("root")
    pdf_path = cfg["pdf"].get("path")
    if not pdf_root and not pdf_path:
        raise ValueError("Either pdf.root or pdf.path is required.")
    if pdf_root:
        if not os.path.isdir(pdf_root):
            raise NotADirectoryError(f"pdf.root must be a directory: {pdf_root}")
    if pdf_path and not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path and not os.path.isfile(pdf_path):
        raise ValueError(f"pdf.path must be a file: {pdf_path}")

    model = cfg["openrouter"].get("model")
    if not model:
        raise ValueError("openrouter.model is required.")

    output_root = cfg["output"].get("root")
    if pdf_root:
        if not output_root:
            raise ValueError("output.root is required when pdf.root is configured.")
    elif not cfg["output"].get("markdown_path") and not output_root:
        raise ValueError("output.markdown_path or output.root is required in single-PDF mode.")

    prefix = str(cfg["output"].get("prefix") or "").strip()
    if not prefix:
        raise ValueError("output.prefix cannot be empty.")
    cfg["output"]["prefix"] = prefix

    workers = int(cfg.get("concurrency", {}).get("workers") or 1)
    if workers < 1:
        raise ValueError("concurrency.workers must be >= 1.")
    cfg["concurrency"]["workers"] = workers

    page_start = int(cfg["pdf"].get("page_start") or 1)
    page_end = cfg["pdf"].get("page_end")
    if page_end is not None:
        page_end = int(page_end)
    if page_start < 1:
        raise ValueError("pdf.page_start must be >= 1.")
    if page_end is not None and page_end < page_start:
        raise ValueError("pdf.page_end must be >= pdf.page_start.")
    cfg["pdf"]["page_start"] = page_start
    cfg["pdf"]["page_end"] = page_end

    crop = cfg["render"].get("crop")
    if crop:
        for key in ("left", "right", "top", "bottom"):
            value = float(crop.get(key, 0))
            if value < 0 or value >= 1:
                raise ValueError(f"render.crop.{key} must be in [0, 1).")
            crop[key] = value
        if crop.get("left", 0) + crop.get("right", 0) >= 1:
            raise ValueError("render.crop left+right must be < 1.")
        if crop.get("top", 0) + crop.get("bottom", 0) >= 1:
            raise ValueError("render.crop top+bottom must be < 1.")


class QpsLimiter:
    def __init__(self, qps):
        self.qps = float(qps or 0)
        self._last_time = None
        self._lock = threading.Lock()

    def wait(self):
        if self.qps <= 0:
            return
        min_interval = 1.0 / self.qps
        with self._lock:
            now = time.time()
            if self._last_time is not None:
                sleep_sec = self._last_time + min_interval - now
                if sleep_sec > 0:
                    time.sleep(sleep_sec)
                    now = time.time()
            self._last_time = now


def safe_print(print_lock, message):
    if print_lock is None:
        print(message)
        return
    with print_lock:
        print(message)


class WorkerProgressRenderer:
    def __init__(
        self,
        worker_totals,
        print_lock,
        bar_width=18,
        preview_width=60,
        enabled=True,
    ):
        self.worker_totals = list(worker_totals or [])
        self.total_workers = len(self.worker_totals)
        self.bar_width = int(bar_width or 18)
        self.preview_width = int(preview_width or 60)
        self.print_lock = print_lock
        self.enabled = bool(enabled) and self.total_workers > 0 and sys.stdout.isatty()
        self._started = False
        self._task_ids = {}
        self._console = Console() if self.enabled else None
        self._progress = (
            Progress(
                TextColumn("worker-{task.fields[worker_id]:>2}"),
                BarColumn(bar_width=self.bar_width),
                TextColumn("{task.completed:.0f}/{task.total:.0f}"),
                TextColumn("{task.fields[preview]}"),
                console=self._console,
                transient=False,
                refresh_per_second=8,
            )
            if self.enabled
            else None
        )

    def start(self):
        if not self.enabled:
            return
        with self.print_lock:
            self._start_locked()

    def update(self, worker_id, done, total, preview):
        preview_text = str(preview or "").strip()
        if len(preview_text) > self.preview_width:
            preview_text = preview_text[: self.preview_width - 3] + "..."
        worker_id = int(worker_id)
        done = int(done)
        total = int(total)

        if not self.enabled:
            progress = f"{done}/{total}" if total > 0 else "0/0"
            safe_print(self.print_lock, f"[worker-{worker_id}] {progress} {preview_text}")
            return

        with self.print_lock:
            if not self._started:
                self._start_locked()
            task_id = self._task_ids.get(worker_id)
            if task_id is None:
                task_id = self._progress.add_task(
                    "",
                    total=max(1, total),
                    completed=0,
                    worker_id=worker_id,
                    preview="",
                )
                self._task_ids[worker_id] = task_id
            self._progress.update(
                task_id,
                total=max(1, total),
                completed=min(done, max(1, total)),
                preview=preview_text,
            )

    def finish(self):
        if not self.enabled:
            return
        with self.print_lock:
            if self._started:
                self._progress.stop()
                self._started = False

    def _start_locked(self):
        if self._started:
            return
        self._progress.start()
        for worker_id in range(1, self.total_workers + 1):
            total = int(self.worker_totals[worker_id - 1] or 0)
            task_id = self._progress.add_task(
                "",
                total=max(1, total),
                completed=0,
                worker_id=worker_id,
                preview="",
            )
            self._task_ids[worker_id] = task_id
        self._started = True


def split_evenly(items, parts):
    if parts <= 0:
        return []
    chunk_count = min(parts, len(items))
    if chunk_count <= 0:
        return []

    base, remainder = divmod(len(items), chunk_count)
    chunks = []
    cursor = 0
    for index in range(chunk_count):
        size = base + (1 if index < remainder else 0)
        chunk = items[cursor : cursor + size]
        if chunk:
            chunks.append(chunk)
        cursor += size
    return chunks


def list_pdf_files(pdf_root):
    entries = []
    for name in os.listdir(pdf_root):
        full_path = os.path.join(pdf_root, name)
        if not os.path.isfile(full_path):
            continue
        if not name.lower().endswith(".pdf"):
            continue
        entries.append(full_path)
    entries.sort(key=lambda item: os.path.basename(item).lower())
    return entries


def ensure_parent_dir(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def render_page_to_image(page, render_cfg):
    dpi = float(render_cfg.get("dpi") or 200)
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix, alpha=False)

    if pix.n >= 3:
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    else:
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples).convert("RGB")

    crop = render_cfg.get("crop")
    if crop:
        width, height = img.size
        left = int(width * crop.get("left", 0))
        right = int(width * (1 - crop.get("right", 0)))
        top = int(height * crop.get("top", 0))
        bottom = int(height * (1 - crop.get("bottom", 0)))
        if left < right and top < bottom:
            img = img.crop((left, top, right, bottom))

    max_side_px = int(render_cfg.get("max_side_px") or 0)
    if max_side_px > 0:
        width, height = img.size
        max_side = max(width, height)
        if max_side > max_side_px:
            scale = max_side_px / float(max_side)
            new_size = (int(width * scale), int(height * scale))
            img = img.resize(new_size, Image.LANCZOS)

    return img


def image_to_data_url(image, render_cfg):
    fmt = render_cfg.get("format", "jpeg").lower()
    if fmt == "jpg":
        fmt = "jpeg"
    mime = "image/jpeg" if fmt == "jpeg" else "image/png"

    buffer = io.BytesIO()
    if fmt == "jpeg":
        quality = int(render_cfg.get("jpeg_quality") or 85)
        image.save(buffer, format="JPEG", quality=quality)
    else:
        image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_messages(cfg, page_number, total_pages, data_url, current_page_end=None):
    system_prompt = cfg["prompt"].get("system") or ""
    user_template = cfg["prompt"].get("user_template") or ""
    user_text = safe_format(
        user_template,
        page_number=page_number,
        page_index=page_number - 1,
        page_start=cfg["pdf"]["page_start"],
        page_end=current_page_end or cfg["pdf"]["page_end"] or total_pages,
        total_pages=total_pages,
    )

    messages = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt})
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    )
    return messages


def should_retry_status(status_code):
    return status_code in RETRY_STATUS


def should_retry_error_code(code):
    try:
        code_int = int(code)
    except (TypeError, ValueError):
        return False
    return code_int in RETRY_ERROR_CODES


def call_openrouter(cfg, messages, api_key, limiter=None):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    extra_headers = cfg["openrouter"].get("headers") or {}
    for key, value in extra_headers.items():
        key_lower = str(key).lower()
        if key_lower in ("authorization", "content-type"):
            continue
        headers[str(key)] = str(value)

    body = {
        "model": cfg["openrouter"]["model"],
        "messages": messages,
        "temperature": cfg["openrouter"].get("temperature"),
        "max_tokens": cfg["openrouter"].get("max_tokens"),
    }
    provider = cfg["openrouter"].get("provider")
    if provider:
        body["provider"] = provider

    timeout_sec = float(cfg["openrouter"].get("timeout_sec") or 120)
    retries = int(cfg["openrouter"].get("retries") or 0)

    for attempt in range(retries + 1):
        if limiter is not None:
            limiter.wait()

        try:
            response = requests.post(
                url, headers=headers, data=json.dumps(body), timeout=timeout_sec
            )
        except requests.RequestException as exc:
            if attempt < retries:
                backoff = min(60, 2 ** attempt)
                time.sleep(backoff)
                continue
            raise RuntimeError(f"Request failed: {exc}") from exc

        status = response.status_code
        if status in FATAL_STATUS:
            raise RuntimeError(
                f"OpenRouter request failed with HTTP {status}: {response.text}"
            )
        if should_retry_status(status):
            if attempt < retries:
                backoff = min(60, 2 ** attempt)
                time.sleep(backoff)
                continue
            raise RuntimeError(
                f"OpenRouter request failed with HTTP {status}: {response.text}"
            )

        try:
            data = response.json()
        except ValueError:
            if attempt < retries:
                backoff = min(60, 2 ** attempt)
                time.sleep(backoff)
                continue
            raise RuntimeError(f"Invalid JSON response: {response.text}")

        if "error" in data:
            code = data["error"].get("code")
            message = data["error"].get("message")
            if should_retry_error_code(code) and attempt < retries:
                backoff = min(60, 2 ** attempt)
                time.sleep(backoff)
                continue
            raise RuntimeError(f"OpenRouter error {code}: {message}")

        choices = data.get("choices") or []
        if not choices:
            if attempt < retries:
                backoff = min(60, 2 ** attempt)
                time.sleep(backoff)
                continue
            raise RuntimeError("OpenRouter returned no choices.")

        message = choices[0].get("message") or {}
        content = message.get("content")
        if not content:
            if attempt < retries:
                backoff = min(60, 2 ** attempt)
                time.sleep(backoff)
                continue
            raise RuntimeError("OpenRouter returned empty content.")

        return content

    raise RuntimeError("OpenRouter request failed after retries.")


def build_preview(content, preview_chars, compact=True):
    if preview_chars <= 0:
        return ""
    text = (content or "").strip()
    if compact:
        text = " ".join(text.split())
    if len(text) > preview_chars:
        return text[:preview_chars] + "..."
    return text


def build_worker_preview(content, preview_chars, compact=True, max_len=60):
    source_chars = int(preview_chars or 0)
    if source_chars <= 0:
        source_chars = 240
    text = build_preview(content, source_chars, compact)
    if not text:
        text = (content or "").strip()
        if compact:
            text = " ".join(text.split())
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def resolve_outputs_for_pdf(cfg, pdf_path):
    output_root = cfg["output"].get("root")
    if output_root:
        pdf_stem = os.path.splitext(os.path.basename(pdf_path))[0]
        pages_dir = os.path.join(output_root, pdf_stem)
        merged_name = f"{cfg['output']['prefix']}-{pdf_stem}.md"
        markdown_path = os.path.join(output_root, merged_name)
        return markdown_path, pages_dir
    return cfg["output"]["markdown_path"], cfg["output"].get("pages_dir")


def build_page_cache_path(pages_dir, page_number, page_pad):
    if not pages_dir:
        return None
    page_name = f"page_{page_number:0{page_pad}d}.md"
    return os.path.join(pages_dir, page_name)


def worker_process_pages(
    worker_id,
    pdf_path,
    page_numbers,
    worker_total_pages,
    page_start,
    page_end,
    total_pages,
    total_to_process,
    page_pad,
    pages_dir,
    cfg,
    api_key,
    limiter,
    print_lock,
    progress_renderer,
):
    results = {}
    print_progress = bool(cfg["output"].get("print_progress", True))
    preview_chars = int(cfg["output"].get("preview_chars") or 0)
    preview_compact = bool(cfg["output"].get("preview_compact", True))

    with fitz.open(pdf_path) as doc:
        for done_count, page_number in enumerate(page_numbers, start=1):
            page_index = page_number - page_start + 1
            page = doc.load_page(page_number - 1)
            image = render_page_to_image(page, cfg["render"])
            data_url = image_to_data_url(image, cfg["render"])
            messages = build_messages(
                cfg,
                page_number,
                total_pages,
                data_url,
                current_page_end=page_end,
            )

            try:
                content = call_openrouter(cfg, messages, api_key, limiter=limiter)
            except Exception as exc:
                raise RuntimeError(
                    f"Worker {worker_id} failed on page {page_number}: {exc}"
                ) from exc

            results[page_number] = content
            page_path = build_page_cache_path(pages_dir, page_number, page_pad)
            if page_path:
                with open(page_path, "w", encoding="utf-8") as handle:
                    handle.write(content)

            preview = build_worker_preview(
                content,
                preview_chars,
                preview_compact,
                max_len=60,
            )
            if print_progress and progress_renderer is not None:
                progress_renderer.update(worker_id, done_count, worker_total_pages, preview)
            elif print_progress:
                safe_print(
                    print_lock,
                    (
                        f"[{page_index}/{total_to_process}] "
                        f"page {page_number} (ok, worker {worker_id})"
                    ),
                )
                if preview:
                    safe_print(print_lock, f"[preview] {preview}")

    return results


def merge_page_results(cfg, page_start, page_end, results):
    include_separators = bool(cfg["output"].get("include_page_separators"))
    separator_template = cfg["output"].get("page_separator") or "\n\n"
    merged_parts = []

    for page_number in range(page_start, page_end + 1):
        content = results.get(page_number, "")
        if include_separators and merged_parts:
            merged_parts.append(
                safe_format(separator_template, n=page_number, page_number=page_number)
            )
        elif merged_parts:
            merged_parts.append("\n\n")
        merged_parts.append(content)
    return "".join(merged_parts)


def process_one_pdf(pdf_path, cfg, args, api_key, limiter):
    with fitz.open(pdf_path) as doc:
        total_pages = doc.page_count

    page_start = cfg["pdf"]["page_start"]
    page_end = cfg["pdf"]["page_end"] or total_pages

    if page_start > total_pages:
        raise ValueError(
            f"pdf.page_start exceeds total pages ({total_pages}) for {pdf_path}"
        )
    if page_end > total_pages:
        page_end = total_pages

    if args.dry_run:
        print(f"Dry run: pages {page_start} to {page_end} (total {total_pages}) from {pdf_path}")
        return

    output_path, pages_dir = resolve_outputs_for_pdf(cfg, pdf_path)
    if pages_dir:
        os.makedirs(pages_dir, exist_ok=True)
    ensure_parent_dir(output_path)

    page_pad = len(str(page_end))
    total_to_process = page_end - page_start + 1
    print_progress = bool(cfg["output"].get("print_progress", True))
    print_lock = threading.Lock()

    results = {}
    pending_pages = []
    for page_number in range(page_start, page_end + 1):
        page_index = page_number - page_start + 1
        page_path = build_page_cache_path(pages_dir, page_number, page_pad)
        if args.resume and page_path and os.path.exists(page_path) and not args.force:
            with open(page_path, "r", encoding="utf-8") as handle:
                results[page_number] = handle.read()
            if print_progress:
                safe_print(
                    print_lock,
                    f"[{page_index}/{total_to_process}] page {page_number} (cached)",
                )
            continue
        pending_pages.append(page_number)

    workers = int(cfg["concurrency"].get("workers") or 1)
    worker_chunks = split_evenly(pending_pages, workers)
    use_worker_renderer = print_progress and len(worker_chunks) > 1
    worker_totals = [len(chunk) for chunk in worker_chunks]
    progress_renderer = WorkerProgressRenderer(
        worker_totals,
        print_lock=print_lock,
        bar_width=18,
        preview_width=60,
        enabled=use_worker_renderer,
    )
    if use_worker_renderer:
        safe_print(
            print_lock,
            f"Worker progress for {os.path.basename(pdf_path)}:",
        )
        progress_renderer.start()

    if len(worker_chunks) <= 1:
        if worker_chunks:
            worker_results = worker_process_pages(
                1,
                pdf_path,
                worker_chunks[0],
                len(worker_chunks[0]),
                page_start,
                page_end,
                total_pages,
                total_to_process,
                page_pad,
                pages_dir,
                cfg,
                api_key,
                limiter,
                print_lock,
                progress_renderer if use_worker_renderer else None,
            )
            results.update(worker_results)
    else:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(worker_chunks)
        ) as executor:
            futures = []
            for worker_id, page_numbers in enumerate(worker_chunks, start=1):
                futures.append(
                    executor.submit(
                        worker_process_pages,
                        worker_id,
                        pdf_path,
                        page_numbers,
                        len(page_numbers),
                        page_start,
                        page_end,
                        total_pages,
                        total_to_process,
                        page_pad,
                        pages_dir,
                        cfg,
                        api_key,
                        limiter,
                        print_lock,
                        progress_renderer if use_worker_renderer else None,
                    )
                )
            for future in concurrent.futures.as_completed(futures):
                worker_results = future.result()
                results.update(worker_results)

    if use_worker_renderer:
        progress_renderer.finish()

    merged_content = merge_page_results(cfg, page_start, page_end, results)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(merged_content)
    print(f"Saved merged Markdown to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="PDF to Markdown via OpenRouter.")
    parser.add_argument("--config", required=True, help="Path to YAML config.")
    parser.add_argument("--resume", action="store_true", help="Resume from pages_dir.")
    parser.add_argument("--force", action="store_true", help="Overwrite cached pages.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and page range without API calls.",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    validate_config(cfg)

    env_file = cfg["openrouter"].get("env_file")
    if env_file and os.path.exists(env_file):
        load_dotenv(env_file, override=False)

    api_key_env = cfg["openrouter"].get("api_key_env") or "OPENROUTER_API_KEY"
    api_key = os.getenv(api_key_env)
    if not args.dry_run and not api_key:
        raise RuntimeError(f"Missing API key in env var {api_key_env}.")

    limiter = QpsLimiter(cfg["openrouter"].get("rate_limit_qps"))
    pdf_root = cfg["pdf"].get("root")
    if pdf_root:
        pdf_files = list_pdf_files(pdf_root)
        if not pdf_files:
            raise ValueError(f"No PDF files found under pdf.root: {pdf_root}")
        for index, pdf_path in enumerate(pdf_files, start=1):
            print(f"Processing [{index}/{len(pdf_files)}]: {pdf_path}")
            process_one_pdf(pdf_path, cfg, args, api_key, limiter)
    else:
        process_one_pdf(cfg["pdf"]["path"], cfg, args, api_key, limiter)


if __name__ == "__main__":
    main()
