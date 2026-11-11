// Teste do Worker (precisa estar rodando: npm run dev). Uso:
//   TOKEN_ESCRITA=... TOKEN_LEITURA=... node teste_worker.mjs [url]
const BASE = process.argv[2] || "http://127.0.0.1:8788";
const W = process.env.TOKEN_ESCRITA, R = process.env.TOKEN_LEITURA;
let falhas = 0;
const confere = (nome, cond, extra = "") => {
  console.log(`${cond ? "PASS" : "FAIL"}  ${nome} ${cond ? "" : extra}`);
  if (!cond) falhas++;
};
const chama = async (metodo, rota, token, corpo) => {
  const r = await fetch(BASE + rota, {
    method: metodo,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), "Content-Type": "application/json" },
    body: corpo ? JSON.stringify(corpo) : undefined,
  });
  let j = null; try { j = await r.json(); } catch {}
  return { s: r.status, j };
};

const silo = "silot" + Math.floor(Math.random() * 1e6);
const t0 = Date.now() - 3 * 3600000;
const leit = (i, u, vent) => ({ silo, ts: t0 + i * 600000, temp_c: 25 + i * 0.1, umid_pct: u, ventilador: vent,
                                sensor_ok: true, bat_v: 3.9, rssi: -60 });

// --- seguranca (rota de gravacao aceita qualquer um?) ---
confere("POST /ingest sem token -> 401", (await chama("POST", "/ingest", null, leit(0, 60, 0))).s === 401);
confere("POST /ingest token errado -> 401", (await chama("POST", "/ingest", "errado", leit(0, 60, 0))).s === 401);
confere("POST /ingest com token de LEITURA -> 401", (await chama("POST", "/ingest", R, leit(0, 60, 0))).s === 401);
confere("GET /historico sem token -> 401", (await chama("GET", `/historico?silo=${silo}`, null)).s === 401);
confere("GET /saude e publico", (await chama("GET", "/saude", null)).s === 200);

// --- validacao ---
confere("umidade 150% -> 400", (await chama("POST", "/ingest", W, { ...leit(0, 150, 0) })).s === 400);
confere("silo com caractere estranho -> 400", (await chama("POST", "/ingest", W, { ...leit(0, 60, 0), silo: "a;b" })).s === 400);

// --- gravacao + historico ---
const us = [60, 66, 72, 74, 68, 63];
for (let i = 0; i < us.length; i++)
  confere(`ingest leitura ${i}`, (await chama("POST", "/ingest", W, leit(i, us[i], us[i] >= 70 ? 1 : 0))).j?.gravado === true);
const dup = await chama("POST", "/ingest", W, leit(0, 60, 0));
confere("leitura duplicada nao grava de novo", dup.s === 200 && dup.j.gravado === false);

const h = await chama("GET", `/historico?silo=${silo}&horas=24`, R);
confere("historico devolve 6 linhas (token de leitura)", h.s === 200 && h.j.length === 6, JSON.stringify(h.j));

const r = await chama("GET", `/resumo?silo=${silo}&horas=24`, R);
const totalLeit = r.j.reduce((a, x) => a + x.leituras, 0);
const maxU = Math.max(...r.j.map((x) => x.umid_max));
confere("resumo por hora soma 6 leituras", r.s === 200 && totalLeit === 6, JSON.stringify(r.j));
confere("resumo: umidade maxima = 74", maxU === 74, String(maxU));
confere("resumo: leituras com ventilador = 2", r.j.reduce((a, x) => a + x.leituras_com_ventilador, 0) === 2);

const u = await chama("GET", `/ultimo?silo=${silo}`, R);
confere("/ultimo (KV) devolve a leitura mais recente", u.s === 200 && u.j.umid_pct === 63, JSON.stringify(u.j));

// --- sensor falhou: NULL no banco e fora do resumo ---
await chama("POST", "/ingest", W, { silo, ts: Date.now(), temp_c: null, umid_pct: null, ventilador: 1, sensor_ok: false });
const r2 = await chama("GET", `/resumo?silo=${silo}&horas=24`, R);
confere("leitura invalida nao entra no resumo", r2.j.reduce((a, x) => a + x.leituras, 0) === 6);

// --- evento + cooldown ---
confere("POST /evento", (await chama("POST", "/evento", W, { silo, tipo: "alerta", detalhe: "teste" })).j?.ok === true);
const e = await chama("GET", `/eventos?silo=${silo}`, R);
confere("GET /eventos", e.j.length === 1 && e.j[0].tipo === "alerta");
const c1 = await chama("POST", "/alerta/tentar", W, { silo, tipo: "umidade_alta", cooldown_s: 60 });
const c2 = await chama("POST", "/alerta/tentar", W, { silo, tipo: "umidade_alta", cooldown_s: 60 });
const c3 = await chama("POST", "/alerta/tentar", W, { silo, tipo: "bateria_baixa", cooldown_s: 60 });
confere("cooldown: 1o alerta permitido", c1.j?.permitido === true);
confere("cooldown: 2o igual e BLOQUEADO", c2.j?.permitido === false);
confere("cooldown: alerta de outro tipo e permitido", c3.j?.permitido === true);

console.log(falhas ? `\n${falhas} FALHA(S)` : "\nTODOS OS TESTES PASSARAM");
process.exit(falhas ? 1 : 0);
