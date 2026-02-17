# OpenRouter PDF to Markdown (YAML driven)

This tool renders PDF pages to images and sends them to an OpenRouter multimodal
model for OCR-to-Markdown transcription.

It now supports:

- Batch mode: iterate all PDFs under `pdf.root` (first level, non-recursive)
- Serial processing across PDFs
- Multi-threaded processing inside each single PDF (`concurrency.workers`)
- Compact per-worker progress bar rendering in multi-thread mode
- Unified output root layout per PDF

## Requirements

- Conda environment: `alphafrog`
- Python packages (install with `requirements.txt`)
- OpenRouter API key in an environment variable or a `.env` file

## Install

```bash
conda activate alphafrog
pip install -r xiaolin-java/tools/openrouter_pdf2md/requirements.txt
```

## Configure

Copy and edit the example:

```bash
cp xiaolin-java/tools/openrouter_pdf2md/config.example.yml ./config.yml
```

Key fields:

- `pdf.root`: PDF directory for batch mode (preferred)
- `pdf.path`: single PDF input (legacy compatible mode)
- `pdf.page_start` / `pdf.page_end`: per-PDF page range
- `output.root`: output root directory
- `output.prefix`: merged markdown file name prefix
- `concurrency.workers`: thread count for pages within one PDF
- `openrouter.env_file`: optional `.env` file path (relative to YAML)
- `openrouter.model`: model slug (must support image input)
- `openrouter.provider`: provider routing preferences (passed through as-is)

## Output layout (batch mode)

Assume:

- `output.root: ./output`
- `output.prefix: out`
- input file: `banana.pdf`

Generated outputs:

- `./output/out-banana.md` (merged markdown for this PDF)
- `./output/banana/page_01.md`, `page_02.md`, ... (per-page markdown cache)

## Run

```bash
export OPENROUTER_API_KEY="your_key"
python xiaolin-java/tools/openrouter_pdf2md/pdf_to_markdown.py --config ./config.yml
```

Optional `.env` (placed next to your YAML, or set `openrouter.env_file`):

```text
OPENROUTER_API_KEY=your_key
```

Useful flags:

- `--resume`: skip pages already saved in each PDF's page cache directory
- `--force`: overwrite cached pages when used with `--resume`
- `--dry-run`: validate config and print effective page ranges without API calls

In multi-thread mode, each worker gets one dedicated progress line:

- left: progress bar
- middle: numeric progress (for example `1/3`)
- right: latest OCR preview text (truncated to 60 chars)
- rendering: powered by `rich` progress components

## Smoke test (1-2 pages)

1. Set `pdf.page_start: 1` and `pdf.page_end: 2`.
2. Put 1-2 small PDFs under `pdf.root`.
3. Run the script and check:
   - output contains only Markdown (no extra explanations)
   - headers/footers/sidebars are excluded
   - lists/headings/code blocks are preserved
   - output layout matches the `output.root` structure above

## Notes

- Image inputs use `data:image/jpeg;base64,...` or `data:image/png;base64,...`
  inside the Chat Completions `messages` array.
- Provider routing is configured via the `provider` object in the request body.
