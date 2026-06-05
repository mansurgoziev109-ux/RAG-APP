#!/usr/bin/env python3
import json, os, hashlib, urllib.request, http.server
from urllib.parse import urlparse

# Fayl yo'llari
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
USERS = os.path.join(DATA, "users.json")
RAGS = os.path.join(DATA, "rags.json")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# Helpers
def load_json(path):
    with open(path, encoding="utf-8") as f: return json.load(f)

def do_search_logic(rag_id, query):
    # Bu yerda pandas ishlatamiz, requirements.txt faylida bo'lishi shart
    import pandas as pd
    rags = load_json(RAGS)
    rag = next((r for r in rags if r["id"] == rag_id), None)
    if not rag: return []
    df = pd.read_excel(os.path.join(DATA, rag["file"]))
    
    # Oddiy qidiruv (Gemini qismini ham shu yerga qo'shish kerak)
    # Hozircha sinov uchun birinchi 3 ta qatorni qaytaramiz
    res = []
    for i, row in df.head(3).iterrows():
        res.append({"id": str(i), "question": str(row.iloc[0]), "answer": "Javob...", "score": 0.9})
    return res

class Handler(http.server.BaseHTTPRequestHandler):
    def json_resp(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            with open(os.path.join(BASE, "app.html"), "rb") as f:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(f.read())
        elif p == "/api/rags":
            self.json_resp(200, {"rags": load_json(RAGS)})
        else: self.json_resp(404, {"error": "Not found"})

    def do_POST(self):
        p = urlparse(self.path).path
        content_length = int(self.headers['Content-Length'])
        body = json.loads(self.rfile.read(content_length))

        if p == "/api/login":
            self.json_resp(200, {"token": "fake-token", "name": "Admin", "role": "admin"})
        elif p == "/api/search":
            results = do_search_logic(body.get("rag_id"), body.get("query"))
            self.json_resp(200, {"results": results})
        else: self.json_resp(404, {"error": "Not found"})

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8000))
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"🚀 Server {PORT}-portda ishlamoqda...")
    server.serve_forever()
