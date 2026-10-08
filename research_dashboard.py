"""Local read-only research dashboard; no application or broker integration."""

import argparse
import json
import math
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from online_finrl_data import fetch_latest_records


class ResearchStore:
    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("research root must be a directory")
        self.cache, self.lock = {}, threading.Lock()

    def _folder(self, run):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run):
            raise ValueError("invalid run identifier")
        folder = self.root/run
        if folder.is_symlink() or folder.resolve().parent != self.root:
            raise ValueError("run must be a direct research child")
        return folder

    def _json(self, folder, name):
        path = folder/name
        if path.is_symlink() or path.resolve().parent != folder.resolve() or path.stat().st_size > 5_000_000:
            raise ValueError("invalid or oversized research file")
        return json.loads(path.read_text(encoding="utf-8"))

    def runs(self):
        return sorted(p.name for p in self.root.iterdir() if p.is_dir() and not p.is_symlink()
                      and re.fullmatch(r"[A-Za-z0-9_-]{1,100}", p.name)
                      and (p/"report.json").is_file() and (p/"snapshot.json").is_file())

    def load(self, run):
        folder = self._folder(run)
        report = self._json(folder, "report.json")
        snapshot = self._json(folder, "snapshot.json")
        if not isinstance(report, dict) or not isinstance(snapshot, dict):
            raise ValueError("invalid report or snapshot")
        records = snapshot.get("records")
        if not isinstance(records, list) or not records or len(records) > 20000:
            raise ValueError("snapshot must contain 1..20000 records")
        symbol = report.get("symbol")
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9]{1,20}USDT", symbol):
            raise ValueError("invalid report symbol")
        selected = [r for r in records if isinstance(r, dict) and r.get("tic") == symbol]
        if not selected:
            raise ValueError("snapshot does not contain report symbol")
        # Validate the selected closed-candle series with the same causal contract.
        from causal_indicators import add_indicators
        featured = add_indicators(selected, as_of_ms=snapshot["server_time_ms"],
                                  interval=snapshot.get("interval", "1h"))
        for section in ("validation", "test"):
            results = report.get("results", {}).get(section)
            if not isinstance(results, dict) or not results:
                raise ValueError("missing benchmark results")
            for result in results.values():
                for key in ("return_pct", "max_drawdown_pct", "final_equity", "trades"):
                    value = result.get(key)
                    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                        raise ValueError("invalid benchmark metric")
        return {"run": run, "report": report,
                "snapshot": {k: v for k, v in snapshot.items() if k != "records"},
                "quality": {"checked_rows": len(featured), "ready_rows": sum(r["features_ready"] for r in featured),
                            "first_date": featured[0]["date"], "last_date": featured[-1]["date"],
                            "status": "validated", "scope": "selected symbol; closed times, OHLCV, continuity"},
                "candles": [{k: r[k] for k in ("date", "close", "sma", "ema", "rsi")} for r in featured[-180:]]}

    def market(self, symbol):
        # A single lock prevents refresh storms; 60s cache is explicit in UI.
        with self.lock:
            now = time.monotonic()
            cached = self.cache.get(symbol)
            if cached and now-cached[0] < 60:
                return dict(cached[1], cached=True)
            snapshot = fetch_latest_records([symbol], count=2)
            payload = {"symbol": symbol, "server_time_ms": snapshot["server_time_ms"],
                       "closed_before_ms": snapshot["closed_before_ms"],
                       "latest": snapshot["records"][-1], "cached": False}
            self.cache[symbol] = (now, payload)
            return payload


def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def respond(self, status, payload, content_type="application/json; charset=utf-8"):
            body = payload.encode() if isinstance(payload, str) else json.dumps(payload, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
                return self.respond(403, {"error": "local host required"})
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            try:
                if parsed.path == "/":
                    return self.respond(200, Path(__file__).with_name("research_dashboard.html").read_text(encoding="utf-8"), "text/html; charset=utf-8")
                if parsed.path == "/api/runs":
                    return self.respond(200, {"runs": store.runs()})
                if parsed.path == "/api/run":
                    return self.respond(200, store.load(query.get("id", [""])[0]))
                if parsed.path == "/api/market":
                    return self.respond(200, store.market(query.get("symbol", [""])[0]))
                return self.respond(404, {"error": "not found"})
            except (ValueError, KeyError, TypeError):
                return self.respond(400, {"error": "Veri biçimi geçersiz veya dosya doğrulanamadı."})
            except OSError:
                return self.respond(404, {"error": "Araştırma dosyası bulunamadı veya okunamadı."})
            except RuntimeError:
                return self.respond(503, {"error": "Online veriye erişilemiyor. Bağlantı veya API limiti nedeniyle yenileme durdu."})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", required=True)
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(ResearchStore(args.research_root)))
    print(f"Research dashboard: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
