#!/usr/bin/env python3
"""Password-protected web front door for the browser Jedi Academy MP server.

- serves the WebAssembly client and the game data (pk3) to logged-in users
- bridges each browser WebSocket to a UDP socket on the local OpenJK dedicated server

Browsers cannot speak UDP. Emscripten's socket layer sends every UDP datagram as one
binary WebSocket message, so each WebSocket here becomes one UDP "client" of openjkded.

Environment:
  JKA_PASSWORD   site password (required)
  JKA_SECRET     cookie signing key (default: derived from the password)
  GAME_HOST/PORT dedicated server address (default 127.0.0.1:29070)
  WEB_DIR        client files (index.html, openjk_mp.js/.wasm)
  CLIENT_DATA_DIR directory holding the (repacked) client pk3 files served under /base/
                 (*-mobile.pk3: phone variant, listed separately in the manifest)
  PORT           HTTP listen port (default 8080)
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import time

from aiohttp import WSMsgType, web

log = logging.getLogger('gateway')

PASSWORD = os.environ.get('JKA_PASSWORD', '')
SECRET = (os.environ.get('JKA_SECRET') or ('jka:' + PASSWORD)).encode()
GAME = (os.environ.get('GAME_HOST', '127.0.0.1'), int(os.environ.get('GAME_PORT', '29070')))
WEB_DIR = os.environ.get('WEB_DIR', os.path.join(os.path.dirname(__file__), '..', 'dist-mp'))
DATA_DIR = os.environ.get('CLIENT_DATA_DIR', '/data/web')
COOKIE = 'jka_session'
SESSION_DAYS = 30
# Emscripten announces the socket's bound port in a first message: FF FF FF FF 'port' hi lo
PORT_MSG = b'\xff\xff\xff\xffport'

LOGIN_PAGE = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Jedi Academy Server</title>
<style>
:root{--bg:#05070c;--fg:#d8e2f0;--muted:#7d8aa0;--accent:#4aa3ff}
html,body{margin:0;height:100%;background:radial-gradient(ellipse at center,#0d1a33 0%,var(--bg) 70%);color:var(--fg);
font:15px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}
main{min-height:100%;display:flex;align-items:center;justify-content:center;padding:0 16px;box-sizing:border-box}
form{width:100%;max-width:340px;text-align:center}
h1{margin:0 0 18px;font-size:26px;letter-spacing:.06em;color:#ffe81f;text-transform:uppercase}
input,button{width:100%;box-sizing:border-box;padding:11px 12px;font-size:15px;border-radius:6px;margin-top:10px}
input{background:#0c1220;color:var(--fg);border:1px solid #23324d}
button{background:transparent;color:var(--fg);border:1px solid var(--accent);cursor:pointer}
button:hover{background:var(--accent);color:#000}
.err{color:#ff7a7a;min-height:1.4em;margin-top:10px}
</style></head><body><main><form method="post" action="/login">
<h1>Jedi Academy</h1>
<input type="password" name="password" placeholder="Server password" autofocus required>
<button type="submit">Enter</button><div class="err">%ERR%</div>
</form></main></body></html>'''


def make_token(now=None):
    exp = int((now or time.time()) + SESSION_DAYS * 86400)
    sig = hmac.new(SECRET, str(exp).encode(), hashlib.sha256).hexdigest()
    return f'{exp}.{sig}'


def valid_token(token):
    try:
        exp, sig = token.split('.', 1)
        good = hmac.new(SECRET, exp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, good) and int(exp) > time.time()
    except (ValueError, AttributeError):
        return False


# fetched without the session cookie (the browser loads the manifest and icons without credentials)
PUBLIC = ('/login', '/healthz', '/manifest.webmanifest', '/sw.js', '/icon-192.png', '/icon-512.png')


@web.middleware
async def auth(request, handler):
    if request.path in PUBLIC or valid_token(request.cookies.get(COOKIE, '')):
        return await handler(request)
    if request.path == '/' or request.path.endswith('.html'):
        raise web.HTTPFound('/login')
    raise web.HTTPUnauthorized()


async def login_get(request):
    return web.Response(text=LOGIN_PAGE.replace('%ERR%', ''), content_type='text/html')


async def login_post(request):
    form = await request.post()
    if PASSWORD and hmac.compare_digest(str(form.get('password', '')), PASSWORD):
        resp = web.HTTPFound('/')
        resp.set_cookie(COOKIE, make_token(), max_age=SESSION_DAYS * 86400, httponly=True,
                        samesite='Strict', secure=request.secure or request.headers.get('X-Forwarded-Proto') == 'https')
        raise resp
    await asyncio.sleep(1)  # slow down guessing
    return web.Response(text=LOGIN_PAGE.replace('%ERR%', 'Wrong password'), content_type='text/html', status=401)


async def healthz(request):
    return web.Response(text='ok')


def pak_list(mobile):
    """client pk3s; *-mobile.pk3 is the phone variant (web/MOBILE.md), the rest is for desktop"""
    out = []
    if os.path.isdir(DATA_DIR):
        for name in sorted(os.listdir(DATA_DIR)):
            low = name.lower()
            if low.endswith('.pk3') and low.endswith('-mobile.pk3') == mobile:
                st = os.stat(os.path.join(DATA_DIR, name))
                out.append({'name': name, 'size': st.st_size, 'version': f'{st.st_size:x}-{int(st.st_mtime):x}'})
    return out


async def manifest(request):
    return web.json_response({'paks': pak_list(False), 'mobile': pak_list(True)},
                             headers={'Cache-Control': 'no-cache'})


async def pak(request):
    name = request.match_info['name']
    if '/' in name or '..' in name or not name.lower().endswith('.pk3'):
        raise web.HTTPNotFound()
    path = os.path.join(DATA_DIR, name)
    if not os.path.isfile(path):
        raise web.HTTPNotFound()
    return web.FileResponse(path, headers={'Cache-Control': 'private, max-age=31536000, immutable'})


class UdpRelay(asyncio.DatagramProtocol):
    def __init__(self, ws):
        self.ws = ws
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if not self.ws.closed:
            asyncio.ensure_future(self.ws.send_bytes(data))


async def ws_bridge(request):
    ws = web.WebSocketResponse(protocols=('binary',), max_msg_size=1 << 20, heartbeat=30)
    await ws.prepare(request)
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(lambda: UdpRelay(ws), remote_addr=GAME)
    peer = request.headers.get('Fly-Client-IP') or request.remote
    log.info('ws open %s -> udp %s', peer, transport.get_extra_info('sockname'))
    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                data = msg.data
                if data.startswith(PORT_MSG) and len(data) == 10:
                    continue
                transport.sendto(data)
            elif msg.type == WSMsgType.ERROR:
                break
    finally:
        transport.close()
        log.info('ws closed %s', peer)
    return ws


async def static(request):
    rel = request.match_info.get('path') or 'index.html'
    path = os.path.normpath(os.path.join(WEB_DIR, rel))
    if not path.startswith(os.path.normpath(WEB_DIR)) or not os.path.isfile(path):
        raise web.HTTPNotFound()
    headers = {'Cache-Control': 'no-cache'}
    resp = web.FileResponse(path, headers=headers)
    if path.endswith('.wasm'):
        resp.content_type = 'application/wasm'
    elif path.endswith('.webmanifest'):
        resp.content_type = 'application/manifest+json'
    return resp


def make_app():
    if not PASSWORD:
        raise SystemExit('JKA_PASSWORD must be set')
    app = web.Application(middlewares=[auth])
    app.add_routes([
        web.get('/login', login_get), web.post('/login', login_post),
        web.get('/healthz', healthz),
        web.get('/ws', ws_bridge),
        web.get('/base/manifest.json', manifest),
        web.get('/base/{name}', pak),
        web.get('/', static), web.get('/{path:.+}', static),
    ])
    return app


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
    web.run_app(make_app(), port=int(os.environ.get('PORT', '8080')), access_log=None)
