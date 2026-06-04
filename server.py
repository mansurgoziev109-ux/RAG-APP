#!/usr/bin/env python3
"""
TBC RAG Qidiruv Tizimi — Backend Server
"""
import json, os, hashlib, secrets, urllib.request, http.server
from urllib.parse import urlparse, parse_qs

BASE   = os.path.dirname(os.path.abspath(__file__))
DATA   = os.path.join(BASE, "data")
USERS  = os.path.join(DATA, "users.json")
RAGS   = os.path.join(DATA, "rags.json")

GEMINI_KEY = ""        
SESSIONS   = {}        
QS_CACHE   = {}        

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

# ── HTTP handler (Qisqartirilgan) ─────────────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def json_resp(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        self.wfile.write(body)
    def html_resp(self, body_bytes):
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body_bytes)
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Headers","*")
        self.end_headers()
    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/" or p == "/index.html":
            with open(os.path.join(BASE, "app.html"),"rb") as f: self.html_resp(f.read())
        elif p == "/api/rags":
            rags = load_json(RAGS)
            self.json_resp(200, {"rags": rags, "role": "user"})
        else: self.json_resp(404, {"error":"Not found"})
    def do_POST(self):
        # SEARCH logic (qolgan qismlar avvalgidek qolaveradi)
        # ...
        pass

# ── main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 Server ishga tushirildi...")
    GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
    
    if not GEMINI_KEY:
        print("DIQQAT: GEMINI_API_KEY topilmadi!")

    if os.path.exists(RAGS):
        for r in load_json(RAGS):
            load_questions(r["id"])

    PORT = int(os.environ.get("PORT", 8000))
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Server port {PORT} da ishlamoqda")
    server.serve_forever()
