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
import re
import time
import zipfile

from metrics import ProcessMetrics

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


async def sample_metrics(app):
    sampler = ProcessMetrics(os.environ.get('GAME_PID', 'unknown'))
    while True:
        values = sampler.sample(time.monotonic())
        started = time.monotonic()
        try:
            await query_info()
            values.update(online=True, responseMs=round((time.monotonic() - started) * 1000, 1))
        except (OSError, ValueError, asyncio.TimeoutError):
            values.update(online=False, responseMs=None)
        app['server_metrics'].update(values, sampledAt=time.monotonic())
        await asyncio.sleep(2)


async def metrics_lifecycle(app):
    task = asyncio.create_task(sample_metrics(app))
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def server_metrics(request):
    values = dict(request.app['server_metrics'])
    sampled_at = values.pop('sampledAt', None)
    values['ageSeconds'] = None if sampled_at is None else round(time.monotonic() - sampled_at, 1)
    return web.json_response(values, headers={'Cache-Control': 'no-store'})


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


class _InfoQuery(asyncio.DatagramProtocol):
    def __init__(self, fut):
        self.fut = fut

    def datagram_received(self, data, addr):
        if not self.fut.done():
            self.fut.set_result(data)


async def query_info():
    """getinfo on the game server: hostname, map, player count, mod (for the loading screen)"""
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    transport, _ = await loop.create_datagram_endpoint(lambda: _InfoQuery(fut), remote_addr=GAME)
    try:
        transport.sendto(b'\xff\xff\xff\xffgetinfo web')
        data = await asyncio.wait_for(fut, 1.5)
    finally:
        transport.close()
    text = data[4:].decode('latin-1')
    if not text.startswith('infoResponse'):
        raise ValueError('unexpected reply')
    parts = text.split('\n', 1)[1].strip().split('\\')[1:]
    return dict(zip(parts[::2], parts[1::2]))


_pk3_files = {}
_map_titles = None


def map_title(mapname):
    """longname of a map from the scripts/*.arena files in the client pk3 (e.g. mp/ffa3 -> Tatooine City)"""
    global _map_titles
    if _map_titles is None:
        _map_titles = {}
        for p in pak_list(False):
            try:
                with zipfile.ZipFile(os.path.join(DATA_DIR, p['name'])) as z:
                    for n in z.namelist():
                        if n.lower().startswith('scripts/') and n.lower().endswith('.arena'):
                            for block in re.findall(r'\{([^}]*)\}', z.read(n).decode('latin-1')):
                                m, t = re.search(r'map\s+"([^"]+)"', block), re.search(r'longname\s+"([^"]+)"', block)
                                if m and t:
                                    _map_titles[m.group(1).lower()] = t.group(1)
            except (OSError, zipfile.BadZipFile):
                pass
    return _map_titles.get(mapname.lower(), '')


def pk3_file(path):
    """a file from the desktop client pk3 (later pk3s win), cached in memory; None if missing"""
    want = path.lower()
    if want not in _pk3_files:
        data = None
        for p in pak_list(False):
            try:
                with zipfile.ZipFile(os.path.join(DATA_DIR, p['name'])) as z:
                    for n in z.namelist():
                        if n.lower() == want:
                            data = z.read(n)
            except (OSError, zipfile.BadZipFile):
                pass
        _pk3_files[want] = data
    return _pk3_files[want]


async def pk3_jpg(path):
    data = await asyncio.get_running_loop().run_in_executor(None, pk3_file, path)
    if not data:
        raise web.HTTPNotFound()
    return web.Response(body=data, content_type='image/jpeg', headers={'Cache-Control': 'private, max-age=3600'})


async def info(request):
    try:
        i = await query_info()
    except (OSError, ValueError, asyncio.TimeoutError):
        return web.json_response({'online': False}, headers={'Cache-Control': 'no-cache'})
    return web.json_response({
        'online': True, 'hostname': i.get('hostname', ''), 'map': i.get('mapname', ''),
        'mapTitle': await asyncio.get_running_loop().run_in_executor(None, map_title, i.get('mapname', '')),
        'players': int(i.get('clients', 0) or 0), 'maxPlayers': int(i.get('sv_maxclients', 0) or 0),
        'mod': i.get('game', ''),
    }, headers={'Cache-Control': 'no-cache'})


async def levelshot_jpg(request):
    mapname = request.match_info['map']
    if '..' in mapname or not all(c.isalnum() or c in '/_-' for c in mapname):
        raise web.HTTPNotFound()
    return await pk3_jpg(f'levelshots/{mapname}.jpg')


async def character_icon(request):
    """portrait of a player model (phone character picker, shell-mp/touch.js)"""
    model = request.match_info['model']
    if not all(c.isalnum() or c == '_' for c in model):
        raise web.HTTPNotFound()
    return await pk3_jpg(f'models/players/{model}/icon_default.jpg')


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
    app['server_metrics'] = {'online': None, 'cpuPercent': None, 'ramMb': None, 'responseMs': None}
    app.cleanup_ctx.append(metrics_lifecycle)
    app.add_routes([
        web.get('/login', login_get), web.post('/login', login_post),
        web.get('/healthz', healthz),
        web.get('/base/metrics.json', server_metrics),
        web.get('/ws', ws_bridge),
        web.get('/base/manifest.json', manifest),
        web.get('/base/info.json', info),
        web.get('/base/levelshot/{map:.+}.jpg', levelshot_jpg),
        web.get('/base/icon/{model}.jpg', character_icon),
        web.get('/base/{name}', pak),
        web.get('/', static), web.get('/{path:.+}', static),
    ])
    return app


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
    web.run_app(make_app(), port=int(os.environ.get('PORT', '8080')), access_log=None)
