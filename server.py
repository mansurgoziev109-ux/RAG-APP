import http.server
import socketserver
import os
import json

PORT = int(os.environ.get("PORT", 8000))

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = 'app.html'
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode())

print(f"Server {PORT} portda ishga tushdi...")
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
