export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // ---- SENSORES ----
    if (url.pathname === "/insert" && request.method === "POST") {
      const body = await request.json();               // { sensor, valor }
      const sensor = body.sensor || "temp";
      const valor  = Number(body.valor ?? 0);
      await env.DB.prepare(
        "INSERT INTO leituras (sensor, valor, timestamp) VALUES (?, ?, ?)"
      ).bind(sensor, valor, Date.now()).run();
      return new Response(`OK: ${sensor}=${valor}`);
    }

    if (url.pathname === "/get") {
      const sensor = url.searchParams.get("sensor") || "temp";
      const row = await env.DB.prepare(
        "SELECT valor, timestamp FROM leituras WHERE sensor = ? ORDER BY timestamp DESC LIMIT 1"
      ).bind(sensor).first();
      if (!row) return new Response("Nenhum valor encontrado", { status: 404 });
      return Response.json(row);
    }

    if (url.pathname === "/list") {
      const sensor = url.searchParams.get("sensor") || "temp";
      const { results } = await env.DB.prepare(
        "SELECT valor, timestamp FROM leituras WHERE sensor = ? ORDER BY timestamp DESC LIMIT 50"
      ).bind(sensor).all();
      return Response.json(results);
    }

    if (url.pathname === "/media") {
      const sensor = url.searchParams.get("sensor") || "temp";
      const row = await env.DB.prepare(
        `SELECT AVG(valor) AS media, MIN(valor) AS minimo,
                MAX(valor) AS maximo, COUNT(*) AS n
         FROM leituras WHERE sensor = ?`
      ).bind(sensor).first();
      return Response.json(row);
    }

    if (url.pathname === "/resumo") {
      const { results } = await env.DB.prepare(
        `SELECT sensor, AVG(valor) AS media, MAX(valor) AS maximo, COUNT(*) AS n
         FROM leituras GROUP BY sensor`
      ).all();
      return Response.json(results);
    }

    // ---- LOG DE CONEXAO ----
    if (url.pathname === "/log" && request.method === "POST") {
      const b = await request.json();   // { ip, rssi, tempo_ms, internet }
      await env.DB.prepare(
        "INSERT INTO conexoes (ip, rssi, tempo_ms, internet, timestamp) VALUES (?, ?, ?, ?, ?)"
      ).bind(b.ip || "", Number(b.rssi ?? 0), Number(b.tempo_ms ?? 0),
             Number(b.internet ?? 0), Date.now()).run();
      return new Response("LOG OK");
    }

    if (url.pathname === "/logs") {
      const { results } = await env.DB.prepare(
        "SELECT ip, rssi, tempo_ms, internet, timestamp FROM conexoes ORDER BY timestamp DESC LIMIT 50"
      ).all();
      return Response.json(results);
    }

    return new Response("Use /insert, /get, /list, /media, /resumo, /log, /logs");
  }
}
