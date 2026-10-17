#!/usr/bin/env python3
"""Import original Bal's Sound Garden cover/gallery images from its official itch.io page.

Python standard library only. Updates README and Pages gallery after validated
image downloads succeed. Never changes game source, releases, or GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.parse import urlparse, urljoin, unquote
from urllib.request import Request, urlopen

GAMES = {'Bals-Sound-Garden': 'bals-sound-garden'}
HOSTS = {'img.itch.zone', 'img.itch.io'}
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'
MAX_FILE = 35 * 1024 * 1024
MAX_IMAGES = 80
MEDIA_SUFFIXES = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.avif'}


def normalized_image_url(value: str, base: str) -> str | None:
    if not value:
        return None
    value = html.unescape(value).strip().strip('"\'')
    value = value.replace('\\/', '/')
    if value.startswith('//'):
        value = 'https:' + value
    elif value.startswith('/'):
        value = urljoin(base, value)
    parsed = urlparse(value)
    if parsed.scheme != 'https' or (parsed.hostname or '').lower() not in HOSTS:
        return None
    return value


def full_size(url: str) -> str:
    """Prefer original-size itch image, unless the URL is not in its thumbnail scheme."""
    return re.sub(r'/(?:\d+x\d+|\d+x|x\d+)(?:%23[^/]*)?/', '/original/', url, count=1)


class PageGallery(HTMLParser):
    def __init__(self, page_url: str):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.stack: list[tuple[str, bool, bool]] = []
        self.gallery: list[str] = []
        self.covers: list[str] = []
        self.gallery_anchors: list[str] = []
        self.all_visible: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): v or '' for k, v in attrs}
        css = (a.get('class', '') + ' ' + a.get('id', '')).lower()
        ancestor_gallery = any(g for _, g, _ in self.stack)
        ancestor_cover = any(c for _, _, c in self.stack)
        # itch.io uses screenshot_list, screenshot, screenshot_link and game_cover_image.
        is_gallery = ancestor_gallery or any(t in css for t in ('screenshot', 'screenshot_list', 'gallery', 'lightbox'))
        is_cover = ancestor_cover or any(t in css for t in ('game_cover', 'cover_image', 'cover_img'))

        if tag == 'meta' and a.get('property', '').lower() in ('og:image', 'twitter:image'):
            u = normalized_image_url(a.get('content', ''), self.page_url)
            if u:
                self.covers.append(u)

        values = [a.get(k, '') for k in ('href', 'src', 'data-src', 'data-original', 'data-full', 'data-href', 'data-screenshot', 'data-image')]
        for item in values:
            u = normalized_image_url(item, self.page_url)
            if not u:
                continue
            if tag in ('a', 'img', 'source', 'meta'):
                self.all_visible.append(u)
            if is_gallery:
                self.gallery.append(u)
                if tag == 'a':
                    self.gallery_anchors.append(u)
            if is_cover:
                self.covers.append(u)
        if tag not in {'br', 'img', 'meta', 'link', 'input', 'hr', 'source', 'wbr', 'area'}:
            self.stack.append((tag, is_gallery, is_cover))

    def handle_endtag(self, tag: str) -> None:
        if tag in {'br', 'img', 'meta', 'link', 'input', 'hr', 'source', 'wbr', 'area'}:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break


def image_key(url: str) -> str:
    # Itch images share the encoded source-id part of the URL across size variants.
    path = urlparse(url).path.split('/')
    return path[1] if len(path) >= 3 else url


def choose_gallery(page: PageGallery) -> tuple[list[tuple[str, str]], list[str]]:
    # The full-size gallery anchor takes precedence over embedded thumbnails.
    ranked = [(0, u) for u in page.gallery_anchors] + [(1, u) for u in page.gallery]
    covers = [(0, u) for u in page.covers]
    unique: dict[str, tuple[int, str]] = {}
    for rank, u in ranked:
        u = full_size(u)
        key = image_key(u)
        old = unique.get(key)
        if old is None or rank < old[0]:
            unique[key] = (rank, u)
    cover = []
    for rank, u in covers:
        u = full_size(u)
        if image_key(u) not in {image_key(x) for x in cover}:
            cover.append(u)
    shots = [u for _, u in unique.values() if image_key(u) not in {image_key(x) for x in cover}]
    return ([('Cover', u) for u in cover[:1]] + [('Screenshot', u) for u in shots]), page.all_visible


def download(url: str, referer: str, max_bytes: int = MAX_FILE) -> bytes:
    req = Request(url, headers={'User-Agent': UA, 'Referer': referer, 'Accept': 'image/avif,image/webp,image/png,image/jpeg,image/gif,*/*;q=0.8'})
    with urlopen(req, timeout=40) as r:
        size_header = r.headers.get('Content-Length')
        if size_header and int(size_header) > max_bytes:
            raise RuntimeError(f'Image too large: {url}')
        data = r.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise RuntimeError(f'Image exceeded safety limit: {url}')
    return data


def extension(data: bytes) -> str:
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return '.png'
    if data.startswith(b'\xff\xd8\xff'): return '.jpg'
    if data.startswith((b'GIF87a', b'GIF89a')): return '.gif'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP': return '.webp'
    if data[4:12] in (b'ftypavif', b'ftypavis'): return '.avif'
    raise RuntimeError('Downloaded content is not a supported image')


def between_markers(text: str, begin: str, end: str, replacement: str) -> str:
    i = text.find(begin)
    j = text.find(end)
    if i < 0 or j < 0 or j <= i:
        raise RuntimeError(f'Missing document gallery markers: {begin}, {end}')
    return text[:i] + begin + "\n" + replacement.rstrip() + "\n" + text[j:]


def update_documents(repo: Path, entries: list[tuple[str, str]], page_url: str) -> None:
    # Write both documents only after all images are downloaded and verified.
    readme = repo / 'README.md'
    website = repo / 'docs' / 'index.html'
    md = readme.read_text(encoding='utf-8')
    site = website.read_text(encoding='utf-8')
    lines = [
        '## Screenshots — official itch.io gallery',
        '',
        f'These are the original images hosted on the [official itch.io page]({page_url}).',
        'The image sources and SHA-256 checksums are recorded in [`docs/itch-gallery/SOURCES.json`](docs/itch-gallery/SOURCES.json).',
        '',
    ]
    for typ, filename in entries:
        label = 'Cover art' if typ == 'Cover' else 'Gameplay screenshot'
        lines.append(f'![{label}](docs/itch-gallery/{filename})')
        lines.append('')
    new_md = between_markers(md, '<!-- ITCH_GALLERY_START -->', '<!-- ITCH_GALLERY_END -->', '\n'.join(lines))

    import html as html_module
    figures = []
    for idx, (typ, filename) in enumerate(entries, 1):
        label = 'Cover art' if typ == 'Cover' else f'Screenshot {idx - int(entries[0][0] == "Cover")}'
        relative = 'itch-gallery/' + filename
        figures.append(
            f'        <a href="{relative}" target="_blank" rel="noopener noreferrer">'
            f'<figure><img src="{relative}" loading="lazy" alt="Bal\'s Sound Garden — {html_module.escape(label)}">'
            f'<figcaption>{html_module.escape(label)}</figcaption></figure></a>'
        )
    gallery = (
        '    <section class="itch-gallery" id="screenshots" aria-labelledby="itch-gallery-title">\n'
        '      <div class="itch-gallery-header">\n'
        '        <p class="eyebrow">Original itch.io imagery</p>\n'
        '        <h2 id="itch-gallery-title">Screenshots from the game</h2>\n'
        '        <p>These images are sourced from the official Bal\'s Sound Garden itch.io page. Select one to view the full-size original.</p>\n'
        '      </div>\n'
        '      <div class="itch-gallery-grid">\n'
        + '\n'.join(figures) + '\n'
        '      </div>\n'
        '    </section>'
    )
    new_site = between_markers(site, '<!-- ITCH_GALLERY_START -->', '<!-- ITCH_GALLERY_END -->', gallery)
    # Both documents are prepared before either is written.
    readme.write_text(new_md, encoding='utf-8')
    website.write_text(new_site, encoding='utf-8')


def process(root: Path, game: str, slug: str) -> bool:
    page_url = f'https://abprojects.itch.io/{slug}'
    repo = root
    if not (repo / 'main.py').is_file() or not (repo / 'README.md').is_file() or not (repo / 'docs/index.html').is_file():
        raise RuntimeError(f'Expected Bal source repository with main.py, README.md and docs/index.html: {repo}')
    req = Request(page_url, headers={'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml'})
    with urlopen(req, timeout=35) as r:
        final = r.geturl()
        if urlparse(final).hostname != 'abprojects.itch.io':
            raise RuntimeError(f'Unexpected page redirect: {final}')
        raw = r.read(12 * 1024 * 1024 + 1)
    if len(raw) > 12 * 1024 * 1024:
        raise RuntimeError('Page HTML unexpectedly large')
    parser = PageGallery(page_url)
    parser.feed(raw.decode('utf-8', errors='replace'))
    imgs, visible = choose_gallery(parser)
    if not imgs:
        print(f'WARNING {game}: no verified cover/gallery images found in page HTML; README unchanged.')
        print('  Visible itch CDN images (for investigation):', len(set(visible)))
        return False
    if len(imgs) > MAX_IMAGES:
        raise RuntimeError('Unexpectedly many images; stopping rather than downloading unrelated assets')
    print(f'\n{game}: found {len(imgs)} original image(s) ({sum(k=="Screenshot" for k,_ in imgs)} gallery screenshots).')
    with tempfile.TemporaryDirectory(prefix=f'{slug}-') as tmp:
        temp = Path(tmp)
        entries: list[tuple[str, str]] = []
        sources: list[dict[str, str]] = []
        seen_hashes: set[str] = set()
        for typ, url in imgs:
            try:
                data = download(url, page_url)
            except Exception as e:
                # Some original paths can be unavailable even though the resized page image works.
                fallback = next((u for u in parser.all_visible if image_key(u) == image_key(url) and u != url), None)
                if not fallback:
                    raise RuntimeError(f'Could not fetch a page image: {url} ({e})') from e
                url = fallback
                data = download(url, page_url)
            checksum = hashlib.sha256(data).hexdigest()
            if checksum in seen_hashes:
                continue
            seen_hashes.add(checksum)
            number = len(entries) + 1
            suffix = extension(data)
            filename = f'{number:02d}-{typ.lower()}{suffix}'
            (temp / filename).write_bytes(data)
            entries.append((f'{typ} {number}', filename))
            sources.append({'file': filename, 'source': url, 'sha256': checksum, 'bytes': str(len(data))})
            print(f'  {filename} — {len(data):,} bytes')
        if not entries:
            print('No valid images were retrieved. No changes made.')
            return False
        destination = repo/'docs'/'itch-gallery'
        replacement = repo/'docs'/'itch-gallery.NEW'
        if replacement.exists():
            shutil.rmtree(replacement)
        shutil.copytree(temp, replacement)
        (replacement / 'SOURCES.json').write_text(json.dumps({'source_page': page_url, 'images': sources}, indent=2) + '\n', encoding='utf-8')
        # README is only altered after downloads succeed.
        if destination.exists():
            shutil.rmtree(destination)
        replacement.rename(destination)
        update_documents(repo, entries, page_url)
        print('  Updated README.md and docs/index.html with original itch.io imagery')
        return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parent,
                    help="Bal's Sound Garden repository root")
    args = ap.parse_args()
    successes = 0
    failures = 0
    for name, slug in GAMES.items():
        try:
            successes += int(process(args.root, name, slug))
        except Exception as e:
            failures += 1
            print(f'ERROR {name}: {e}', file=sys.stderr)
    print(f'\nSummary: {successes} gallery imports, {failures} errors. No GitHub upload was performed.')
    return 0 if successes == 1 and failures == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
