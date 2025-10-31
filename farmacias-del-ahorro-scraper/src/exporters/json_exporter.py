pythonpython
import json
from pathlib import Path
from typing import Any, Dict, List

class JsonExporter:
 @staticmethod
 def to_file(items: List[Dict[str, Any]], path: Path, pretty: bool = True) -> None:
 payload = items
 if pretty:
 data = json.dumps(payload, indent=2, ensure_ascii=False)
 else:
 data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

 path.write_text(data, encoding="utf-8")