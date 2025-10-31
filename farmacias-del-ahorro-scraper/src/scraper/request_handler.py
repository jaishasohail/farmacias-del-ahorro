pythonpython
import random
import time
from typing import Dict, Optional

import requests
from tenacity import (
 retry,
 stop_after_attempt,
 wait_exponential_jitter,
 retry_if_exception_type,
)

DEFAULT_USER_AGENTS = [
 # A small rotation of common desktop UAs
 "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
 " Chrome/124.0.0.0 Safari/537.36",
 "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_0) AppleWebKit/605.1.15 (KHTML, like Gecko)"
 " Version/16.5 Safari/605.1.15",
 "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)"
 " Chrome/123.0.0.0 Safari/537.36",
]

class TransientHTTPError(Exception):
 pass

class RequestHandler:
 def __init__(
 self,
 timeout: int = 15,
 max_retries: int = 3,
 backoff_base: float = 0.5,
 rotate_user_agents: bool = True,
 default_headers: Optional[Dict[str, str]] = None,
 request_delay: float = 0.0,
 ):
 self.timeout = timeout
 self.max_retries = max_retries
 self.backoff_base = backoff_base
 self.rotate_user_agents = rotate_user_agents
 self.default_headers = default_headers or {}
 self.session = requests.Session()
 self.request_delay = max(0.0, float(request_delay))

 def _headers(self) -> Dict[str, str]:
 headers = dict(self.default_headers)
 if self.rotate_user_agents:
 headers["User-Agent"] = random.choice(DEFAULT_USER_AGENTS)
 else:
 headers.setdefault("User-Agent", DEFAULT_USER_AGENTS[0])
 headers.setdefault("Accept-Language", "en-US,en;q=0.9,es-MX;q=0.8,es;q=0.7")
 headers.setdefault("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
 return headers

 @retry(
 retry=retry_if_exception_type(TransientHTTPError),
 stop=stop_after_attempt(3),
 wait=wait_exponential_jitter(initial=0.5, max=5.0),
 reraise=True,
 )
 def _fetch(self, url: str) -> str:
 resp = self.session.get(url, headers=self._headers(), timeout=self.timeout)
 # Simple throttling to be polite
 if self.request_delay:
 time.sleep(self.request_delay)

 if resp.status_code >= 500:
 raise TransientHTTPError(f"Server error {resp.status_code}")
 if resp.status_code in (403, 429):
 # Sometimes retrying works; treat as transient
 raise TransientHTTPError(f"Blocked or rate limited: {resp.status_code}")
 if resp.status_code != 200:
 # Non-retryable (e.g., 404)
 resp.raise_for_status()
 resp.encoding = resp.apparent_encoding or "utf-8"
 return resp.text

 def get(self, url: str) -> Optional[str]:
 try:
 return self._fetch(url)
 except Exception:
 return None