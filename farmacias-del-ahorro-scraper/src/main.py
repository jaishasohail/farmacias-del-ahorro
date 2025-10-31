pythonpython
import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

from scraper.request_handler import RequestHandler
from scraper.fahorro_parser import FahorroParser
from exporters.json_exporter import JsonExporter
from scraper.utils import (
 load_json,
 batched,
 ensure_dir,
 setup_logging,
 guess_url_kind,
)

APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = APP_ROOT / "data"
DEFAULT_INPUT = DEFAULT_DATA_DIR / "input_urls.txt"
DEFAULT_OUTPUT = DEFAULT_DATA_DIR / "output_sample.json"
DEFAULT_SETTINGS = APP_ROOT / "src" / "config" / "settings.json"

def read_input_urls(path: Path) -> List[str]:
 if not path.exists():
 raise FileNotFoundError(f"Input file not found: {path}")
 urls: List[str] = []
 with path.open("r", encoding="utf-8") as f:
 for line in f:
 line = line.strip()
 if not line or line.startswith("#"):
 continue
 urls.append(line)
 unique = list(dict.fromkeys(urls)) # stable dedupe
 return unique

def run(urls: List[str], output_path: Path, settings_path: Path) -> None:
 ensure_dir(output_path.parent)

 settings = load_json(settings_path)
 logger = setup_logging(level=settings.get("log_level", "INFO"))

 rh = RequestHandler(
 timeout=settings.get("timeout", 15),
 max_retries=settings.get("max_retries", 3),
 backoff_base=settings.get("backoff_base", 0.5),
 rotate_user_agents=settings.get("rotate_user_agents", True),
 default_headers=settings.get("headers", {}),
 request_delay=settings.get("request_delay", 0.0),
 )

 parser = FahorroParser(rh, logger=logger)

 all_products: List[Dict[str, Any]] = []
 for batch in batched(urls, settings.get("concurrency_batch", 8)):
 for url in batch:
 kind = guess_url_kind(url)
 logger.debug(f"Processing URL as {kind}: {url}")
 try:
 if kind == "product":
 prod = parser.parse_product(url)
 if prod:
 all_products.append(prod)
 else:
 products = parser.parse_listing(url)
 all_products.extend(products)
 except Exception as e:
 logger.exception(f"Failed to parse {url}: {e}")

 # Deduplicate by URL or title
 dedup: Dict[str, Dict[str, Any]] = {}
 for p in all_products:
 key = p.get("url") or p.get("title")
 if key and key not in dedup:
 dedup[key] = p
 final_list = list(dedup.values())

 JsonExporter.to_file(final_list, output_path)
 logger.info(f"Saved {len(final_list)} products to {output_path}")

def parse_args(argv: List[str]) -> argparse.Namespace:
 p = argparse.ArgumentParser(
 description="Farmacias del Ahorro Scraper - extract product data into JSON."
 )
 p.add_argument(
 "-i",
 "--input",
 type=Path,
 default=DEFAULT_INPUT,
 help=f"Path to input URLs file (default: {DEFAULT_INPUT})",
 )
 p.add_argument(
 "-o",
 "--output",
 type=Path,
 default=DEFAULT_OUTPUT,
 help=f"Path to output JSON file (default: {DEFAULT_OUTPUT})",
 )
 p.add_argument(
 "-s",
 "--settings",
 type=Path,
 default=DEFAULT_SETTINGS,
 help=f"Path to settings JSON (default: {DEFAULT_SETTINGS})",
 )
 p.add_argument(
 "url",
 nargs="*",
 help="Optional one-off URLs to scrape (overrides --input if provided).",
 )
 return p.parse_args(argv)

if __name__ == "__main__":
 args = parse_args(sys.argv[1:])
 input_urls: List[str]
 if args.url:
 input_urls = args.url
 else:
 input_urls = read_input_urls(args.input)

 run(input_urls, args.output, args.settings)