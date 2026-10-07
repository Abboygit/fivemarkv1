import sys
sys.path.insert(0, r'C:\Users\MY PC\Documents\Default Project\Five mark v1')
from src.dashboard.server import loop, Handler, PORT
from http.server import ThreadingHTTPServer
import threading

print('Starting loop thread...')
t = threading.Thread(target=loop, daemon=True)
t.start()

print('Starting HTTP server...')
server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
server.serve_forever()