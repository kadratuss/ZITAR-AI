import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = Path(sys.executable)

OBSERVER = ROOT / "forward_signal_observer_v2.py"
EXECUTOR = ROOT / "forward_paper_executor_v1.py"

print("")
print("=" * 60)
print("FORWARD HOURLY RUNNER V1")
print("UTC:", datetime.now(timezone.utc).isoformat())
print("=" * 60)

print("")
print("1/2 OBSERVER BASLIYOR...")
observer = subprocess.run(
    [str(PYTHON), str(OBSERVER)],
    cwd=str(ROOT)
)

if observer.returncode != 0:
    print("")
    print("OBSERVER HATA KODU:", observer.returncode)
    print("EXECUTOR CALISTIRILMADI.")
    sys.exit(observer.returncode)

print("")
print("OBSERVER OK.")

print("")
print("2/2 PAPER EXECUTOR BASLIYOR...")
executor = subprocess.run(
    [str(PYTHON), str(EXECUTOR)],
    cwd=str(ROOT)
)

if executor.returncode != 0:
    print("")
    print("EXECUTOR HATA KODU:", executor.returncode)
    sys.exit(executor.returncode)

print("")
print("EXECUTOR OK.")
print("")
print("FORWARD SAATLIK ZINCIR TAMAMLANDI.")
print("GERCEK EMIR YOK.")
