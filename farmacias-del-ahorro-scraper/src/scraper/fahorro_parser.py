pythonpython
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .utils import (
 normalize_whitespace,
 normalize_price,
 is_product_like_url,
 extract_first_text,
)

class FahorroParser:
 """
 Parser for fahorro.com pages (product pages and listings).
 Uses a RequestHandler to fetch pages, then BeautifulSoup/JSON-LD to extract data.
 """

 BASE_DOMAIN = "fahorro.com"

 def __init__(self, request_handler, logger):
 self.rh = request_handler
 self.logger = logger

 # -----------------------------
 # Public API
 # -----------------------------
 def parse_product(self, url: str) -> Optional[Dict[str, Any]]:
 """
 Parse a single product page and return a normalized product dict.
 """
 html = self.rh.get(url)
 if not html:
 self.logger.warning(f"No HTML fetched for product: {url}")
 return None

 soup = BeautifulSoup(html, "lxml")

 # Prefer JSON-LD schema if available
 schemas = self._extract_jsonld(soup)
 product = self._product_from_jsonld(schemas)
 if not product:
 product = self._product_from_dom(soup)

 if not product:
 self.logger.warning(f"Failed to extract product fields: {url}")
 return None

 # Fill in missing URL and category
 product["url"] = product.get("url") or url
 product["category"] = product.get("category") or self._breadcrumbs_category(soup)

 # Tidy values
 if product.get("title"):
 product["title"] = normalize_whitespace(product["title"])
 if product.get("description"):
 product["description"] = normalize_whitespace(product["description"])
 if product.get("imageUrl"):
 product["imageUrl"] = product["imageUrl"].strip()
 if product.get("price") is not None:
 product["price"] = normalize_price(str(product["price"]))

 return product

 def parse_listing(self, url: str) -> List[Dict[str, Any]]:
 """
 Parse a category/search listing page, follow product links, and return product objects.
 Includes basic pagination support where possible.
 """
 products: List[Dict[str, Any]] = []
 seen_links = set()

 next_url = url
 page_no = 1
 while next_url:
 self.logger.info(f"Fetching listing page {page_no}: {next_url}")
 html = self.rh.get(next_url)
 if not html:
 self.logger.warning(f"No HTML fetched for listing: {next_url}")
 break

 soup = BeautifulSoup(html, "lxml")
 product_links = self._collect_product_links(soup, base_url=next_url)
 new_links = [l for l in product_links if l not in seen_links]
 self.logger.info(f"Found {len(new_links)} new product links on page {page_no}")

 for link in new_links:
 seen_links.add(link)
 if not is_product_like_url(link):
 # Still try, we rely on product page structure more than URL
 self.logger.debug(f"Following non-typical product URL: {link}")
 try:
 prod = self.parse_product(link)
 if prod:
 products.append(prod)
 except Exception as e:
 self.logger.exception(f"Error parsing product {link}: {e}")

 next_url = self._find_next_page(soup, base_url=next_url)
 page_no += 1

 return products

 # -----------------------------
 # Private helpers
 # -----------------------------
 def _extract_jsonld(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
 schemas: List[Dict[str, Any]] = []
 for tag in soup.find_all("script", type="application/ld+json"):
 try:
 data = json.loads(tag.string or "{}")
 if isinstance(data, list):
 schemas.extend([d for d in data if isinstance(d, dict)])
 elif isinstance(data, dict):
 schemas.append(data)
 except Exception:
 continue
 return schemas

 def _product_from_jsonld(self, schemas: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
 product_schema = None
 for s in schemas:
 t = s.get("@type")
 if isinstance(t, list):
 if "Product" in t:
 product_schema = s
 break
 elif t == "Product":
 product_schema = s
 break

 if not product_schema:
 return None

 title = product_schema.get("name")
 description = product_schema.get("description")
 image = None
 imgs = product_schema.get("image")
 if isinstance(imgs, list) and imgs:
 image = imgs[0]
 elif isinstance(imgs, str):
 image = imgs

 price = None
 offers = product_schema.get("offers")
 if isinstance(offers, dict):
 price = offers.get("price") or offers.get("lowPrice")

 url = product_schema.get("url")

 return {
 "title": title,
 "description": description,
 "price": normalize_price(price) if price is not None else None,
 "imageUrl": image,
 "category": None,
 "url": url,
 }

 def _product_from_dom(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
 title = extract_first_text(
 soup.select("h1, h1.product-title, h1[itemprop='name'], meta[itemprop='name']")
 )
 if not title:
 # Try OpenGraph
 og_title = soup.find("meta", property="og:title")
 title = og_title.get("content").strip() if og_title else None

 desc = None
 # Typical description containers
 desc_candidates = soup.select(
 "[itemprop='description'], .product-description, #description, .description"
 )
 for c in desc_candidates:
 text = c.get_text(" ", strip=True)
 if text and len(text) > 20:
 desc = text
 break
 if not desc:
 meta_desc = soup.find("meta", attrs={"name": "description"})
 desc = meta_desc.get("content").strip() if meta_desc and meta_desc.get("content") else None

 # Price
 price = None
 # itemprop
 price_tag = soup.find(attrs={"itemprop": re.compile("price", re.I)})
 if price_tag:
 content = price_tag.get("content") or price_tag.get_text(strip=True)
 price = normalize_price(content)
 if price is None:
 # common classes
 for sel in [".price", ".product-price", ".price__current", ".product__price"]:
 pt = soup.select_one(sel)
 if pt:
 price = normalize_price(pt.get_text(" ", strip=True))
 if price is not None:
 break

 # Image
 image = None
 for sel in [
 "img[itemprop='image']",
 "img.product-image",
 "img#productImage",
 "meta[property='og:image']",
 ]:
 tag = soup.select_one(sel)
 if tag:
 image = tag.get("content") or tag.get("src")
 if image:
 image = image.strip()
 break

 return {
 "title": title,
 "description": desc,
 "price": price,
 "imageUrl": image,
 "category": None,
 "url": None,
 }

 def _breadcrumbs_category(self, soup: BeautifulSoup) -> Optional[str]:
 crumbs = soup.select("nav.breadcrumb a, .breadcrumb a, [itemtype*='BreadcrumbList'] a")
 texts = [c.get_text(" ", strip=True) for c in crumbs if c.get_text(strip=True)]
 if texts:
 return " > ".join(texts[1:]) if len(texts) > 1 else texts[0]
 return None

 def _collect_product_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
 links: List[str] = []
 # Common product card anchors
 for a in soup.select("a"):
 href = a.get("href")
 if not href:
 continue
 txt = a.get_text(" ", strip=True)
 # Heuristics: product cards often have data attributes or images inside
 if a.find("img") or "product" in (a.get("class") or []) or ("producto" in txt.lower()):
 url = urljoin(base_url, href)
 # Filter out obvious non-product links (cart, account, etc.)
 if not re.search(r"(cart|account|login|register|wishlist|help|policy)", url, re.I):
 links.append(url)

 # Fallback: look for product-like URLs
 if is_product_like_url(href):
 links.append(urljoin(base_url, href))

 # Stable unique
 uniq = list(dict.fromkeys(links))
 return uniq

 def _find_next_page(self, soup: BeautifulSoup, base_url: str) -> Optional[str]:
 # Look for rel="next"
 link = soup.find("link", rel="next")
 if link and link.get("href"):
 return urljoin(base_url, link.get("href"))

 # Common pagination selectors
 for sel in [
 "a.next",
 "a[rel='next']",
 "li.pagination-next a",
 ".pagination a[aria-label='Next']",
 ".pagination a[rel='next']",
 ]:
 a = soup.select_one(sel)
 if a and a.get("href"):
 return urljoin(base_url, a.get("href"))

 return None