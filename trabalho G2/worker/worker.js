// Worker do Silo: guarda o historico (D1), o ultimo estado e o cooldown dos alertas (KV).
//
// Seguranca: toda rota (menos /saude) exige "Authorization: Bearer <token>".
//   TOKEN_ESCRITA -> servico que grava (POST)
//   TOKEN_LEITURA -> painel (GET)
// Os tokens sao segredos do ambiente (.dev.vars / wrangler secret), nunca ficam no codigo.

const CORS = {
  "Access-Control-Allow-Origin": "*",   // so e seguro porque TODA rota exige token
  "Access-Control-Allow-Headers": "Authorization, Content-Type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...CORS },
  });

// comparacao em tempo constante (nao revela quantos caracteres do token estavam certos)
function igual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

function token(request) {
  const h = request.headers.get("Authorization") || "";
  return h.startsWith("Bearer ") ? h.slice(7) : "";
}

const SILO_RE = /^[a-z0-9_-]{1,32}$/;
const num = (v) => (v === null || v === undefined || v === "" ? null : Number(v));
const dentro = (v, min, max) => v === null || (Number.isFinite(v) && v >= min && v <= max);

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const rota = url.pathname;

    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    if (rota === "/saude") return json({ ok: true });

    // ---------- autenticacao ----------
    if (!env.TOKEN_ESCRITA || !env.TOKEN_LEITURA)
      return json({ erro: "servidor sem tokens configurados" }, 500);   // falha fechada
    const t = token(request);
    const podeEscrever = igual(t, env.TOKEN_ESCRITA);
    const podeLer = podeEscrever || igual(t, env.TOKEN_LEITURA);
    const escreve = request.method === "POST";
    if (escreve ? !podeEscrever : !podeLer) return json({ erro: "nao autorizado" }, 401);

    try {
      // ================= ESCRITA =================
      if (escreve && rota === "/ingest") {
        const b = await request.json();
        const silo = String(b.silo || "");
        if (!SILO_RE.test(silo)) return json({ erro: "silo invalido" }, 400);
        const temp = num(b.temp_c), umid = num(b.umid_pct), bat = num(b.bat_v);
        const ok = b.sensor_ok ? 1 : 0;
        const vent = b.ventilador ? 1 : 0;
        if (!dentro(temp, -40, 80) || !dentro(umid, 0, 100) || !dentro(bat, 0, 6))
          return json({ erro: "valor fora da faixa fisica" }, 400);
        const agora = Date.now();
        const ts = Number(b.ts) > 1.7e12 ? Number(b.ts) : agora;   // ESP32 sem hora: usa a chegada

        const r = await env.DB.prepare(
          `INSERT OR IGNORE INTO leituras
             (silo, ts, temp_c, umid_pct, ventilador, sensor_ok, bat_v, rssi, atrasada, recebido_ts)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
        ).bind(silo, ts, temp, umid, vent, ok, bat, num(b.rssi), b.atrasada ? 1 : 0, agora).run();

        // retencao: guarda so o necessario, pelo tempo necessario
        const dias = Number(env.RETENCAO_DIAS) || 30;
        await env.DB.prepare("DELETE FROM leituras WHERE ts < ?").bind(agora - dias * 86400000).run();

        // ultimo estado no KV (so se esta leitura for a mais recente)
        const anterior = await env.KV.get(`ultimo:${silo}`, "json");
        if (!b.atrasada && (!anterior || ts >= anterior.ts)) {
          await env.KV.put(
            `ultimo:${silo}`,
            JSON.stringify({ silo, ts, temp_c: temp, umid_pct: umid, ventilador: vent, sensor_ok: ok,
                             bat_v: bat, rssi: num(b.rssi), modo: b.modo || null })
          );
        }
        return json({ ok: true, gravado: r.meta.changes === 1 });
      }

      if (escreve && rota === "/evento") {
        const b = await request.json();
        const silo = String(b.silo || "");
        if (!SILO_RE.test(silo) || !b.tipo) return json({ erro: "evento invalido" }, 400);
        await env.DB.prepare("INSERT INTO eventos (silo, ts, tipo, detalhe) VALUES (?, ?, ?, ?)")
          .bind(silo, Number(b.ts) > 1.7e12 ? Number(b.ts) : Date.now(),
                String(b.tipo).slice(0, 32), String(b.detalhe || "").slice(0, 300)).run();
        return json({ ok: true });
      }

      // cooldown de alerta: "posso avisar de novo?"  (o KV expira a chave sozinho)
      if (escreve && rota === "/alerta/tentar") {
        const b = await request.json();
        const silo = String(b.silo || ""), tipo = String(b.tipo || "");
        const cd = Math.max(60, Number(b.cooldown_s) || 1800);       // KV exige TTL >= 60 s
        if (!SILO_RE.test(silo) || !/^[a-z0-9_]{1,32}$/.test(tipo)) return json({ erro: "invalido" }, 400);
        const chave = `cooldown:${silo}:${tipo}`;
        if (await env.KV.get(chave)) return json({ permitido: false });
        await env.KV.put(chave, String(Date.now()), { expirationTtl: cd });
        return json({ permitido: true, cooldown_s: cd });
      }

      // ================= LEITURA =================
      const silo = url.searchParams.get("silo") || "silo01";
      if (!SILO_RE.test(silo)) return json({ erro: "silo invalido" }, 400);
      const horas = Math.min(Math.max(Number(url.searchParams.get("horas")) || 24, 1), 24 * 30);
      const desde = Date.now() - horas * 3600000;

      if (rota === "/ultimo") {
        const u = await env.KV.get(`ultimo:${silo}`, "json");
        return u ? json(u) : json({ erro: "sem leituras" }, 404);
      }

      if (rota === "/historico") {
        const lim = Math.min(Number(url.searchParams.get("limite")) || 200, 1000);
        const { results } = await env.DB.prepare(
          `SELECT ts, temp_c, umid_pct, ventilador, sensor_ok, bat_v, atrasada
           FROM leituras WHERE silo = ? AND ts >= ? ORDER BY ts DESC LIMIT ?`
        ).bind(silo, desde, lim).all();
        return json(results.reverse());
      }

      // CONSULTA DE RESUMO: umidade/temperatura por hora + quanto tempo o ventilador ficou ligado
      if (rota === "/resumo") {
        const { results } = await env.DB.prepare(
          `SELECT strftime('%Y-%m-%dT%H:00:00Z', ts / 1000, 'unixepoch') AS hora,
                  COUNT(*)                     AS leituras,
                  ROUND(MAX(umid_pct), 1)      AS umid_max,
                  ROUND(AVG(umid_pct), 1)      AS umid_media,
                  ROUND(MAX(temp_c), 1)        AS temp_max,
                  SUM(ventilador)              AS leituras_com_ventilador
           FROM leituras
           WHERE silo = ? AND ts >= ? AND sensor_ok = 1
           GROUP BY hora ORDER BY hora`
        ).bind(silo, desde).all();
        return json(results);
      }

      if (rota === "/eventos") {
        const { results } = await env.DB.prepare(
          "SELECT ts, tipo, detalhe FROM eventos WHERE silo = ? ORDER BY ts DESC LIMIT 50"
        ).bind(silo).all();
        return json(results);
      }

      return json({ erro: "rota inexistente", rotas: ["/ingest", "/evento", "/alerta/tentar", "/ultimo",
                    "/historico", "/resumo", "/eventos", "/saude"] }, 404);
    } catch (e) {
      return json({ erro: "falha interna" }, 500);   // nao vaza detalhes do erro para quem chama
    }
  },
};
