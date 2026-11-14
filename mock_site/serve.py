import http.server, socketserver, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
class H(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.path = "/index.html"; return super().do_GET()
    def log_message(self,*a): pass
socketserver.TCPServer.allow_reuse_address=True
socketserver.TCPServer(("127.0.0.1",8765),H).serve_forever()
