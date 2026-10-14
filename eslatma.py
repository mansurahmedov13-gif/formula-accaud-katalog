# -*- coding: utf-8 -*-
"""
Formula-Accaud: soliq tölovi va hisobot muddatlari eslatmasi.
GitHub Actions har kuni 10:00 (Toşkent) da işga tuşiradi. muddatlar.json dagi kalendar böyiça
3, 2, 1 kun qolganda va muddat kunida kanalga eslatma post qiladi.
Şanba/yakşanba yoki bayramga tuşgan muddat keyingi iş kuniga suriladi (SK 5-modda).

Muhit: BOT_TOKEN, CHANNEL (standart formulaAccaud), ADMIN_ID (xabarnoma), SINOV=1 bölsa kanalga emas, adminga yuboradi
"""
import json, os, sys, html, urllib.request, urllib.parse
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CAL = os.path.join(HERE, "muddatlar.json")
STATE = os.path.join(HERE, "eslatma_state.json")
TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN = os.environ.get("ADMIN_ID", "").strip()
CHANNEL = "@" + os.environ.get("CHANNEL", "formulaAccaud").strip().lstrip("@")
SINOV = os.environ.get("SINOV", "").strip() in ("1", "true", "ha")
TZ = timezone(timedelta(hours=5))

OYLAR = ["", "yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentyabr", "oktyabr", "noyabr", "dekabr"]
KUNLAR = ["duşanba", "seşanba", "çorşanba", "payşanba", "juma", "şanba", "yakşanba"]

def api(method, params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read().decode())
        except Exception: return {"ok": False, "description": str(e)}
    except Exception as e:
        return {"ok": False, "description": str(e)}

def load(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception: return default

def fmt(d):
    return f"{d.day}-{OYLAR[d.month]} ({KUNLAR[d.weekday()]})"

def holidays(cal):
    hs = set()
    for k, v in cal.items():
        if k.startswith("bayramlar_"):
            for s in v: hs.add(date.fromisoformat(s))
    return hs

def shift(d, hs):
    """Dam olish yoki bayram kuniga tuşsa — keyingi iş kuniga suradi."""
    while d.weekday() >= 5 or d in hs:
        d += timedelta(days=1)
    return d

def period_label(m, due_month, due_year):
    """Muddat qaysi davr uçun ekanini yozadi: '2026-yil sentyabr', '2026-yil 3-çorak', '2025-yil'."""
    davr = m["davr"]
    joriy = davr.endswith("_joriy")
    base = davr.replace("_joriy", "")
    if base == "oylik":
        if joriy: return f"{due_year}-yil {OYLAR[due_month]}"
        pm = due_month - 1 or 12; py = due_year if due_month > 1 else due_year - 1
        return f"{py}-yil {OYLAR[pm]}"
    if base == "choraklik":
        if joriy:
            return f"{due_year}-yil {(due_month - 1) // 3 + 1}-çorak"
        q_end = due_month - 1 if due_month > 1 else 12
        y = due_year if due_month > 1 else due_year - 1
        return f"{y}-yil {(q_end - 1) // 3 + 1}-çorak"
    if base == "yillik":
        return f"{due_year if joriy else due_year - 1}-yil"
    return ""

def due_dates(m, year):
    """Muddatning şu yildagi barça asl sanalari."""
    out = []
    months = range(1, 13) if m["davr"].startswith("oylik") else m.get("oylar", [])
    for mo in months:
        try: out.append(date(year, mo, m["kun"]))
        except ValueError: pass
    return out

def main():
    cal = load(CAL, None)
    if not cal: print("muddatlar.json topilmadi"); sys.exit(1)
    st = load(STATE, {"yuborilgan": []})
    hs = holidays(cal)
    today = datetime.now(TZ).date()
    steps = cal.get("eslatma_kunlari", [3, 2, 1, 0])

    # Keyingi 10 kun içidagi (surilgan) muddatlarni yiğamiz: sana → röyxat
    agenda = {}
    for m in cal["muddatlar"]:
        if not m.get("faol"): continue
        for y in (today.year, today.year + 1):
            for d0 in due_dates(m, y):
                d = shift(d0, hs)
                if 0 <= (d - today).days <= 10:
                    agenda.setdefault(d, []).append((m, d0))

    posted = 0
    for d in sorted(agenda):
        left = (d - today).days
        if left not in steps: continue
        key = f"{d.isoformat()}:{left}"
        if key in st["yuborilgan"]: continue
        items = agenda[d]
        head = {0: "⏰ Bugun", 1: "⏰ 1 kun qoldi (ertaga)"}.get(left, f"⏰ {left} kun qoldi")
        lines = [f"<b>{html.escape(head)} — muddat: {html.escape(fmt(d))}</b>"]
        shifted = {d0 for _, d0 in items if d0 != d}
        if shifted:
            d0 = min(shifted)
            lines.append(html.escape(f"(asl muddat {fmt(d0)} dam olish kuniga tuşgani uçun keyingi iş kuniga surilgan)"))
        lines.append("")
        tags = set(["#muddat", "#soliq"])
        for m, d0 in items:
            icon = {"hisobot": "📄", "tolov": "💸"}.get(m["tur"], "🧾")
            per = period_label(m, d0.month, d0.year)
            lines.append(f"{icon} <b>{html.escape(m['nom'])}</b>" + (f" — {html.escape(per)} uçun" if per else ""))
            if m.get("izoh"): lines.append(f"    <i>{html.escape(m['izoh'])}</i>")
            for t in m.get("teg", "").split(): tags.add(t)
        lines.append("")
        lines.append("📚 Hisobot şakllari va formulalar: t.me/AccaudBot/katalog")
        lines.append(" ".join(sorted(tags)))
        text = "\n".join(lines)

        target = ADMIN if SINOV else CHANNEL
        r = api("sendMessage", {"chat_id": target, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "true"})
        if r.get("ok"):
            posted += 1
            if not SINOV: st["yuborilgan"].append(key)
            print(f"✓ {key}\n{text}\n")
        else:
            print(f"✗ {key}: {r.get('description')}")
            if ADMIN and not SINOV:
                api("sendMessage", {"chat_id": ADMIN, "text": f"⚠️ Eslatma yuborilmadi ({key}): {r.get('description')}"})

    # eski yozuvlarni tozalaş (60 kundan eskisi)
    cutoff = (today - timedelta(days=60)).isoformat()
    st["yuborilgan"] = [k for k in st["yuborilgan"] if k[:10] >= cutoff]
    with open(STATE, "w", encoding="utf-8") as f: json.dump(st, f, ensure_ascii=False, indent=1)

    if SINOV:
        # keyingi 45 kunlik jadvalni körsatamiz
        print("\n=== Keyingi 45 kun jadvali (sinov) ===")
        for m in cal["muddatlar"]:
            if not m.get("faol"): continue
            for y in (today.year, today.year + 1):
                for d0 in due_dates(m, y):
                    d = shift(d0, hs)
                    if 0 <= (d - today).days <= 45:
                        print(f"{d.isoformat()} ({KUNLAR[d.weekday()]:<9}) {m['nom']}" + (f"  [asl: {d0.isoformat()}]" if d0 != d else ""))
    print(f"\nYuborildi: {posted}")

if __name__ == "__main__":
    main()
