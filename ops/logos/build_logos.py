"""Download one small logo per listed company into frontend/public/logos/.

Run monthly by .github/workflows/logos.yml (and by hand). Public data only:
no database, no secrets.

For each stock on the site (GET /api/v1/stocks), the company's website comes
from its nightly snapshot (/snapshot/stock/<SYMBOL>.json, company-profile).
Sources, best first (measured 2026-11-13 on the top 30: favicons alone left
Reliance, HDFC Bank, SBI, L&T, Kotak, Axis, Maruti and ITC at a blurry 16 px):

  0. the NSE logo set in github.com/dharunashokkumar/api.dharun.dev
     (data/logos/nse/NSE_<SYMBOL>.svg, AGPL-3.0 repository), pinned to
     REPO_SHA. Owner decision 2026-11-13: use it wherever it has the company,
     since vector logos are sharper than any icon below. Provenance: that
     repo's tools/scrape_logos.py downloads them from TradingView's logo
     server; the marks are the companies' trademarks. The SVG is rendered to
     a raster WebP here, so no third-party SVG (which could carry script) is
     ever served from the site's origin. These are full-bleed square tiles,
     so they fill the canvas without padding;
  1. the site's own app icon via Google's favicon service, if square-ish and
     at least 64 px (company sites often block other bots; Google's crawler
     already has the icon);
  2. the company's logo on Wikimedia Commons, via Wikidata (P154), matched by
     website or name: free-licensed files, rendered to PNG by Commons;
  3. the app icon again if at least 32 px;
  4. nothing: the site draws an initials badge instead.

Every logo is trimmed, centred on a transparent 96 x 96 canvas and saved as
WebP (a few KB). The site shows it on a light tile, so dark logos stay
visible in dark mode. frontend/src/lib/logoIndex.ts lists the symbols that
have a file, so the site never requests a logo that does not exist.

Usage:  python ops/logos/build_logos.py [--limit N]
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "frontend" / "public" / "logos"
INDEX = ROOT / "frontend" / "src" / "lib" / "logoIndex.ts"
SOURCES = Path(__file__).with_name("sources.json")
API = "https://signaldesk-31gt.onrender.com/api/v1"
SITE = "https://signaldesk.shyamsundar2935.workers.dev"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"
# Wikimedia asks for a descriptive agent.
WIKI_UA = "signaldesk-logos/1.0 (student research project; github.com/shyam-029/SignalDesk)"
SIZE = 96
PAD = 6
# api.dharun.dev commit whose NSE logo files are used (checked 2026-11-13).
REPO_SHA = "6ccdff999869e0ba41db76d894f840515fca0b53"
REPO_RAW = f"https://raw.githubusercontent.com/dharunashokkumar/api.dharun.dev/{REPO_SHA}/data/logos/nse/"


def file_stem(symbol: str) -> str:
    """Symbol -> file name stem. Must match logoFile() in frontend/src/lib/logos.ts."""
    return re.sub(r"[^A-Z0-9-]", "_", symbol.upper())


def _get(url: str, ua: str = BROWSER_UA, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(3_000_000)


def _host(url: str | None) -> str:
    h = (urllib.parse.urlparse(url or "").hostname or "").lower()
    return re.sub(r"^www\d?\.", "", h)


def _norm(name: str | None) -> str:
    return re.sub(
        r"\b(limited|ltd|the|of|and|co|company|corporation)\b|[^a-z0-9]", "", (name or "").lower()
    )


def list_stocks() -> list[tuple[str, str | None, str | None]]:
    """(symbol, website, name) for every listed stock."""
    symbols: list[str] = []
    page = 1
    while True:
        d = json.loads(_get(f"{API}/stocks?page={page}&limit=100&sort=market_cap&direction=desc", timeout=120))
        items = d.get("items") or []
        symbols += [i["symbol"].removesuffix(".NS") for i in items]
        if len(items) < 100:
            break
        page += 1

    def one(sym: str):
        try:
            d = json.loads(_get(f"{SITE}/snapshot/stock/{urllib.parse.quote(sym, safe='')}.json"))
            q = {x["key"][0]: x["data"] for x in d["queries"]}
            return sym, (q.get("company-profile") or {}).get("website"), (q.get("stock-detail") or {}).get("name")
        except Exception:
            return sym, None, None

    with cf.ThreadPoolExecutor(16) as ex:
        return list(ex.map(one, symbols))


_STOP = {"limited", "ltd", "the", "of", "and", "india", "indian", "company", "co", "corporation",
         "industries", "bank", "group", "services", "finance", "financial"}


def _words(name: str | None) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(w) >= 3 and w not in _STOP}


def same_company(our_name: str | None, label: str | None) -> bool:
    """A Wikidata match by website must also share a distinctive name word.

    Websites move between entities: airtel.in is also on the Tata Docomo
    item (merged into Airtel), which would put Docomo's logo on Bharti
    Airtel (seen 2026-11-13). A wrong logo is worse than the initials badge.
    """
    return bool(_words(our_name) & _words(label))


def wikidata_logos() -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    """(Commons logo URL, label) by website host and by normalised name (Indian items)."""
    q = """
    SELECT ?logo ?site ?label WHERE {
      ?item wdt:P17 wd:Q668 ; wdt:P154 ?logo .
      OPTIONAL { ?item wdt:P856 ?site }
      OPTIONAL { ?item rdfs:label ?label FILTER(LANG(?label) = "en") }
    }"""
    url = "https://query.wikidata.org/sparql?format=json&query=" + urllib.parse.quote(q)
    rows = json.loads(_get(url, WIKI_UA, timeout=240))["results"]["bindings"]
    by_host: dict[str, list[tuple[str, str]]] = {}
    by_name: dict[str, tuple[str, str]] = {}
    for b in rows:
        logo = b["logo"]["value"]
        label = b.get("label", {}).get("value", "")
        if "site" in b:
            by_host.setdefault(_host(b["site"]["value"]), []).append((logo, label))
        if label:
            by_name.setdefault(_norm(label), (logo, label))
    return by_host, by_name


def _open(data: bytes) -> Image.Image | None:
    try:
        im = Image.open(io.BytesIO(data))
        if im.format == "ICO":
            im = im.ico.getimage(max(im.ico.sizes()))
        im.load()
        return im.convert("RGBA")
    except Exception:
        return None


def google_icon(site: str) -> Image.Image | None:
    root = "https://" + (urllib.parse.urlparse(site).hostname or "")
    url = (
        "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON"
        "&fallback_opts=TYPE,SIZE,URL"
        f"&url={urllib.parse.quote(root, safe='')}&size=256"
    )
    try:
        return _open(_get(url))
    except Exception:
        return None


def commons_logo(file_url: str) -> Image.Image | None:
    # Special:FilePath with ?width renders SVGs to PNG on Commons' side.
    url = file_url.replace("http://", "https://", 1) + "?width=256"
    try:
        return _open(_get(url, WIKI_UA))
    except Exception:
        return None


def _squareish(im: Image.Image) -> bool:
    w, h = im.size
    return max(w, h) <= 1.35 * min(w, h)


def repo_name(symbol: str) -> str:
    """Symbol -> that repo's file name ("BAJAJ-AUTO" is NSE_BAJAJ_AUTO.svg)."""
    return "NSE_" + symbol.upper().replace("-", "_") + ".svg"


def repo_logo(symbol: str) -> Image.Image | None:
    """The repo's SVG for this symbol, rendered to a 192 px raster, or None."""
    import resvg_py  # only needed here; the rest runs on Pillow alone

    url = REPO_RAW + urllib.parse.quote(repo_name(symbol))
    try:
        svg = _get(url).decode("utf-8")
    except Exception:
        return None
    try:
        png = resvg_py.svg_to_bytes(svg_string=svg, width=2 * SIZE, height=2 * SIZE)
        tile = _open(bytes(png))
    except Exception:
        return None
    if tile is None or _flat(tile):
        return None
    return tile


def _flat(tile: Image.Image) -> bool:
    """A repo tile that is one colour is a placeholder, not a logo.

    Every real tile in that set is a background plus a mark (two or more
    colours); NSE_POWERINDIA.svg was a bare red square (2026-11-13). The
    stock then falls through to the other sources.
    """
    small = tile.convert("RGB").resize((32, 32))
    counts = sorted((c for c, _ in small.getcolors(32 * 32) or []), reverse=True)
    return not counts or sum(counts[1:]) < 0.03 * sum(counts)


def normalise(im: Image.Image, pad: int = PAD) -> Image.Image:
    """Trim transparent borders, fit inside SIZE x SIZE with padding."""
    bbox = im.getchannel("A").getbbox()
    if bbox:
        im = im.crop(bbox)
    inner = SIZE - 2 * pad
    im.thumbnail((inner, inner), Image.LANCZOS)
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(im, ((SIZE - im.width) // 2, (SIZE - im.height) // 2), im)
    return canvas


def pick(site: str | None, commons: str | None) -> tuple[Image.Image | None, str]:
    icon = google_icon(site) if site else None
    if icon is not None and min(icon.size) >= 64 and _squareish(icon):
        return icon, "icon"
    if commons:
        logo = commons_logo(commons)
        if logo is not None and min(logo.size) >= 32:
            return logo, "commons"
    if icon is not None and min(icon.size) >= 32 and _squareish(icon):
        return icon, "small-icon"
    return None, "none"


# Hand-checked: symbols whose fetched image (from sources 1-3; the repo set
# is used first) is not their logo. They get the initials badge. Automatic "blank" and "photo" filters were tried on
# 2026-11-13 and rejected ~30 real logos (flat or JPEG-compressed marks), so
# this list is curated by looking at the images instead:
#   CYIENT      a plain grey disc
#   MIDHANI     a photograph of a building (Commons "logo" field)
#   UNIVCABLES  a gambling-site banner served as the site's icon
BLOCKED = set(json.loads((Path(__file__).with_name("blocked.json")).read_text(encoding="utf-8")))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only the first N stocks (testing)")
    args = ap.parse_args(argv)

    stocks = list_stocks()
    if args.limit:
        stocks = stocks[: args.limit]
    by_host, by_name = wikidata_logos()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    def one(row):
        sym, site, name = row
        tile = repo_logo(sym)
        if tile is not None:
            normalise(tile, pad=0).save(OUT_DIR / f"{file_stem(sym)}.webp", "WEBP", quality=90, method=6)
            return sym, "repo"
        if sym in BLOCKED:
            return sym, "blocked"
        commons = None
        for logo, label in (by_host.get(_host(site), []) if site else []):
            if same_company(name, label):
                commons = logo
                break
        if commons is None and _norm(name) in by_name:
            commons = by_name[_norm(name)][0]
        im, source = pick(site, commons)
        if im is None:
            return sym, source
        normalise(im).save(OUT_DIR / f"{file_stem(sym)}.webp", "WEBP", quality=88, method=6)
        return sym, source

    with cf.ThreadPoolExecutor(12) as ex:
        results = list(ex.map(one, stocks))

    have = sorted(s for s, src in results if src not in ("none", "blocked"))
    if args.limit:
        print(f"test run: {len(have)} of {len(results)}; index and old files left untouched")
        return 0
    # Remove files of stocks that left the list or lost their logo.
    keep = {f"{file_stem(s)}.webp" for s in have}
    for f in OUT_DIR.glob("*.webp"):
        if f.name not in keep:
            f.unlink()
    lines = "\n".join(f"  {json.dumps(s)}," for s in have)
    INDEX.write_text(
        "// Generated by ops/logos/build_logos.py; do not edit by hand.\n"
        "// Symbols with a logo file in public/logos/ (see lib/logos.ts).\n"
        f"export const LOGO_SYMBOLS: readonly string[] = [\n{lines}\n];\n",
        encoding="utf-8",
    )

    # Where each logo came from, for provenance and later checks.
    SOURCES.write_text(
        json.dumps(dict(sorted(results)), indent=0, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    counts: dict[str, int] = {}
    for _, src in results:
        counts[src] = counts.get(src, 0) + 1
    print(f"logos: {len(have)} of {len(results)} stocks; by source {counts}")
    return 0 if len(have) >= len(results) // 2 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
