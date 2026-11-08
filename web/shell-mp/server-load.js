/* Server diagnostics stay independent of the engine and never intercept input. */
(() => {
  const label = document.getElementById('server-load');
  let lastSuccess = 0;
  const unknown = () => {
    label.dataset.level = 'warn';
    label.textContent = 'Server · unknown / stale';
  };
  const known = value => typeof value === 'number' && Number.isFinite(value);
  async function poll() {
    try {
      const response = await fetch('/base/metrics.json', {
        cache: 'no-store', signal: AbortSignal.timeout(4000)
      });
      if (!response.ok) throw new Error('Metrics unavailable');
      const m = await response.json();
      if (!known(m.ageSeconds) || m.ageSeconds > 6) throw new Error('Stale metrics');
      lastSuccess = performance.now();
      const cpu = known(m.cpuPercent) ? Math.round(m.cpuPercent) + '%' : '?';
      const ram = known(m.ramMb) ? Math.round(m.ramMb) + ' MiB' : '?';
      const reply = known(m.responseMs) ? Math.round(m.responseMs) + ' ms' : '?';
      const bad = m.online === false || m.cpuPercent >= 95 || m.responseMs >= 250;
      const warn = m.online !== true || !known(m.cpuPercent) || !known(m.ramMb) ||
        !known(m.responseMs) || m.cpuPercent >= 80 || m.responseMs >= 100;
      label.dataset.level = bad ? 'bad' : warn ? 'warn' : 'ok';
      const state = m.online === false ? 'no reply' : bad ? 'high load / delay' : warn ? 'warning' : '';
      label.textContent = `Server · CPU ${cpu} · RAM ${ram} · Reply ${reply}${state ? ' · ' + state : ''}`;
    } catch (_) {
      lastSuccess = 0;
      unknown();
    } finally {
      setTimeout(poll, 2000); // no overlapping requests, even when the game server stalls
    }
  }
  setInterval(() => {
    if (!lastSuccess || performance.now() - lastSuccess > 6500) unknown();
  }, 1000);
  poll();
})();
