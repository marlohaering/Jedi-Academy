/* Async map preparation; never resumes a superseded engine gamestate. */
class MapAssets {
  constructor(options) { this.o = options; this.installed = new Set(); this.map = null; this.isIndexed = false; this.job = null; }
  seed(map, packages) { this.map = map; this.isIndexed = true; this.installed = new Set(packages.map(p => p.name)); }
  request(map, ticket) {
    if (this.job && this.job.map !== map) {
      this.job.controller.abort(); this.job = null;
    }
    if (map === this.map) return this.isIndexed ? true : 2;
    if (this.job) { this.job.ticket = ticket; return false; }
    const job = { map, ticket, controller: new AbortController() };
    this.job = job;
    this.prepare(job);
    return false;
  }
  indexed(map) { if (map === this.map) this.isIndexed = true; }
  cancel(ticket) {
    if (this.job && this.job.ticket === ticket) { this.job.controller.abort(); this.job = null; }
  }
  async prepare(job) {
    const current = () => this.job === job && !job.controller.signal.aborted;
    try {
      const manifest = await this.o.manifest(job.map, job.controller.signal);
      if (!current()) return;
      const packages = this.o.mobile ? manifest.mobile : manifest.paks;
      if (!Array.isArray(packages) || !packages.length) throw Error('No map packages available');
      const wanted = new Set(packages.map(p => p.name));
      const missing = packages.filter(p => !this.installed.has(p.name));
      let done = 0, total = missing.reduce((n, p) => n + p.size, 0);
      this.o.progress(job.map, done, total);
      // Keep newly fetched bytes outside MEMFS until the whole set has succeeded.
      const loaded = [];
      for (const pak of missing) {
        const bytes = await this.o.load(pak, n => {
          if (current()) this.o.progress(job.map, done += n, total);
        }, job.controller.signal);
        if (!current()) return;
        loaded.push([pak, bytes]);
      }
      if (!current()) return;
      for (const [pak, bytes] of loaded) { this.o.mount(pak.name, bytes); this.installed.add(pak.name); }
      // Engine FS_Restart will close the old pk3 handles; Cache Storage keeps prior maps.
      for (const name of this.installed) {
        if (!wanted.has(name)) { this.o.unmount(name); this.installed.delete(name); }
      }
      this.map = job.map; this.isIndexed = false; this.job = null;
      this.o.ready(job.ticket, true);
    } catch (error) {
      if (!current()) return;
      this.job = null;
      this.o.error(job.map, error);
      this.o.ready(job.ticket, false);
    }
  }
}
if (typeof module !== 'undefined' && module.exports) module.exports = MapAssets;
else window.MapAssets = MapAssets;
