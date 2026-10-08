from pathlib import Path

path = Path("zitar_futures_evidence_v1.py")
text = path.read_text(encoding="utf-8")

old = '''    for sym, rows in sorted(by.items()):
        latest=rows[-1]
        first=rows[0]
        n=len(rows)

        funding=latest.get("funding_rate")'''

new = '''    for sym, rows in sorted(by.items()):

        # -------------------------------------------------
        # UNIQUE UTC HOUR TEMPORAL VIEW
        # Ham log korunur.
        # Aynı UTC saatindeki birden fazla ölçümden
        # yalnızca o saatin SON ölçümü temporal analizde kullanılır.
        # -------------------------------------------------

        hourly = {}

        for row in rows:
            ts = row.get("_observed_utc")

            if not ts:
                continue

            try:
                dt = datetime.fromisoformat(ts)

                hour_key = (
                    dt.year,
                    dt.month,
                    dt.day,
                    dt.hour
                )

                hourly[hour_key] = row

            except Exception:
                continue

        temporal_rows = [
            hourly[key]
            for key in sorted(hourly)
        ]

        if not temporal_rows:
            continue

        latest=temporal_rows[-1]
        first=temporal_rows[0]

        raw_n=len(rows)
        n=len(temporal_rows)

        funding=latest.get("funding_rate")'''

if old not in text:
    raise SystemExit("STOP: temporal rows anchor bulunamadi")

text = text.replace(old, new, 1)

old2 = '''        temporal = {
            "status":"INSUFFICIENT_OBSERVATIONS" if n < MIN_OBS_FOR_TEMPORAL else "OBSERVABLE",
            "observations":n,'''

new2 = '''        temporal = {
            "status":"INSUFFICIENT_OBSERVATIONS" if n < MIN_OBS_FOR_TEMPORAL else "OBSERVABLE",
            "observations":n,
            "raw_observations":raw_n,
            "unique_utc_hours":n,
            "deduplication":"LAST_OBSERVATION_PER_UTC_HOUR",'''

if old2 not in text:
    raise SystemExit("STOP: temporal dictionary anchor bulunamadi")

text = text.replace(old2, new2, 1)

old3 = '''        "observation_count":len(history),
        "mode":"EVIDENCE_ONLY",'''

new3 = '''        "observation_count":len(history),
        "raw_observation_count":len(history),
        "temporal_counting_policy":"UNIQUE_UTC_HOUR_LAST_OBSERVATION",
        "mode":"EVIDENCE_ONLY",'''

if old3 not in text:
    raise SystemExit("STOP: report observation anchor bulunamadi")

text = text.replace(old3, new3, 1)

path.write_text(text, encoding="utf-8")

print("FUTURES EVIDENCE UNIQUE-HOUR PATCH PASS")
