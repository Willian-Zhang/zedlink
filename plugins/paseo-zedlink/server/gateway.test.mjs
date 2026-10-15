import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile, chmod, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { createServer } from "node:https";
import { GatewayClient } from "./connection.mjs";

test("TLS gateway identity is checked before bearer token; redirects are refused", async () => {
  const dir = await mkdtemp(join(tmpdir(), "zedlink-paseo-test-"));
  const cert = join(dir, "cert.pem"), key = join(dir, "key.pem"), tokenFile = join(dir, "device.json");
  let server;
  try {
    execFileSync("openssl", ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key,
      "-out", cert, "-days", "1", "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], { stdio: "ignore" });
    await writeFile(tokenFile, JSON.stringify({ gateway_id: "expected", device_id: "device", token: "secret" }));
    await chmod(tokenFile, 0o600);
    const received = [];
    let actualId = "other";
    server = createServer({ key: await readFile(key), cert: await readFile(cert) }, (req, res) => {
      received.push({ url: req.url, authorization: req.headers.authorization });
      if (req.url === "/v1/gateway") { res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify({ version: 1, gateway_id: actualId })); return; }
      res.writeHead(302, { Location: "https://example.com/" }); res.end();
    });
    await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
    const port = server.address().port;
    const gateway = new GatewayClient({ baseUrl: `https://127.0.0.1:${port}`, targetId: "primary", credentialFile: tokenFile, caFile: cert });
    await assert.rejects(gateway.list(), /identity changed/);
    assert.deepEqual(received.map((item) => item.authorization), [undefined]);
    actualId = "expected";
    await assert.rejects(gateway.list(), /redirect refused/);
    assert.equal(received.at(-1).authorization, "Bearer secret");
    await chmod(tokenFile, 0o644);
    await assert.rejects(gateway.list(), /private regular file/);
  } finally {
    if (server) await new Promise((resolve) => server.close(resolve));
    await rm(dir, { recursive: true, force: true });
  }
});
