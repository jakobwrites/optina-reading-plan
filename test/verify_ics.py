#!/usr/bin/env python3
"""Build a sample Optina Rule calendar and check it.

Runs the browser generator (app.js) under Node, then parses the file
with the icalendar library. From the repo root:

    python3 test/verify_ics.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REC = ROOT / "data" / "rec"
DTSTAMP = "20260101T120000Z"

NODE = r"""
const { buildIcs, previewDays } = require('./app.js');
const readings = require('./readings.js');
const spec = JSON.parse(process.env.OPTINA_SPEC);
if (spec.mode === 'ics') {
  process.stdout.write(buildIcs(readings, spec));
} else if (spec.mode === 'preview') {
  process.stdout.write(JSON.stringify(previewDays(readings, spec)));
} else if (spec.mode === 'throw') {
  try {
    buildIcs(readings, spec);
    process.stderr.write('expected an error');
    process.exit(2);
  } catch (err) {
    process.stdout.write(String(err && err.message || err));
  }
} else {
  process.stderr.write('unknown mode');
  process.exit(2);
}
"""


def fail(errors: list[str]) -> None:
    print("FAILED", file=sys.stderr)
    for err in errors:
        print("- " + err, file=sys.stderr)
    sys.exit(1)


def load_readings_js() -> dict:
    text = (ROOT / "readings.js").read_text(encoding="utf-8")
    marker = "const OPTINA_READINGS = "
    start = text.index(marker) + len(marker)
    data, _end = json.JSONDecoder().raw_decode(text[start:])
    return data


def source_text(kind: str, n: int) -> str:
    prefix = "g" if kind == "day" else "k"
    return (REC / f"{prefix}{n:02d}.txt").read_bytes().decode("utf-8")


def derive_day_title(n: int, description: str) -> str:
    gospel = apostol = None
    for line in description.split("\n"):
        if line.startswith("Gospel: "):
            gospel = line.split(": ", 1)[1]
        elif line.startswith("Apostol: "):
            apostol = line.split(": ", 1)[1]
    if not gospel or not apostol:
        raise AssertionError(f"day {n} is missing a Gospel or Apostol line")
    if apostol.startswith("none"):
        apostol = "Apostol complete"
    return f"Day {n}: {gospel} | {apostol}"


def derive_kathisma_title(description: str) -> tuple[str, int]:
    first = description.split("\n", 1)[0]
    match = re.match(r"Psalter: Kathisma (\d+) \((Psalms? [^,]+)", first)
    if not match:
        raise AssertionError("unrecognized kathisma line: " + first)
    return f"Kathisma {match[1]}: {match[2]}", int(match[1])


def run_node(spec: dict) -> str:
    env = os.environ.copy()
    env["OPTINA_SPEC"] = json.dumps(spec)
    proc = subprocess.run(
        ["node", "-e", NODE],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace") or f"node exited {proc.returncode}")
    return proc.stdout.decode("utf-8")


def check_wire_format(ics: str, errors: list[str], label: str) -> None:
    if ics.startswith("\ufeff"):
        errors.append(f"{label}: BOM is not allowed")
    stripped = ics.replace("\r\n", "")
    if "\n" in stripped or "\r" in stripped:
        errors.append(f"{label}: line endings must be CRLF only")
    if not ics.endswith("\r\n"):
        errors.append(f"{label}: file must end with CRLF")
        return
    physical = ics.split("\r\n")[:-1]
    if any(line == "" for line in physical):
        errors.append(f"{label}: blank line in the calendar")
    if physical[0] != "BEGIN:VCALENDAR" or physical[-1] != "END:VCALENDAR":
        errors.append(f"{label}: calendar wrapper is missing")
    for line in physical:
        size = len(line.encode("utf-8"))
        if size > 75:
            errors.append(f"{label}: line is {size} octets: {line[:80]!r}")
            break
        if line.endswith("\\"):
            errors.append(f"{label}: a fold split an escape: {line[-20:]!r}")
            break
        for url in re.findall(r"https://biblehub\.com/[^\s\\]*", line):
            if not url.endswith(".htm"):
                errors.append(f"{label}: a Bible Hub link was folded in half: {url}")
                break


def as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError(type(value).__name__)


def rrule_parts(event) -> tuple[str, int]:
    rule = event.get("rrule")
    if rule is None:
        raise KeyError("RRULE")
    freq = rule.get("FREQ")
    interval = rule.get("INTERVAL")
    if isinstance(freq, list):
        freq = freq[0]
    if isinstance(interval, list):
        interval = interval[0]
    return str(freq), int(interval)


def check_events(calendar, events, start: date, start_k: int, errors: list[str], label: str) -> None:
    if len(events) != 109:
        errors.append(f"{label}: expected 109 VEVENTs, found {len(events)}")
        return
    if list(calendar.walk("VALARM")):
        errors.append(f"{label}: alarm present")
    uids = []
    days = {}
    kathismata = {}
    for event in events:
        uid = str(event.get("uid"))
        uids.append(uid)
        summary = str(event.get("summary"))
        description = str(event.get("description"))
        transp = str(event.get("transp"))
        if transp != "TRANSPARENT":
            errors.append(f"{label}: {uid} TRANSP is {transp}")
        if event.get("dtstamp") is None:
            errors.append(f"{label}: {uid} missing DTSTAMP")
        try:
            freq, interval = rrule_parts(event)
        except Exception as exc:  # noqa: BLE001 — report and keep going
            errors.append(f"{label}: {uid} RRULE {exc}")
            continue
        rule = event.get("rrule")
        if "UNTIL" in rule or "COUNT" in rule:
            errors.append(f"{label}: {uid} RRULE is not open-ended")
        start_on = as_date(event.decoded("dtstart"))
        end_on = as_date(event.decoded("dtend"))
        if end_on != start_on + timedelta(days=1):
            errors.append(f"{label}: {uid} DTEND is not the next day")

        day_match = re.fullmatch(r"optina-day-(\d{2})-from-(\d{8})@optina-reading-plan", uid)
        k_match = re.fullmatch(
            r"optina-kathisma-(\d{2})-from-(\d{8})-k(\d{2})@optina-reading-plan",
            uid,
        )
        if day_match:
            n = int(day_match.group(1))
            if day_match.group(2) != start.strftime("%Y%m%d"):
                errors.append(f"{label}: {uid} start stamp mismatch")
            if freq != "DAILY" or interval != 89:
                errors.append(f"{label}: day {n} RRULE is {freq}/{interval}")
            expected_day = start + timedelta(days=n - 1)
            if start_on != expected_day:
                errors.append(f"{label}: day {n} starts {start_on}, expected {expected_day}")
            source = source_text("day", n)
            if description != source:
                errors.append(f"{label}: day {n} description does not match g{n:02d}.txt")
            expected_title = derive_day_title(n, source)
            if summary != expected_title:
                errors.append(f"{label}: day {n} summary {summary!r} != {expected_title!r}")
            days[n] = event
        elif k_match:
            k = int(k_match.group(1))
            if k_match.group(2) != start.strftime("%Y%m%d") or int(k_match.group(3)) != start_k:
                errors.append(f"{label}: {uid} does not match this plan")
            if freq != "DAILY" or interval != 20:
                errors.append(f"{label}: kathisma {k} RRULE is {freq}/{interval}")
            offset = (k - start_k + 20) % 20
            expected_day = start + timedelta(days=offset)
            if start_on != expected_day:
                errors.append(f"{label}: kathisma {k} starts {start_on}, expected {expected_day}")
            source = source_text("kathisma", k)
            if description != source:
                errors.append(f"{label}: kathisma {k} description does not match k{k:02d}.txt")
            expected_title, found = derive_kathisma_title(source)
            if found != k or summary != expected_title:
                errors.append(f"{label}: kathisma {k} summary {summary!r} != {expected_title!r}")
            kathismata[k] = event
        else:
            errors.append(f"{label}: unexpected uid {uid}")

    if len(set(uids)) != 109:
        errors.append(f"{label}: UIDs are not unique")
    if set(days) != set(range(1, 90)) or set(kathismata) != set(range(1, 21)):
        errors.append(f"{label}: missing day or kathisma events")
        return

    # Day 1 lines up with the chosen starting kathisma; the other kathismata follow.
    if as_date(days[1].decoded("dtstart")) != start:
        errors.append(f"{label}: day 1 is not on the start date")
    if as_date(kathismata[start_k].decoded("dtstart")) != start:
        errors.append(f"{label}: starting kathisma {start_k} is not on day 1")
    if start_k == 1:
        for n in range(1, 21):
            if as_date(days[n].decoded("dtstart")) != as_date(kathismata[n].decoded("dtstart")):
                errors.append(f"{label}: day {n} and kathisma {n} do not share a start date")
                break


def check_sources(readings: dict, errors: list[str]) -> None:
    if [item["n"] for item in readings["days"]] != list(range(1, 90)):
        errors.append("readings.js days are not 1..89 in order")
    if [item["n"] for item in readings["kathismata"]] != list(range(1, 21)):
        errors.append("readings.js kathismata are not 1..20 in order")
    for item in readings["days"]:
        source = source_text("day", item["n"])
        if item["description"] != source:
            errors.append(f"readings.js day {item['n']} differs from data/rec")
        if f"day {item['n']} of 89" not in source:
            errors.append(f"g{item['n']:02d}.txt does not name its day")
        title = derive_day_title(item["n"], source)
        if item["n"] == 1 and title != "Day 1: Matthew 1 | Acts 1-2":
            errors.append("day 1 title drifted: " + title)
        if item["n"] == 83 and title != "Day 83: John 15 | Revelation 16-22":
            errors.append("day 83 title drifted: " + title)
        if item["n"] == 89 and title != "Day 89: John 21 | Apostol complete":
            errors.append("day 89 title drifted: " + title)
    for item in readings["kathismata"]:
        source = source_text("kathisma", item["n"])
        if item["description"] != source:
            errors.append(f"readings.js kathisma {item['n']} differs from data/rec")
        title, found = derive_kathisma_title(source)
        if found != item["n"]:
            errors.append(f"kathisma {item['n']} heading number is {found}")
        if item["n"] == 6 and title != "Kathisma 6: Psalms 37-45":
            errors.append("kathisma 6 title drifted: " + title)
        if item["n"] == 17 and title != "Kathisma 17: Psalm 118":
            errors.append("kathisma 17 title drifted: " + title)
    file_urls = Counter()
    js_urls = Counter()
    url_re = re.compile(r"https://biblehub\.com/\S+")
    for n in range(1, 90):
        file_urls.update(url_re.findall(source_text("day", n)))
        js_urls.update(url_re.findall(readings["days"][n - 1]["description"]))
    for n in range(1, 21):
        file_urls.update(url_re.findall(source_text("kathisma", n)))
        js_urls.update(url_re.findall(readings["kathismata"][n - 1]["description"]))
    if file_urls != js_urls:
        errors.append("Bible Hub links in readings.js do not match data/rec")
    if not file_urls:
        errors.append("no Bible Hub links found in the source texts")


def main() -> None:
    try:
        from icalendar import Calendar
    except ImportError:
        sys.exit("Install the checker first: python3 -m pip install icalendar")

    errors: list[str] = []
    readings = load_readings_js()
    check_sources(readings, errors)

    cases = [
        ("2026-03-01", 1),   # kathisma n shares its first date with day n
        ("2026-10-22", 6),   # Psalter begins at kathisma 6
        ("2024-02-28", 1),   # day 2 is the leap day
        ("2023-02-28", 1),   # day 2 falls on March 1
        ("2024-02-20", 1),   # kathisma 10 first falls on Feb 29
        ("2026-12-20", 20),  # day 21 crosses into the next year
    ]

    max_line = 0
    sample = ""
    for iso, start_k in cases:
        spec = {
            "mode": "ics",
            "startDate": iso,
            "startKathisma": start_k,
            "dtstamp": DTSTAMP,
        }
        ics = run_node(spec)
        sample = ics
        for line in ics.split("\r\n"):
            max_line = max(max_line, len(line.encode("utf-8")))
        label = f"{iso} k{start_k}"
        check_wire_format(ics, errors, label)
        if ics.count("RRULE:FREQ=DAILY;INTERVAL=89") != 89:
            errors.append(f"{label}: 89-day rule count is wrong")
        if ics.count("RRULE:FREQ=DAILY;INTERVAL=20") != 20:
            errors.append(f"{label}: 20-day rule count is wrong")
        if "VALARM" in ics or "TRIGGER" in ics:
            errors.append(f"{label}: alarm text present")
        calendar = Calendar.from_ical(ics)
        check_events(calendar, list(calendar.walk("VEVENT")), date.fromisoformat(iso), start_k, errors, label)

    again = run_node({"mode": "ics", "startDate": "2026-03-01", "startKathisma": 1, "dtstamp": DTSTAMP})
    first = run_node({"mode": "ics", "startDate": "2026-03-01", "startKathisma": 1, "dtstamp": DTSTAMP})
    if again != first:
        errors.append("the same start date did not produce the same file")
    shifted = run_node({"mode": "ics", "startDate": "2026-03-01", "startKathisma": 1, "dtstamp": "20260202T010203Z"})
    if shifted == first:
        errors.append("DTSTAMP should change when the timestamp changes")
    def uids(text: str) -> list[str]:
        return re.findall(r"^UID:[^\r]+", text, re.M)
    if uids(shifted) != uids(first):
        errors.append("UIDs changed when only DTSTAMP changed")

    # Named alignments the generic check also covers, kept here so a failure is obvious.
    leap = Calendar.from_ical(run_node({"mode": "ics", "startDate": "2024-02-28", "startKathisma": 1, "dtstamp": DTSTAMP}))
    by_uid = {str(ev.get("uid")): ev for ev in leap.walk("VEVENT")}
    leap_day = as_date(by_uid["optina-day-02-from-20240228@optina-reading-plan"].decoded("dtstart"))
    if leap_day != date(2024, 2, 29):
        errors.append(f"leap day alignment: day 2 is {leap_day}")
    feb20 = Calendar.from_ical(run_node({"mode": "ics", "startDate": "2024-02-20", "startKathisma": 1, "dtstamp": DTSTAMP}))
    by_uid = {str(ev.get("uid")): ev for ev in feb20.walk("VEVENT")}
    kathisma_10 = as_date(by_uid["optina-kathisma-10-from-20240220-k01@optina-reading-plan"].decoded("dtstart"))
    if kathisma_10 != date(2024, 2, 29):
        errors.append(f"kathisma 10 should land on 2024-02-29, got {kathisma_10}")

    shifted_psalter = Calendar.from_ical(run_node({"mode": "ics", "startDate": "2026-10-22", "startKathisma": 6, "dtstamp": DTSTAMP}))
    by_uid = {str(ev.get("uid")): ev for ev in shifted_psalter.walk("VEVENT")}
    if as_date(by_uid["optina-kathisma-06-from-20261022-k06@optina-reading-plan"].decoded("dtstart")) != date(2026, 10, 22):
        errors.append("kathisma 6 should start on 2026-10-22")
    if as_date(by_uid["optina-kathisma-01-from-20261022-k06@optina-reading-plan"].decoded("dtstart")) != date(2026, 11, 6):
        errors.append("kathisma 1 should first fall on 2026-11-06 when starting at kathisma 6")
    if str(by_uid["optina-day-01-from-20261022@optina-reading-plan"].get("summary")) != "Day 1: Matthew 1 | Acts 1-2":
        errors.append("day 1 summary mismatch for 2026-10-22")

    preview = json.loads(run_node({
        "mode": "preview",
        "startDate": "2026-10-22",
        "startKathisma": 6,
        "count": 7,
    }))
    if len(preview) != 7:
        errors.append("preview is not 7 days")
    elif preview[0]["date"] != "2026-10-22" or preview[0]["gospel"] != "Matthew 1" or preview[0]["kathismaNumber"] != 6:
        errors.append("preview day 1 / kathisma alignment is wrong: " + json.dumps(preview[0]))
    elif [row["kathismaNumber"] for row in preview] != [6, 7, 8, 9, 10, 11, 12]:
        errors.append("preview kathisma sequence is wrong")

    for bad in (
        {"mode": "throw", "startDate": "2026-02-31", "startKathisma": 1, "dtstamp": DTSTAMP},
        {"mode": "throw", "startDate": "2026-10-22", "startKathisma": 0, "dtstamp": DTSTAMP},
        {"mode": "throw", "startDate": "2026-10-22", "startKathisma": 21, "dtstamp": DTSTAMP},
    ):
        message = run_node(bad)
        if not message:
            errors.append("invalid input was accepted: " + json.dumps(bad))

    if errors:
        fail(errors)

    print(
        f"OK: 109 events, max physical line {max_line} octets, "
        f"{len(cases)} start dates, descriptions match data/rec"
    )
    # Keep a generated sample from being flagged as unused in a refactor.
    if not sample.startswith("BEGIN:VCALENDAR"):
        sys.exit("sample calendar was empty")


if __name__ == "__main__":
    main()
