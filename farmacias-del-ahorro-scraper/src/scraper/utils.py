pythonpython
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Optional

def setup_logging(level: str = "INFO") -> logging.Logger:
 logger = logging.getLogger("fahorro_scraper")
 if not logger.handlers:
 logger.setLevel(getattr(logging, level.upper(), logging.INFO))
 ch = logging.StreamHandler()
 fmt = logging.Formatter("[%(levelname)s] %(message)s")
 ch.setFormatter(fmt)
 logger.addHandler(ch)
 return logger

def load_json(path: Path) -> Dict[str, Any]:
 if not path.exists():
 return {}
 with path.open("r", encoding="utf-8") as f:
 return json.load(f)

def ensure_dir(path: Path) -> None:
 os.makedirs(path, exist_ok=True)

def batched(iterable: Iterable[Any], n: int) -> Generator[List[Any], None, None]:
 batch: List[Any] = []
 for item in iterable:
 batch.append(item)
 if len(batch) >= n:
 yield batch
 batch = []
 if batch:
 yield batch

_CURRENCY_RE = re.compile(
 r"(?P(?:\d{1,3}(?:[ ,]\d{3})+)|\d+)(?:[.,](\d{1,2}))?"
)

def normalize_price(value: Optional[str]) -> Optional[float]:
 """
 Convert a price string like "$1,234.56" or "1 234,56" to a float.
 Returns None if parsing fails.
 """
 if value is None:
 return None
 s = str(value).strip()
 if not s:
 return None
 # Remove currency symbols and non-numeric prefixes
 s = s.replace("MXN", "").replace("$", "").replace("USD", "")
 s = s.replace("€", "").replace("Precio", "").replace(":", " ")
 s = re.sub(r"[^\d,.\s]", " ", s)
 s = re.sub(r"\s+", " ", s).strip()

 m = _CURRENCY_RE.search(s)
 if not m:
 try:
 return float(s)
 except Exception:
 return None

 num = m.group("num")
 # Decide if comma is decimal separator by presence of dot
 if "," in num and "." not in num:
 num = num.replace(".", "").replace(",", ".")
 else:
 num = num.replace(",", "")
 try:
 return float(num)
 except Exception:
 return None

def normalize_whitespace(text: Optional[str]) -> Optional[str]:
 if text is None:
 return None
 return re.sub(r"\s+", " ", text).strip()

def is_product_like_url(url: str) -> bool:
 if not url:
 return False
 return bool(re.search(r"/(producto|product|sku|item|p)/", url, re.I))

def extract_first_text(elems) -> Optional[str]:
 if not elems:
 return None
 for e in elems:
 if getattr(e, "name", None) == "meta":
 content = e.get("content")
 if content:
 return content.strip()
 else:
 txt = e.get_text(" ", strip=True)
 if txt:
 return txt
 return None

def guess_url_kind(url: str) -> str:
 """
 Return 'product' or 'listing' based on light heuristics.
 """
 if is_product_like_url(url) or re.search(r"/(detalle|detalle-producto)/", url, re.I):
 return "product"
 if re.search(r"(search|buscar|busqueda|categoria|category|catalogo)", url, re.I):
 return "listing"
 # Unknown: treat as listing and try to discover product links
 return "listing"