#!/usr/bin/env python3
"""
TBC RAG Qidiruv Tizimi — Backend Server
Ishlatish:
  pip install pandas openpyxl
  python3 server.py
  http://localhost:8000
"""
import json, os, hashlib, secrets, urllib.request, http.server
from urllib.parse import urlparse, parse_qs

BASE   = os.path.dirname(os.path.abspath(__file__))
DATA   = os.path.join(BASE, "data")
USERS  = os.path.join(DATA, "users.json")
RAGS   = os.path.join(DATA, "rags.json")

GEMINI_KEY = ""          # server.py ishga tushganda so'raladi
SESSIONS   = {}          # token -> {username, role, name}
QS_CACHE   = {}          # rag_id -> list of questions

# ── helpers ──────────────────────────────────────────────────────────────────
def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def load_questions(rag_id):
    if rag_id in QS_CACHE:
        return QS_CACHE[rag_id]
    rags = load_json(RAGS)
    rag  = next((r for r in rags if r["id"] == rag_id), None)
    if not rag:
        return []
    path = os.path.join(DATA, rag["file"])
    if not os.path.exists(path):
        return []
    try:
        import pandas as pd
        df = pd.read_excel(path)
        qs = []
        for _, row in df.iterrows():
            qid = str(row.get("№","")).strip()
            ru  = str(row.get("Вопрос на русском языке (самая частая формулировка)","")).strip()
            uz  = str(row.get("Вопрос на узбекском языке (самая частая формулировка)","")).strip()
            if qid and qid != "nan":
                qs.append({
                    "id":  qid,
                    "ru": (ru if ru!="nan" else "").split("/")[0].strip()[:150],
                    "uz": (uz if uz!="nan" else "").split("/")[0].strip()[:150],
                })
        QS_CACHE[rag_id] = qs
        print(f"  ✓ {rag['name']}: {len(qs)} savol yuklandi")
        return qs
    except Exception as e:
        print(f"  ✗ Excel xato ({rag['file']}): {e}")
        return []

def gemini_search(query, questions, api_key):
    q_list = "\n".join(f"{q['id']}|{q['uz']}|{q['ru']}" for q in questions)
    prompt = (
        f"Bank FAQ semantic search. Questions (id|uz|ru):\n{q_list}\n\n"
        f"User query: \"{query}\"\n\n"
        "Find top 3-5 semantically similar questions. "
        "Return ONLY valid JSON array, no markdown:\n"
        '[{"id":"1","uz":"...","ru":"...","mos":85}]'
    )
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-flash:generateContent?key={api_key}"
    )
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 800}
    }).encode()
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    text = text.replace("```json","").replace("```","").strip()
    return json.loads(text)

# ── HTTP handler ──────────────────────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def json_resp(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        self.wfile.write(body)

    def html_resp(self, body_bytes):
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length", len(body_bytes))
        self.end_headers()
        self.wfile.write(body_bytes)

    def get_token(self):
        auth = self.headers.get("Authorization","")
        return auth.replace("Bearer ","").strip()

    def require_auth(self):
        tok = self.get_token()
        return SESSIONS.get(tok)

    def read_body(self):
        n = int(self.headers.get("Content-Length",0))
        return json.loads(self.rfile.read(n)) if n else {}

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","*")
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path

        # ── Serve frontend ──
        if p == "/" or p == "/index.html":
            html_path = os.path.join(BASE, "app.html")
            if os.path.exists(html_path):
                with open(html_path,"rb") as f:
                    self.html_resp(f.read())
            else:
                self.html_resp(b"<h2>app.html topilmadi. Papkaga qo'ying.</h2>")
            return

        # ── RAG list ──
        if p == "/api/rags":
            sess = self.require_auth()
            if not sess:
                return self.json_resp(401, {"error":"Avtorizatsiya kerak"})
            rags = load_json(RAGS)
            return self.json_resp(200, {"rags": rags, "role": sess["role"]})

        # ── Questions for RAG ──
        if p.startswith("/api/questions/"):
            sess = self.require_auth()
            if not sess:
                return self.json_resp(401, {"error":"Avtorizatsiya kerak"})
            rag_id = p.split("/")[-1]
            qs = load_questions(rag_id)
            return self.json_resp(200, {"questions": qs, "count": len(qs)})

        self.json_resp(404, {"error":"Not found"})

    def do_POST(self):
        p = urlparse(self.path).path

        # ── Login ──
        if p == "/api/login":
            body  = self.read_body()
            users = load_json(USERS)
            uname = body.get("username","").strip()
            pw    = body.get("password","").strip()
            user  = users.get(uname)
            # Accept plain or hashed
            ok = user and (user["password"] == pw or
                           user["password"] == hash_pw(pw))
            if not ok:
                return self.json_resp(401, {"error":"Login yoki parol noto'g'ri"})
            token = secrets.token_hex(24)
            SESSIONS[token] = {"username": uname, "role": user["role"], "name": user["name"]}
            return self.json_resp(200, {"token": token, "role": user["role"], "name": user["name"]})

        # ── Logout ──
        if p == "/api/logout":
            tok = self.get_token()
            SESSIONS.pop(tok, None)
            return self.json_resp(200, {"ok": True})

        # ── Search ──
        if p == "/api/search":
            sess = self.require_auth()
            if not sess:
                return self.json_resp(401, {"error":"Avtorizatsiya kerak"})
            body   = self.read_body()
            query  = body.get("query","").strip()
            rag_id = body.get("rag_id","").strip()
            if not query:
                return self.json_resp(400, {"error":"query bo'sh"})
            if not GEMINI_KEY:
                return self.json_resp(500, {"error":"Server Gemini kalitisiz ishlamayapti"})
            qs = load_questions(rag_id)
            if not qs:
                return self.json_resp(400, {"error":"Bu RAG bo'sh yoki fayl topilmadi"})
            try:
                results = gemini_search(query, qs, GEMINI_KEY)
                return self.json_resp(200, {"results": results})
            except Exception as e:
                return self.json_resp(500, {"error": str(e)})

        # ── Admin: add RAG ──
        if p == "/api/admin/add-rag":
            sess = self.require_auth()
            if not sess or sess["role"] != "admin":
                return self.json_resp(403, {"error":"Faqat admin"})
            body = self.read_body()
            name = body.get("name","").strip()
            file = body.get("file","").strip()
            desc = body.get("description","").strip()
            if not name or not file:
                return self.json_resp(400, {"error":"name va file kerak"})
            if not os.path.exists(os.path.join(DATA, file)):
                return self.json_resp(400, {"error":f"Fayl topilmadi: data/{file}"})
            rags = load_json(RAGS)
            from datetime import date
            new_id = "rag_" + name.lower().replace(" ","_").replace(".","_")
            rags.append({"id": new_id, "name": name, "file": file,
                         "description": desc, "added": str(date.today())})
            save_json(RAGS, rags)
            QS_CACHE.pop(new_id, None)
            return self.json_resp(200, {"ok": True, "id": new_id})

        # ── Admin: delete RAG ──
        if p == "/api/admin/delete-rag":
            sess = self.require_auth()
            if not sess or sess["role"] != "admin":
                return self.json_resp(403, {"error":"Faqat admin"})
            body   = self.read_body()
            rag_id = body.get("id","").strip()
            rags   = load_json(RAGS)
            rags   = [r for r in rags if r["id"] != rag_id]
            save_json(RAGS, rags)
            QS_CACHE.pop(rag_id, None)
            return self.json_resp(200, {"ok": True})

        # ── Admin: add user ──
        if p == "/api/admin/add-user":
            sess = self.require_auth()
            if not sess or sess["role"] != "admin":
                return self.json_resp(403, {"error":"Faqat admin"})
            body  = self.read_body()
            uname = body.get("username","").strip()
            pw    = body.get("password","").strip()
            name  = body.get("name","").strip()
            role  = body.get("role","user")
            if not uname or not pw:
                return self.json_resp(400, {"error":"username va password kerak"})
            users = load_json(USERS)
            if uname in users:
                return self.json_resp(400, {"error":"Bu username allaqachon mavjud"})
            users[uname] = {"password": pw, "role": role, "name": name or uname}
            save_json(USERS, users)
            return self.json_resp(200, {"ok": True})

        # ── Admin: delete user ──
        if p == "/api/admin/delete-user":
            sess = self.require_auth()
            if not sess or sess["role"] != "admin":
                return self.json_resp(403, {"error":"Faqat admin"})
            body  = self.read_body()
            uname = body.get("username","").strip()
            if uname == "admin":
                return self.json_resp(400, {"error":"Admin o'chirib bo'lmaydi"})
            users = load_json(USERS)
            users.pop(uname, None)
            save_json(USERS, users)
            return self.json_resp(200, {"ok": True})

        # ── Admin: list users ──
        if p == "/api/admin/users":
            sess = self.require_auth()
            if not sess or sess["role"] != "admin":
                return self.json_resp(403, {"error":"Faqat admin"})
            users = load_json(USERS)
            out = [{"username": k, "name": v["name"], "role": v["role"]}
                   for k, v in users.items()]
            return self.json_resp(200, {"users": out})

        self.json_resp(404, {"error":"Not found"})

# ── main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  TBC RAG Qidiruv Tizimi — Server")
    print("=" * 55)

    key = os.environ.get("GEMINI_API_KEY","")
    if not key:
        key = input("\nGemini API kalitini kiriting: ").strip()
    GEMINI_KEY = key

    # Preload all rags
    print("\nRAG fayllar yuklanmoqda...")
    for r in load_json(RAGS):
        load_questions(r["id"])

    PORT = 8000
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"\n🚀 Server ishga tushdi → http://localhost:{PORT}")
    print("   Admin login: admin / admin123")
    print("   To'xtatish: Ctrl+C\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer to'xtatildi.")
