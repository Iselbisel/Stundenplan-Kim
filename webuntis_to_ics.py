#!/usr/bin/env python3
"""Holt den öffentlichen WebUntis-Stundenplan (HS Albstadt-Sigmaringen, Klasse KIM-1)
und schreibt ihn als Kalenderdatei stundenplan.ics – zum Abonnieren in Google Kalender."""
import json, urllib.request, http.cookiejar, datetime as dt

SERVER = "https://hs-albstadt.webuntis.com"
SCHOOL = "hs-albstadt"
CLASS_ID = 6385            # KIM-1 (öffentliche ID in WebUntis)
WEEKS_BACK, WEEKS_AHEAD = 1, 20
OUTFILE = "stundenplan.ics"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.addheaders = [("User-Agent", "Mozilla/5.0 kim-stundenplan-sync")]

def get_json(path):
    with opener.open(SERVER + path, timeout=30) as r:
        return json.load(r)

def esc(s):
    return s.replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,").replace("\n", "\\n")

def fold(line):
    out, b = [], line.encode()
    while len(b) > 75:
        cut = 75
        while (b[cut] & 0xC0) == 0x80:  # nicht mitten in einem UTF-8-Zeichen trennen
            cut -= 1
        out.append(b[:cut].decode()); b = b" " + b[cut:]
    out.append(b.decode())
    return "\r\n".join(out)

def build_events(week_data):
    d = week_data["data"]["result"]["data"]
    els = {(e["type"], e["id"]): e for e in d.get("elements", [])}
    events = []
    for p in d.get("elementPeriods", {}).get(str(CLASS_ID), []):
        names = {1: [], 2: [], 3: [], 4: []}
        for ref in p["elements"]:
            e = els.get((ref["type"], ref["id"]))
            if e and ref["type"] in names:
                names[ref["type"]].append(e.get("name") or "")
        subj_short = ", ".join(n for n in names[3] if n)
        subj_long = ", ".join(els[(3, r["id"])].get("longName", "") for r in p["elements"]
                              if r["type"] == 3 and (3, r["id"]) in els)
        title = subj_long or subj_short or p.get("lessonText") or "Veranstaltung"
        state = p.get("cellState", "")
        if state == "CANCEL":
            title = "❌ Entfällt – " + title
        elif state in ("SUBSTITUTION", "ROOMSUBSTITUTION", "ADDITIONAL", "SHIFT"):
            title = "🔄 " + title
        date = str(p["date"])
        start = f"{date}T{p['startTime']:04d}00"
        end = f"{date}T{p['endTime']:04d}00"
        desc = [f"Kürzel: {subj_short}" if subj_short else "",
                f"Dozent: {', '.join(names[2])}" if names[2] else "",
                f"Modul/Info: {p.get('lessonText')}" if p.get("lessonText") else "",
                p.get("periodText") or "", p.get("substText") or "",
                f"Gruppen: {', '.join(names[1])}"]
        events.append({
            "uid": f"{p['id']}@kim-stundenplan", "start": start, "end": end,
            "summary": title, "location": ", ".join(names[4]),
            "desc": "\n".join(x for x in desc if x),
        })
    return events

def main():
    opener.open(f"{SERVER}/WebUntis/?school={SCHOOL}", timeout=30).read()  # Sitzung/Cookies holen
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    events, seen = [], set()
    for w in range(-WEEKS_BACK, WEEKS_AHEAD + 1):
        day = monday + dt.timedelta(weeks=w)
        try:
            data = get_json(f"/WebUntis/api/public/timetable/weekly/data?elementType=1"
                            f"&elementId={CLASS_ID}&date={day.isoformat()}&formatId=1")
            for ev in build_events(data):
                if ev["uid"] not in seen:
                    seen.add(ev["uid"]); events.append(ev)
        except Exception as ex:
            print(f"Woche {day}: übersprungen ({ex})")
    if not events:
        raise SystemExit("Keine Termine gefunden – Datei wird nicht überschrieben.")
    stamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//kim-stundenplan//DE",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:Stundenplan KIM-1",
             "X-WR-TIMEZONE:Europe/Berlin", "REFRESH-INTERVAL;VALUE=DURATION:PT3H",
             "X-PUBLISHED-TTL:PT3H"]
    for ev in sorted(events, key=lambda e: e["start"]):
        lines += ["BEGIN:VEVENT", f"UID:{ev['uid']}", f"DTSTAMP:{stamp}",
                  f"DTSTART;TZID=Europe/Berlin:{ev['start']}",
                  f"DTEND;TZID=Europe/Berlin:{ev['end']}",
                  f"SUMMARY:{esc(ev['summary'])}", f"LOCATION:{esc(ev['location'])}",
                  f"DESCRIPTION:{esc(ev['desc'])}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    with open(OUTFILE, "w", encoding="utf-8", newline="") as f:
        f.write("\r\n".join(fold(l) for l in lines) + "\r\n")
    print(f"{len(events)} Termine in {OUTFILE} geschrieben.")

if __name__ == "__main__":
    main()
