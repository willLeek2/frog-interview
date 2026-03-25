from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR / '.env'


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_env_file(ENV_FILE)
sys.path.insert(0, str(BACKEND_DIR))


def suffix_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {'.png', '.jpg', '.jpeg', '.webp', '.gif'}:
        return suffix
    return '.jpg'


def mime_from_suffix(suffix: str) -> str:
    mapping = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.webp': 'image/webp',
        '.gif': 'image/gif',
    }
    return mapping.get(suffix.lower(), 'image/jpeg')


def extract_content_text(data: dict[str, Any]) -> str:
    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                value = item.get('text')
                if isinstance(value, str):
                    parts.append(value)
        return '\n'.join(parts)
    return ''


def parse_json_content(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith('```'):
        clean = re.sub(r'^```(?:json)?\s*', '', clean, flags=re.IGNORECASE).strip()
        clean = re.sub(r'\s*```$', '', clean).strip()
    start = clean.find('{')
    end = clean.rfind('}')
    if start >= 0 and end > start:
        clean = clean[start : end + 1]
    try:
        data = json.loads(clean)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def build_instruction(company: str, business_line: str, notes: str) -> str:
    metadata_hint = {
        'company': company,
        'business_line': business_line,
        'notes': notes,
    }
    return (
        'You are extracting interview questions from screenshot images.\n'
        'Return only JSON and focus on user-visible interview questions.\n'
        'Keep question wording close to the original text.\n\n'
        'IMPORTANT FILTERING RULES:\n'
        '1. Skip questions that are highly personal to the interviewee (e.g., about their own past internships, '
        'personal projects, or unique experiences that are not generally applicable to other candidates).\n'
        '2. Keep only questions that have general applicability to other interview candidates.\n'
        '3. Mark algorithm/coding questions containing "手撕", "算法题", "coding", "算法", "编程题" as is_algorithm=true.\n\n'
        f'Metadata hint: {json.dumps(metadata_hint, ensure_ascii=False)}'
    )


def build_legacy_response_schema() -> dict[str, Any]:
    return {
        'type': 'json_schema',
        'json_schema': {
            'name': 'experience_extract',
            'strict': True,
            'schema': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'questions': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'additionalProperties': False,
                            'properties': {
                                'question': {'type': 'string'},
                                'topic_tags': {'type': 'array', 'items': {'type': 'string'}},
                                'interview_round': {'type': 'string'},
                                'confidence': {'type': 'number'},
                                'ocr_raw': {'type': 'string'},
                                'is_personal': {'type': 'boolean'},
                                'is_algorithm': {'type': 'boolean'},
                            },
                            'required': [
                                'question',
                                'topic_tags',
                                'interview_round',
                                'confidence',
                                'ocr_raw',
                                'is_personal',
                                'is_algorithm',
                            ],
                        },
                    }
                },
                'required': ['questions'],
            },
        },
    }


def build_ocr_response_schema() -> dict[str, Any]:
    return {
        'type': 'json_schema',
        'json_schema': {
            'name': 'experience_ocr_lines',
            'strict': True,
            'schema': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'lines': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'additionalProperties': False,
                            'properties': {
                                'text': {'type': 'string'},
                            },
                            'required': ['text'],
                        },
                    }
                },
                'required': ['lines'],
            },
        },
    }


def build_extract_response_schema() -> dict[str, Any]:
    return {
        'type': 'json_schema',
        'json_schema': {
            'name': 'experience_question_extract',
            'strict': True,
            'schema': {
                'type': 'object',
                'additionalProperties': False,
                'properties': {
                    'questions': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'additionalProperties': False,
                            'properties': {
                                'question': {'type': 'string'},
                                'topic_tags': {'type': 'array', 'items': {'type': 'string'}},
                                'interview_round': {'type': 'string'},
                                'confidence': {'type': 'number'},
                                'source_excerpt': {'type': 'string'},
                                'is_algorithm': {'type': 'boolean'},
                            },
                            'required': [
                                'question',
                                'topic_tags',
                                'interview_round',
                                'confidence',
                                'source_excerpt',
                                'is_algorithm',
                            ],
                        },
                    }
                },
                'required': ['questions'],
            },
        },
    }


def make_data_uri(image_path: Path) -> str:
    image_bytes = image_path.read_bytes()
    mime = mime_from_suffix(suffix_from_path(image_path))
    return f'data:{mime};base64,{base64.b64encode(image_bytes).decode("utf-8")}'


def image_to_data_uri(image: Image.Image, source_path: Path) -> str:
    suffix = suffix_from_path(source_path)
    mime = mime_from_suffix(suffix)
    fmt = 'PNG' if suffix == '.png' else 'JPEG'
    output = BytesIO()
    if fmt == 'JPEG' and image.mode not in {'RGB', 'L'}:
        image = image.convert('RGB')
    image.save(output, format=fmt)
    return f'data:{mime};base64,{base64.b64encode(output.getvalue()).decode("utf-8")}'


def load_slice_settings() -> tuple[int, int, int]:
    from app.core.config import settings

    return (
        settings.experience_slice_height,
        settings.experience_slice_overlap,
        settings.experience_slice_threshold,
    )


def slice_image(image_path: Path) -> list[Image.Image]:
    from PIL import Image

    slice_height, slice_overlap, slice_threshold = load_slice_settings()
    with Image.open(image_path) as source:
        source.load()
        if source.height <= slice_threshold:
            return [source.copy()]

        slices: list[Image.Image] = []
        step = max(1, slice_height - slice_overlap)
        top = 0
        while top < source.height:
            bottom = min(source.height, top + slice_height)
            slices.append(source.crop((0, top, source.width, bottom)))
            if bottom >= source.height:
                break
            top += step
        return slices


def merge_adjacent_duplicate_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    previous_text = ''
    for item in lines:
        text = str(item.get('text', '')).strip()
        if not text or text == previous_text:
            continue
        merged.append(item)
        previous_text = text
    return merged


def run_ocr(args: argparse.Namespace) -> dict[str, Any]:
    from app.services.openrouter_client import OpenRouterClient

    client = OpenRouterClient()
    provider = client.provider_preferences('vision')
    schema = build_ocr_response_schema()
    instruction = (
        'Transcribe the main visible post content from this interview screenshot.\n'
        'Return JSON only.\n'
        'Preserve reading order.\n'
        'Exclude obvious app chrome like status bar icons, back buttons, share buttons, '
        'bottom navigation, comment input, and engagement counters when possible.\n'
        'Do not interpret or summarize; only transcribe visible lines.'
    )
    merged_lines: list[dict[str, Any]] = []
    slice_results: list[dict[str, Any]] = []
    slices = slice_image(args.image)

    started_at = time.perf_counter()
    for slice_index, slice_image_obj in enumerate(slices):
        response = client.chat_completion(
            model=args.model,
            messages=[
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'text',
                            'text': instruction,
                        },
                        {'type': 'image_url', 'image_url': {'url': image_to_data_uri(slice_image_obj, args.image)}},
                    ],
                }
            ],
            provider=provider,
            extra_body={'response_format': schema},
            purpose='vision',
        )
        raw_content = extract_content_text(response)
        parsed = parse_json_content(raw_content)
        raw_lines = parsed.get('lines', [])
        parsed_lines: list[dict[str, Any]] = []
        if isinstance(raw_lines, list):
            line_index = 0
            for item in raw_lines:
                if not isinstance(item, dict):
                    continue
                text = str(item.get('text', '')).strip()
                if not text:
                    continue
                line = {
                    'text': text,
                    'slice_index': slice_index,
                    'line_index': line_index,
                }
                merged_lines.append(line)
                parsed_lines.append(line)
                line_index += 1
        slice_results.append(
            {
                'slice_index': slice_index,
                'size': {'width': slice_image_obj.width, 'height': slice_image_obj.height},
                'raw_content': raw_content,
                'parsed': {'lines': parsed_lines},
            }
        )
    seconds = time.perf_counter() - started_at
    merged_lines = merge_adjacent_duplicate_lines(merged_lines)
    return {
        'stage': 'ocr',
        'model': args.model,
        'seconds': round(seconds, 3),
        'provider': provider,
        'request_preview': {
            'instruction': instruction,
            'image_path': str(args.image),
            'image_bytes': args.image.stat().st_size,
            'slice_count': len(slices),
            'slice_settings': {
                'slice_height': load_slice_settings()[0],
                'slice_overlap': load_slice_settings()[1],
                'slice_threshold': load_slice_settings()[2],
            },
            'response_format': schema,
        },
        'slice_results': slice_results,
        'raw_content': '\n\n'.join(item['raw_content'] for item in slice_results),
        'parsed': {'lines': merged_lines},
    }


def run_extract(args: argparse.Namespace) -> dict[str, Any]:
    from app.services.openrouter_client import OpenRouterClient

    ocr_result = run_ocr(args)
    lines = ocr_result.get('parsed', {}).get('lines', [])
    if not isinstance(lines, list):
        lines = []
    transcript_lines = [str(item.get('text', '')).strip() for item in lines if isinstance(item, dict)]
    transcript = '\n'.join(line for line in transcript_lines if line)

    client = OpenRouterClient()
    provider = client.provider_preferences('chat')
    schema = build_extract_response_schema()
    metadata_hint = {
        'company': args.company or '',
        'business_line': args.business_line or '',
        'notes': args.notes or '',
        'source_image': args.image.name,
    }
    instruction = (
        'You are extracting interview questions from OCR text copied from a social-media interview post.\n'
        'Return only final interview questions as JSON.\n'
        'You must deduce split/merge internally and output the final cleaned questions only.\n'
        'Skip obvious noise such as hashtags, interaction prompts, posting metadata, durations, and engagement text.\n'
        'Keep only generally applicable interview questions.\n'
        'For design questions, keep enough context so the question remains complete.\n'
        'For algorithm questions, mark is_algorithm=true.\n'
        f'Metadata hint: {json.dumps(metadata_hint, ensure_ascii=False)}\n\n'
        f'OCR transcript:\n{transcript}'
    )

    started_at = time.perf_counter()
    response = client.chat_completion(
        model=args.extract_model or args.model,
        messages=[{'role': 'user', 'content': [{'type': 'text', 'text': instruction}]}],
        provider=provider,
        extra_body={'response_format': schema},
        purpose='chat',
    )
    seconds = time.perf_counter() - started_at
    raw_content = extract_content_text(response)
    parsed = parse_json_content(raw_content)
    return {
        'stage': 'extract',
        'ocr': ocr_result,
        'model': args.extract_model or args.model,
        'seconds': round(seconds, 3),
        'provider': provider,
        'request_preview': {
            'instruction': instruction,
            'ocr_line_count': len(transcript_lines),
            'response_format': schema,
        },
        'raw_content': raw_content,
        'parsed': parsed,
    }


def run_legacy_extract(args: argparse.Namespace) -> dict[str, Any]:
    from app.services.openrouter_client import OpenRouterClient

    client = OpenRouterClient()
    instruction = build_instruction(
        company=args.company or '',
        business_line=args.business_line or '',
        notes=args.notes or '',
    )
    data_uri = make_data_uri(args.image)
    provider = client.provider_preferences('vision')
    schema = build_legacy_response_schema()

    started_at = time.perf_counter()
    response = client.chat_completion(
        model=args.model,
        messages=[
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': instruction},
                    {'type': 'image_url', 'image_url': {'url': data_uri}},
                ],
            }
        ],
        provider=provider,
        extra_body={'response_format': schema},
        purpose='vision',
    )
    seconds = time.perf_counter() - started_at
    raw_content = extract_content_text(response)
    parsed = parse_json_content(raw_content)
    return {
        'stage': 'legacy_extract',
        'model': args.model,
        'seconds': round(seconds, 3),
        'provider': provider,
        'request_preview': {
            'instruction': instruction,
            'image_path': str(args.image),
            'image_bytes': args.image.stat().st_size,
            'response_format': schema,
        },
        'raw_content': raw_content,
        'parsed': parsed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Reproduce coach-app experience extraction requests to OpenRouter.',
    )
    parser.add_argument('--image', required=True, type=Path, help='Path to the local image file')
    parser.add_argument('--model', required=True, help='OpenRouter multimodal model name')
    parser.add_argument(
        '--stage',
        choices=['ocr', 'extract', 'legacy_extract'],
        default='ocr',
        help='Which stage to reproduce',
    )
    parser.add_argument('--extract-model', default='', help='Optional text model for extract stage')
    parser.add_argument('--company', default='', help='Metadata hint: company')
    parser.add_argument('--business-line', default='', help='Metadata hint: business line')
    parser.add_argument('--notes', default='', help='Metadata hint: notes')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not ENV_FILE.exists():
        raise SystemExit(f'.env not found: {ENV_FILE}')
    if not args.image.exists():
        raise SystemExit(f'image not found: {args.image}')
    if not args.image.is_file():
        raise SystemExit(f'image is not a file: {args.image}')
    if not os.environ.get('OPENROUTER_API_KEY'):
        raise SystemExit('OPENROUTER_API_KEY is missing in backend/.env')

    if args.stage == 'ocr':
        result = run_ocr(args)
    elif args.stage == 'extract':
        result = run_extract(args)
    else:
        result = run_legacy_extract(args)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
