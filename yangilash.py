# -*- coding: utf-8 -*-
"""
Formula-Accaud: yangi kanal postlarini avtomat raqamlaş va katalogga qöşiş.
GitHub Actions har 15 daqiqada işga tuşiradi (server kerak emas).

Qoidalar:
  • Post matnining 1-qatori — sarlavha. Oxirida bölim tegi: #excel #1c #qonun #jadval #til #python
  • Matnsiz fayl/rasm post — oldingi raqamlangan materialning davomi
  • Bölim tegi bölmasa — adminga eslatma, post keyingi safar qayta tekşiriladi
Muhit özgaruvçilari: BOT_TOKEN (majburiy), ADMIN_ID (ixtiyoriy — xabarnoma uçun), CHANNEL (standart: formulaAccaud)
"""
import json, os, re, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE if os.path.exists(os.path.join(HERE, "katalog.json")) else os.path.dirname(HERE)
KATALOG = os.path.join(ROOT, "katalog.json")
STATE = os.path.join(HERE, "state.json")
TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN = os.environ.get("ADMIN_ID", "").strip()
CHANNEL = os.environ.get("CHANNEL", "formulaAccaud").strip().lstrip("@")
TZ = timezone(timedelta(hours=5))

SEC_TAGS = {"excel": "E", "1c": "1C", "qonun": "Q", "jadval": "J", "til": "T", "python": "P"}
SEC_TAG_BY_KEY = {v: "#" + k for k, v in SEC_TAGS.items()}

def api(method, params=None):
    data = urllib.parse.urlencode(params or {}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{TOKEN}/{method}", data=data)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read().decode())
        except Exception: return {"ok": False, "description": str(e)}
    except Exception as e:
        return {"ok": False, "description": str(e)}

def notify(text):
    if ADMIN:
        api("sendMessage", {"chat_id": ADMIN, "text": text, "disable_web_page_preview": "true"})
    print(text)

def load(path, default):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except Exception: return default

def save(path, obj):
    with open(path, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=1)

def next_num(cat, sec):
    nums = [int(i["num"].split("-")[1]) for i in cat["items"] if i["sec"] == sec]
    return f"{sec}-{(max(nums) if nums else 0) + 1:03d}"

def parse_post(text):
    """Matndan sarlavha, tana, teglar va bölimni ajratadi."""
    text = text.strip()
    if text.startswith(("📌", "📎", "📚", "🗂")):      # raqamlangan yoki xizmat posti
        return None
    if "NAVIGATOR" in text or "accaudbot/katalog" in text.lower():   # navigator / eʼlon postlari
        return None
    tags = re.findall(r"#([A-Za-z0-9_]+)", text)
    sec = next((SEC_TAGS[t.lower()] for t in tags if t.lower() in SEC_TAGS), None)
    lines = [l for l in text.split("\n")]
    # oxiridagi faqat teglardan iborat qatorlarni olib taşlaymiz
    while lines and lines[-1].strip() and re.fullmatch(r"(\s*#[A-Za-z0-9_]+\s*)+", lines[-1]):
        lines.pop()
    while lines and not lines[-1].strip(): lines.pop()
    body_lines = [l for l in lines]
    title = body_lines[0].strip() if body_lines else ""
    title = re.sub(r"^[\W_]+", "", title).strip() or title   # boşidagi emoji/belgilarni olib taşlaş
    body = "\n".join(body_lines[1:]).strip()
    return {"title": title[:140], "body": body, "tags": [t.lower() for t in tags], "sec": sec}

def media_info(msg):
    files, photo = [], False
    if "document" in msg: files.append(msg["document"].get("file_name", "fayl"))
    if "photo" in msg: photo = True
    return files, photo

def main():
    if not TOKEN:
        print("BOT_TOKEN yöq"); sys.exit(1)
    cat = load(KATALOG, None)
    if not cat: print("katalog.json topilmadi"); sys.exit(1)
    st = load(STATE, {"offset": 0, "initialized": False, "pending": []})

    r = api("getUpdates", {"offset": st["offset"], "timeout": 0, "allowed_updates": json.dumps(["channel_post", "edited_channel_post"])})
    if not r.get("ok"):
        print("getUpdates xato:", r.get("description")); sys.exit(1)
    updates = r["result"]
    if updates:
        st["offset"] = updates[-1]["update_id"] + 1

    if not st.get("initialized"):
        # Birinçi işga tuşiriş: eski yangilanişlarni ötkazib yuboramiz, faqat offsetni eslab qolamiz
        st["initialized"] = True
        save(STATE, st)
        print(f"Boşlanğiç holat yozildi ({len(updates)} ta eski yangilaniş ötkazildi).")
        return

    posts = [u.get("channel_post") or u.get("edited_channel_post") for u in updates if "channel_post" in u or "edited_channel_post" in u]
    posts = [m for m in posts if (m.get("chat", {}).get("username") or "").lower() == CHANNEL.lower()]
    # oldingi safar tegi bölmagan postlarni qayta tekşiramiz (3 kundan eskisi taşlab yuboriladi)
    now = time.time()
    for p in st.get("pending", []):
        if now - p.get("date", now) > 3 * 86400:
            continue
        if any(m["message_id"] == p["message_id"] for m in posts):
            continue
        if ADMIN:
            # Postning hozirgi matnini olamiz: adminga forward qilib, darhol öçiramiz
            fw = api("forwardMessage", {"chat_id": ADMIN, "from_chat_id": "@" + CHANNEL, "message_id": p["message_id"], "disable_notification": "true"})
            if not fw.get("ok"):
                continue   # post öçirilgan — unutamiz
            cur = fw["result"]
            api("deleteMessage", {"chat_id": ADMIN, "message_id": cur["message_id"]})
            for k in ("text", "caption", "document", "photo"):
                if k in cur: p[k] = cur[k]
                elif k in p: del p[k]
        p["_pending"] = True
        posts.append(p)
    st["pending"] = []
    uniq = {}
    for m in posts: uniq[m["message_id"]] = m     # bir postning oxirgi holati qoladi
    posts = sorted(uniq.values(), key=lambda m: m["message_id"])

    changed = False
    report = []
    for m in posts:
        mid = m["message_id"]
        text = m.get("text") or m.get("caption") or ""
        is_media = "text" not in m
        files, photo = media_info(m)
        date = datetime.fromtimestamp(m.get("date", time.time()), TZ).strftime("%Y-%m-%d")
        if any(mid in it["posts"] for it in cat["items"]):
            continue

        if not text.strip():
            # davomi: oxirgi raqamlangan materialga qöşamiz
            if not cat["items"]: continue
            last = max(cat["items"], key=lambda it: max(it["posts"]))
            k = len(last["posts"])
            last["posts"].append(mid)
            for f in files: last["files"].append({"name": f, "id": mid})
            if photo: last["photo"] = True
            cap = f"📎 {last['num']} · davomi ({k})"
            if is_media: api("editMessageCaption", {"chat_id": "@" + CHANNEL, "message_id": mid, "caption": cap})
            report.append(f"#{mid} → {last['num']} davomi"); changed = True
            continue

        parsed = parse_post(text)
        if parsed is None:
            continue
        if not parsed["sec"]:
            # Post hali turibdimi? (öçirilgan bölsa — unutamiz)
            st["pending"].append({k: m[k] for k in m if k in ("message_id", "date", "text", "caption", "document", "photo", "chat")})
            if not m.get("_pending"):
                notify(f"⚠️ Post #{mid} da bölim tegi yöq. Postga #excel / #1c / #qonun / #jadval / #til / #python dan birini qöşing — keyingi tekşiruvda raqamlanadi (yoki postni öçiring).\nhttps://t.me/{CHANNEL}/{mid}")
            continue

        num = next_num(cat, parsed["sec"])
        sectag = SEC_TAG_BY_KEY[parsed["sec"]].lstrip("#")
        tags = [sectag] + [t for t in parsed["tags"] if t != sectag]
        new_text = f"📌 {num} | {parsed['title']}" + (f"\n\n{parsed['body']}" if parsed["body"] else "") + "\n\n" + " ".join("#" + t for t in tags)
        edited = True
        if is_media and len(new_text) > 1024:
            edited = False
            notify(f"⚠️ {num} (#{mid}): matn 1024 belgidan uzun, rasm/fayl ostiga sığmaydi — qölda tahrirlang:\n\n{new_text[:600]}…")
        else:
            params = {"chat_id": "@" + CHANNEL, "message_id": mid}
            if is_media: params["caption"] = new_text; res = api("editMessageCaption", params)
            else: params["text"] = new_text; res = api("editMessageText", params)
            if not res.get("ok") and "not modified" not in res.get("description", ""):
                edited = False
                notify(f"⚠️ #{mid} tahrirlanmadi: {res.get('description')}")

        cat["items"].append({"num": num, "sec": parsed["sec"], "title": parsed["title"], "body": parsed["body"],
                             "tags": tags, "post": mid, "posts": [mid],
                             "files": [{"name": f, "id": mid} for f in files], "photo": photo, "date": date, "note": ""})
        changed = True
        report.append(f"#{mid} → {num} | {parsed['title']}" + ("" if edited else " (tahrir qölda)"))
        time.sleep(1.2)

    if changed:
        cat["updated"] = datetime.now(TZ).strftime("%Y-%m-%d")
        save(KATALOG, cat)
    save(STATE, st)
    if report:
        notify("✅ Katalog yangilandi:\n" + "\n".join(report) + f"\n\nhttps://t.me/AccaudBot/katalog")
    else:
        print("Yangi post yöq.")

if __name__ == "__main__":
    main()
