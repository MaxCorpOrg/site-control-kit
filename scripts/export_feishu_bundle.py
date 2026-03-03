#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from playwright.sync_api import sync_playwright

SEED_RAW_MD = Path('/home/max/feishu_export/feishu_wiki_raw.md')
OUT_DIR = Path('/home/max/feishu_export')
RAW_PAGES_DIR = OUT_DIR / 'pages_raw'
RU_PAGES_DIR = OUT_DIR / 'pages_ru'
BUNDLE_RU_MD = OUT_DIR / 'feishu_bundle_ru.md'
BUNDLE_RAW_MD = OUT_DIR / 'feishu_bundle_raw.md'
META_JSON = OUT_DIR / 'bundle_meta.json'

TRANSLATE_CHUNK = 1100
TRANSLATE_DELAY_SEC = 0.08
TRANSLATE_MAX_CHARS_PER_PAGE = 24000


@dataclass
class PageResult:
    index: int
    url: str
    title: str
    title_ru: str
    text_chars: int
    translated_chars: int
    text_truncated: bool
    status: str
    error: str | None
    raw_file: str
    ru_file: str


def slugify(value: str, max_len: int = 80) -> str:
    v = value.strip().lower()
    v = re.sub(r'https?://', '', v)
    v = re.sub(r'[^a-z0-9\u0400-\u04ff\u4e00-\u9fff]+', '-', v)
    v = re.sub(r'-+', '-', v).strip('-')
    if not v:
        v = 'page'
    return v[:max_len]


def read_links_from_seed(md_path: Path) -> list[str]:
    raw = md_path.read_text(encoding='utf-8')
    links = re.findall(r'\[[^\]]*\]\(([^)]+)\)', raw)

    out = []
    seen = set()
    for link in links:
        link = link.strip()
        if not link or link.startswith('#'):
            continue
        if not (link.startswith('http://') or link.startswith('https://')):
            continue
        key = link
        if key in seen:
            continue
        seen.add(key)
        out.append(link)
    return out


def normalize_ws(text: str) -> str:
    lines = [ln.rstrip() for ln in text.replace('\r\n', '\n').replace('\r', '\n').split('\n')]
    cleaned = []
    prev_blank = False
    for ln in lines:
        if ln.strip() == '':
            if not prev_blank:
                cleaned.append('')
            prev_blank = True
        else:
            cleaned.append(ln)
            prev_blank = False
    return '\n'.join(cleaned).strip()


def split_chunks(text: str, n: int) -> Iterable[str]:
    i = 0
    while i < len(text):
        yield text[i:i+n]
        i += n


def translate_google(text: str, src: str = 'auto', dst: str = 'ru') -> str:
    if not text.strip():
        return text

    result = []
    for piece in split_chunks(text, TRANSLATE_CHUNK):
        q = urllib.parse.quote(piece)
        url = (
            'https://translate.googleapis.com/translate_a/single'
            f'?client=gtx&sl={src}&tl={dst}&dt=t&q={q}'
        )
        try:
            with urllib.request.urlopen(url, timeout=90) as resp:
                payload = json.loads(resp.read().decode('utf-8'))
            translated = ''.join(item[0] for item in payload[0] if item and item[0])
            result.append(translated)
        except Exception:
            # Fallback: keep original chunk if translation fails.
            result.append(piece)
        time.sleep(TRANSLATE_DELAY_SEC)

    return ''.join(result)


def collect_page(page, url: str) -> tuple[str, str, bool]:
    page.goto(url, wait_until='domcontentloaded', timeout=120000)
    page.wait_for_timeout(3500)

    # Lazy-loading stabilization by scrolling down then up.
    stable = 0
    prev = 0
    for _ in range(70):
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        page.wait_for_timeout(350)
        cur = len(page.inner_text('body'))
        if cur <= prev + 3:
            stable += 1
        else:
            stable = 0
            prev = cur
        if stable >= 5:
            break

    page.evaluate('window.scrollTo(0, 0)')
    page.wait_for_timeout(250)

    title = (page.title() or '').strip() or 'Untitled'
    text = normalize_ws(page.inner_text('body'))

    truncated = False
    if len(text) > TRANSLATE_MAX_CHARS_PER_PAGE:
        text = text[:TRANSLATE_MAX_CHARS_PER_PAGE]
        truncated = True

    return title, text, truncated


def write_page_files(idx: int, url: str, title: str, title_ru: str, text: str, text_ru: str, truncated: bool) -> tuple[Path, Path]:
    slug = slugify(title if title else url)
    raw_file = RAW_PAGES_DIR / f'{idx:02d}_{slug}.md'
    ru_file = RU_PAGES_DIR / f'{idx:02d}_{slug}.md'

    trunc_line = '\n- Note: text was truncated for processing.' if truncated else ''
    raw_file.write_text(
        f"# {title}\n\n"
        f"- URL: {url}\n"
        f"- Exported: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC\n"
        f"- Chars: {len(text)}{trunc_line}\n\n"
        f"## Raw text\n\n"
        f"```text\n{text}\n```\n",
        encoding='utf-8',
    )

    ru_file.write_text(
        f"# {title_ru}\n\n"
        f"- URL: {url}\n"
        f"- Экспорт: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC\n"
        f"- Символов: {len(text_ru)}{trunc_line}\n\n"
        f"## Текст на русском\n\n"
        f"```text\n{text_ru}\n```\n",
        encoding='utf-8',
    )

    return raw_file, ru_file


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_PAGES_DIR.mkdir(parents=True, exist_ok=True)
    RU_PAGES_DIR.mkdir(parents=True, exist_ok=True)

    links = read_links_from_seed(SEED_RAW_MD)

    results: list[PageResult] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path='/usr/bin/google-chrome',
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage'],
        )
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()

        for idx, url in enumerate(links, start=1):
            status = 'ok'
            error = None
            title = ''
            title_ru = ''
            text = ''
            text_ru = ''
            truncated = False
            raw_file = RAW_PAGES_DIR / f'{idx:02d}_failed.md'
            ru_file = RU_PAGES_DIR / f'{idx:02d}_failed.md'

            try:
                title, text, truncated = collect_page(page, url)
                if not text:
                    raise RuntimeError('empty_text')

                title_ru = translate_google(title)
                text_ru = translate_google(text)
                raw_file, ru_file = write_page_files(idx, url, title, title_ru, text, text_ru, truncated)
            except Exception as exc:
                status = 'error'
                error = str(exc)
                fail_text = f"# Export Error\n\n- URL: {url}\n- Error: {error}\n"
                raw_file.write_text(fail_text, encoding='utf-8')
                ru_file.write_text(f"# Ошибка экспорта\n\n- URL: {url}\n- Ошибка: {error}\n", encoding='utf-8')

            results.append(
                PageResult(
                    index=idx,
                    url=url,
                    title=title,
                    title_ru=title_ru,
                    text_chars=len(text),
                    translated_chars=len(text_ru),
                    text_truncated=truncated,
                    status=status,
                    error=error,
                    raw_file=str(raw_file),
                    ru_file=str(ru_file),
                )
            )

        context.close()
        browser.close()

    # Build bundles
    toc_ru = []
    toc_raw = []
    body_ru = []
    body_raw = []

    for r in results:
        name = r.title_ru or r.title or r.url
        rel_ru = Path(r.ru_file).name
        rel_raw = Path(r.raw_file).name
        toc_ru.append(f"- {r.index}. [{name}](pages_ru/{rel_ru})")
        toc_raw.append(f"- {r.index}. [{r.title or r.url}](pages_raw/{rel_raw})")

        ru_content = Path(r.ru_file).read_text(encoding='utf-8')
        raw_content = Path(r.raw_file).read_text(encoding='utf-8')

        body_ru.append(f"\n\n---\n\n## Раздел {r.index}: {name}\n\n{ru_content}\n")
        body_raw.append(f"\n\n---\n\n## Section {r.index}: {r.title or r.url}\n\n{raw_content}\n")

    BUNDLE_RU_MD.write_text(
        "# Feishu Wiki: полный сборник на русском\n\n"
        f"- Seed page: https://my.feishu.cn/wiki/F5krwD16viZoF0kKkvDcrZNYnhb\n"
        f"- Total links processed: {len(results)}\n"
        f"- Generated: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC\n\n"
        "## Оглавление\n\n"
        + "\n".join(toc_ru)
        + "\n\n## Содержимое\n"
        + "".join(body_ru),
        encoding='utf-8',
    )

    BUNDLE_RAW_MD.write_text(
        "# Feishu Wiki: raw bundle\n\n"
        f"- Seed page: https://my.feishu.cn/wiki/F5krwD16viZoF0kKkvDcrZNYnhb\n"
        f"- Total links processed: {len(results)}\n"
        f"- Generated: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC\n\n"
        "## Table of contents\n\n"
        + "\n".join(toc_raw)
        + "\n\n## Content\n"
        + "".join(body_raw),
        encoding='utf-8',
    )

    meta = {
        'seed_md': str(SEED_RAW_MD),
        'out_dir': str(OUT_DIR),
        'pages_raw_dir': str(RAW_PAGES_DIR),
        'pages_ru_dir': str(RU_PAGES_DIR),
        'bundle_ru': str(BUNDLE_RU_MD),
        'bundle_raw': str(BUNDLE_RAW_MD),
        'results': [asdict(r) for r in results],
        'ok_count': sum(1 for r in results if r.status == 'ok'),
        'error_count': sum(1 for r in results if r.status != 'ok'),
        'timestamp_utc': time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()),
    }
    META_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps({'ok_count': meta['ok_count'], 'error_count': meta['error_count'], 'bundle_ru': str(BUNDLE_RU_MD)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
