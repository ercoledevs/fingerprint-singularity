import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
export async function startServer(port = 0) {
  const server = createServer(async (req, res) => {
    try {
      const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
      const relative = pathname === '/' ? 'examples/index.html' : pathname.startsWith('/dist/') ? pathname.slice(1) : null;
      if (!relative || !['.html', '.js', '.css', '.map'].includes(extname(relative))) { res.writeHead(404).end(); return; }
      const file = resolve(root, relative);
      if (!(file.startsWith(resolve(root, 'dist') + sep) || file === resolve(root, 'examples/index.html'))) { res.writeHead(403).end(); return; }
      const body = await readFile(file);
      res.writeHead(200, { 'Content-Type': extname(file) === '.html' ? 'text/html; charset=utf-8' : extname(file) === '.js' ? 'text/javascript; charset=utf-8' : 'application/json', 'Cache-Control': 'no-store' });
      res.end(body);
    } catch { res.writeHead(404).end(); }
  });
  await new Promise((yes, no) => { server.once('error', no); server.listen(port, '127.0.0.1', yes); });
  return { server, url: `http://127.0.0.1:${server.address().port}`, close: () => new Promise((yes, no) => server.close(e => e ? no(e) : yes())) };
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const local = await startServer(Number(process.env.PORT ?? 4173));
  console.log(`Singularity demo: ${local.url}`);
}
