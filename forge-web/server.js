const express = require('express');
const next = require('next');
const { Readable } = require('stream');

const port = parseInt(process.env.PORT, 10) || 3000;
const dev = process.env.NODE_ENV !== 'production';
const pythonApiBaseUrl = process.env.PYTHON_API_BASE_URL || 'http://127.0.0.1:8001';
const app = next({ dev });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  const server = express();

  server.use('/api', express.raw({ type: '*/*', limit: '4mb' }));

  server.all('/api/:path(*)', async (req, res) => {
    try {
      const targetUrl = new URL(req.originalUrl, pythonApiBaseUrl);
      const headers = { ...req.headers };
      delete headers.host;
      delete headers.connection;
      delete headers['content-length'];

      const upstream = await fetch(targetUrl, {
        method: req.method,
        headers,
        body: req.method === 'GET' || req.method === 'HEAD' ? undefined : req.body,
        duplex: 'half'
      });

      res.status(upstream.status);
      upstream.headers.forEach((value, key) => {
        if (key.toLowerCase() === 'transfer-encoding') {
          return;
        }
        res.setHeader(key, value);
      });

      if (!upstream.body) {
        res.end();
        return;
      }

      Readable.fromWeb(upstream.body).pipe(res);
    } catch (error) {
      res.status(502).json({
        ok: false,
        error: 'python_api_unreachable',
        detail: error instanceof Error ? error.message : String(error)
      });
    }
  });

  server.all('*', (req, res) => {
    return handle(req, res);
  });

  server.listen(port, (err) => {
    if (err) throw err;
    console.log(`> Ready on http://localhost:${port}`);
  });
});
