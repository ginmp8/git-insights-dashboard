"""Safe local report serialization."""
from __future__ import annotations

import csv
import io
from typing import Any


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    """Neutralize spreadsheet formula interpretation in exported Git-sourced text."""
    if not rows:
        return b''
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        safe = {}
        for key, value in row.items():
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
                safe[key] = "'" + value
            else:
                safe[key] = value
        writer.writerow(safe)
    return buf.getvalue().encode('utf-8-sig')
