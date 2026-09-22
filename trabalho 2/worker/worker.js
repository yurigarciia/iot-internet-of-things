export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Gravar uma leitura (último valor + histórico)
    if (url.pathname === "/insert" && request.method === "POST") {
      const body = await request.json();
      if (!env.KV_SENSOR)
        return new Response("Binding KV_SENSOR nao encontrado!", { status: 500 });

      const nome = body.sensor || "temp";
      const valor = body.valor ?? "0";
      const timestamp = Date.now();

      await env.KV_SENSOR.put(`sensor:${nome}:last`,
        JSON.stringify({ valor, timestamp }));            // ultimo valor
      await env.KV_SENSOR.put(`sensor:${nome}:${timestamp}`,
        JSON.stringify({ valor, timestamp }));            // historico

      return new Response(`OK: ${nome}=${valor}`);
    }

    // Ler o ultimo valor
    if (url.pathname === "/get") {
      const nome = url.searchParams.get("sensor");
      if (!nome) return new Response("Informe ?sensor=temp", { status: 400 });

      const data = await env.KV_SENSOR.get(`sensor:${nome}:last`, { type: "json" });
      if (!data) return new Response("Nenhum valor encontrado", { status: 404 });

      return new Response(JSON.stringify(data, null, 2), {
        headers: { "Content-Type": "application/json" }
      });
    }

    // Ler o historico
    if (url.pathname === "/list") {
      const nome = url.searchParams.get("sensor");
      if (!nome) return new Response("Informe ?sensor=temp", { status: 400 });

      const { keys } = await env.KV_SENSOR.list({ prefix: `sensor:${nome}:` });
      let historico = [];
      for (let k of keys) {
        if (k.name.endsWith(":last")) continue;   // pula o "last"
        const val = await env.KV_SENSOR.get(k.name, { type: "json" });
        if (val) historico.push(val);
      }
      return new Response(JSON.stringify(historico, null, 2), {
        headers: { "Content-Type": "application/json" }
      });
    }

    return new Response("Use POST /insert, GET /get?sensor=nome ou GET /list?sensor=nome");
  }
}
