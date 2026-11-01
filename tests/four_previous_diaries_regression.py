"""Fourth preceding diary rule with gaps, multiple epicrises and no evidence."""
from datetime import date, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from diary_service import fourth_preceding_diary_observation as select

start = date(2026, 9, 1)
observations = {start + timedelta(days=i * 3): f"OBS_{i + 1}" for i in range(12)}
assert select(start + timedelta(days=18), observations, ()) == "OBS_3"
assert select(start + timedelta(days=6), observations, ()) == ""
assert select(start + timedelta(days=18), observations, (start + timedelta(days=6),)) == "OBS_2"
assert select(start + timedelta(days=18), observations, (start + timedelta(days=6), start + timedelta(days=12))) == "OBS_1"
assert select(start + timedelta(days=21), {}, ()) == ""
assert select(start + timedelta(days=21), {start: "   "}, ()) == ""
assert select(start + timedelta(days=12), observations, ()) == "OBS_1"
print("FOUR PREVIOUS DIARIES: PASS")
