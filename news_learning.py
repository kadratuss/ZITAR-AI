import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MINUTE = 60_000
WINDOWS = (5, 15, 60, 240)


def percent(start, end):
    return float((end / start - 1) * 100) if start else None


def main():
    with sqlite3.connect(ROOT / "ai_core.db", timeout=15) as db:
        news = db.execute("""
            SELECT id, title, published_at
            FROM knowledge
            WHERE project = 'investment'
              AND published_at IS NOT NULL
            ORDER BY id
        """).fetchall()

    with sqlite3.connect(ROOT / "learning_lab.db", timeout=15) as db:
        rows = db.execute("""
            SELECT open_time_ms, open_price, high_price,
                   low_price, close_price, volume
            FROM candles
            WHERE symbol = 'BTCTRY' AND interval = '1m'
            ORDER BY open_time_ms
        """).fetchall()

    candles = {
        int(t): tuple(Decimal(v) for v in values)
        for t, *values in rows
    }

    events = []
    for source_id, title, published in news:
        try:
            published_ms = int(
                parsedate_to_datetime(published)
                .astimezone(timezone.utc).timestamp() * 1000
            )
            events.append((source_id, title, published_ms))
        except (TypeError, ValueError, OverflowError):
            print(f"HABER {source_id}: YAYIN_ZAMANI_OKUNAMADI")

    with sqlite3.connect(ROOT / "news_learning.db", timeout=15) as out:
        out.execute("""
            CREATE TABLE IF NOT EXISTS event_reactions (
                source_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                window_minutes INTEGER NOT NULL,
                published_ms INTEGER NOT NULL,
                baseline_ms INTEGER NOT NULL,
                pre_return_pct REAL,
                post_return_pct REAL,
                max_rise_pct REAL,
                max_drop_pct REAL,
                volume_ratio REAL,
                first_5m_return_pct REAL,
                reversal INTEGER,
                overlapping_source_ids TEXT NOT NULL,
                measurement_status TEXT NOT NULL,
                calculated_at TEXT NOT NULL,
                PRIMARY KEY (source_id, symbol, window_minutes)
            )
        """)

        for source_id, title, published_ms in events:
            minute_start = published_ms // MINUTE * MINUTE
            baseline_t = minute_start - MINUTE
            first_after = (
                (published_ms + MINUTE - 1) // MINUTE
            ) * MINUTE

            print(f"\nHABER {source_id}: {title}")

            # Yayindan once tamamen kapanmis 60 mum.
            pre_times = [
                baseline_t - i * MINUTE
                for i in range(59, -1, -1)
            ]

            if any(t not in candles for t in pre_times):
                print("  ONCESI_60DK: EKSIK_VERI")
                continue

            pre = [candles[t] for t in pre_times]
            baseline = candles[baseline_t][3]
            pre_return = percent(pre[0][0], baseline)
            pre_volume = sum((c[4] for c in pre), Decimal(0))

            for minutes in WINDOWS:
                post_times = [
                    first_after + i * MINUTE
                    for i in range(minutes)
                ]

                if any(t not in candles for t in post_times):
                    print(f"  {minutes}DK: EKSIK_VERI")
                    continue

                post = [candles[t] for t in post_times]
                end_price = post[-1][3]
                highest = max(c[1] for c in post)
                lowest = min(c[2] for c in post)
                post_volume = sum(
                    (c[4] for c in post), Decimal(0)
                )

                # Hacim karsilastirmasi: onceki 60dk'nin
                # dakika basina ortalamasi ile sonraki pencere.
                volume_ratio = (
                    float((post_volume / Decimal(minutes)) /
                          (pre_volume / Decimal(60)))
                    if pre_volume else None
                )

                first_five = (
                    percent(baseline, post[4][3])
                    if len(post) >= 5 else
                    percent(baseline, end_price)
                )
                final_return = percent(baseline, end_price)

                # Ilk 5dk ve pencere sonu zit yonlu mu?
                reversal = int(
                    first_five is not None
                    and final_return is not None
                    and first_five * final_return < 0
                )

                window_end = first_after + minutes * MINUTE
                overlaps = [
                    str(other_id)
                    for other_id, _, other_ms in events
                    if other_id != source_id
                    and published_ms <= other_ms < window_end
                ]

                out.execute("""
                    INSERT INTO event_reactions (
                        source_id, symbol, window_minutes,
                        published_ms, baseline_ms, pre_return_pct,
                        post_return_pct, max_rise_pct, max_drop_pct,
                        volume_ratio, first_5m_return_pct, reversal,
                        overlapping_source_ids, measurement_status,
                        calculated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id, symbol, window_minutes)
                    DO UPDATE SET
                        published_ms=excluded.published_ms,
                        baseline_ms=excluded.baseline_ms,
                        pre_return_pct=excluded.pre_return_pct,
                        post_return_pct=excluded.post_return_pct,
                        max_rise_pct=excluded.max_rise_pct,
                        max_drop_pct=excluded.max_drop_pct,
                        volume_ratio=excluded.volume_ratio,
                        first_5m_return_pct=excluded.first_5m_return_pct,
                        reversal=excluded.reversal,
                        overlapping_source_ids=excluded.overlapping_source_ids,
                        measurement_status=excluded.measurement_status,
                        calculated_at=excluded.calculated_at
                """, (
                    source_id, "BTCTRY", minutes,
                    published_ms, baseline_t, pre_return,
                    final_return, percent(baseline, highest),
                    percent(baseline, lowest), volume_ratio,
                    first_five, reversal, ",".join(overlaps),
                    "OBSERVED_NOT_CAUSAL",
                    datetime.now(timezone.utc).isoformat()
                ))

                ratio_text = (
                    f"{volume_ratio:.2f}x"
                    if volume_ratio is not None else "YOK"
                )
                print(
                    f"  {minutes:>3}DK | "
                    f"SON={final_return:+.3f}% | "
                    f"TEPE={percent(baseline, highest):+.3f}% | "
                    f"DIP={percent(baseline, lowest):+.3f}% | "
                    f"HACIM={ratio_text} | "
                    f"TERS_DONUS={reversal} | "
                    f"CAKISMA={','.join(overlaps) or 'YOK'}"
                )

        out.commit()
        count = out.execute(
            "SELECT COUNT(*) FROM event_reactions"
        ).fetchone()[0]

    print(f"\nKALICI_OLAY_OLCUMU: {count}")
    print("DOSYA: news_learning.db")
    print("UYARI: Olculen hareket, haberin nedensel etkisi degildir.")
    print("RSS yayin saati ilk duyuru saati olmayabilir.")


if __name__ == "__main__":
    main()
