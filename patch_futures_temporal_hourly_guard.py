from pathlib import Path

path = Path("zitar_futures_temporal_intelligence_v1.py")
text = path.read_text(encoding="utf-8")

old = '''def main():
    errors = []'''

new = '''def main():

    # -------------------------------------------------
    # HOURLY OBSERVATION GUARD
    # Aynı UTC saatinde ikinci temporal gözlem yazılmaz.
    # -------------------------------------------------

    existing_records = load_log()
    now_dt = datetime.now(timezone.utc)

    if existing_records:
        last_ts = existing_records[-1].get("observed_utc")

        if last_ts:
            try:
                last_dt = datetime.fromisoformat(last_ts)

                same_utc_hour = (
                    last_dt.year == now_dt.year
                    and last_dt.month == now_dt.month
                    and last_dt.day == now_dt.day
                    and last_dt.hour == now_dt.hour
                )

                if same_utc_hour:
                    print("ZİTAR FUTURES TEMPORAL INTELLIGENCE V1")
                    print("RESEARCH ONLY • NO API KEY • NO ORDER • NO V3 WRITE")
                    print("observation:", len(existing_records))
                    print("HOURLY GUARD: current UTC hour already observed")
                    print("NEW OBSERVATION: SKIPPED")
                    print("STATUS: PASS")
                    return

            except Exception:
                pass

    errors = []'''

if old not in text:
    raise SystemExit("STOP: main() anchor bulunamadi")

text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")

print("FUTURES TEMPORAL HOURLY GUARD PATCH PASS")
