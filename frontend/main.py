import http.server
import socketserver
import threading
import webview

PORT = 8000
DIRECTORY = "dist"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)


def start_server():
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()


threading.Thread(target=start_server).start()

webview.create_window(
    title="Naga Agent",
    url=f"http://localhost:{PORT}",
    min_size=(1200, 800),
)

webview.start()
