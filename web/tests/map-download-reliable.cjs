/* Local integration fixture only. Requires the documented on-demand test container,
   Chrome and an existing Playwright installation; never targets the live game. */
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const container = process.env.JKA_TEST_CONTAINER;
const base = process.env.JKA_TEST_URL || 'http://127.0.0.1:8282';
if (!container || !['127.0.0.1', 'localhost'].includes(new URL(base).hostname)) {
  throw Error('Requires JKA_TEST_CONTAINER and a localhost test gateway');
}
function python(code) { return execFileSync('podman', ['exec', container, 'python3', '-c', code], { encoding: 'utf8' }); }
function command(text) {
  python(`import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(bytes([255])*4+${JSON.stringify('rcon local-only-test ' + text)}.encode(),('127.0.0.1',29070))`);
}
(async () => {
  command('map mp/duel1');
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'jka-reliable-'));
  const context = await chromium.launchPersistentContext(profile, {
    channel: 'chrome', headless: true, viewport: { width: 915, height: 412 }, hasTouch: true,
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  try {
    await context.request.post(base + '/login', { form: { password: 'local-only-test' } });
    const page = context.pages()[0];
    await page.goto(base + '/?mobile&fps=10');
    await page.waitForFunction(() => !document.getElementById('play').disabled, null, { polling: 100, timeout: 120000 });
    await page.evaluate(() => {
      window.testMaps = [];
      const original = window.jkaEnsureMap;
      window.jkaEnsureMap = (map, ticket) => { window.testMaps.push(map); return original(map, ticket); };
    });
    await page.locator('#name').fill('ReliableRegression');
    await page.locator('#play').click();
    const active = async map => {
      await page.waitForFunction(m => {
        const log = document.getElementById('log').textContent;
        return log.includes('reliable command was cycled out') ||
          (window.testMaps.includes(m) && Module.HEAP32[Module._web_state() >> 2] === 8);
      }, map, { polling: 100, timeout: 120000 });
      assert(!(await page.locator('#log').textContent()).includes('reliable command was cycled out'), 'reliable command history overflow');
    };
    await active('mp/duel1');
    const target = python(`import json,zipfile
from pathlib import Path
root=Path('/data/web/map-paks');c=json.loads((root/'bundles.json').read_text())
for n in c['profiles']['mobile']['maps']['hoth2']:
 with zipfile.ZipFile(root/n) as z:
  if 'maps/hoth2.bsp' in z.namelist():print(n);break
`).trim();
    assert(target.startsWith('jka-bundle-'));
    await page.route('**/base/' + target + '*', async route => {
      await new Promise(resolve => setTimeout(resolve, 35000));
      await route.continue().catch(() => {});
    });
    // One RCON exec avoids RCON rate limits. wait keeps the server's unacknowledged
    // queue below its limit while more than 128 acknowledged commands accumulate
    // without a cgame consumer on the downloading client.
    python(`from pathlib import Path
lines=['map hoth2','wait 30']+[line for i in range(165) for line in ('say load-'+str(i),'wait 2')]
Path('/tmp/home/japlus/map-flood.cfg').write_text(chr(10).join(lines)+chr(10))`);
    command('exec map-flood.cfg');
    await active('hoth2');
    console.log('PASS: hoth2 loads after 35 seconds and 165 reliable server messages');
  } finally {
    await context.close();
    fs.rmSync(profile, { recursive: true, force: true });
    command('map mp/duel1');
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
