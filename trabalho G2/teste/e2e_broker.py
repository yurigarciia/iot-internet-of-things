"""Teste ponta a ponta com o BROKER REAL (precisa de internet e do Worker local rodando):
   ponte.py (subprocesso) <-TLS 8883-> broker <-TLS-> "ESP32 simulado" (este script)

O ESP32 simulado e um PORT em Python da logica do silo.ino (HMAC, seq, ack); ele NAO prova o firmware,
prova o protocolo: TLS conferido, mensagens retidas, assinatura, ack, API da ponte e gravacao no Worker.
Usa um GRUPO aleatorio para nao colidir com outros usuarios do broker publico.
"""
import hashlib, hmac, json, os, secrets, ssl, subprocess, sys, time, urllib.request
from pathlib import Path
import paho.mqtt.client as mqtt

RAIZ = Path(__file__).parent.parent
GRUPO, SILO, KEY = "e2e" + secrets.token_hex(4), "silo" + secrets.token_hex(3), secrets.token_hex(16)
CA = RAIZ / "esp32" / "silo" / "mosquitto_ca.pem"
BASE = f"sis1a/{GRUPO}/{SILO}/"
env = {**os.environ, "GRUPO": GRUPO, "SILO": SILO, "HMAC_KEY": KEY, "SLEEP_S": "5", "API_PORT": "8793",
       "TOKEN_ESCRITA": "teste-escrita-123", "TOKEN_COMANDO": "tok-e2e", "CA_FILE": str(CA), "COOLDOWN_S": "60"}

falhas = 0
def confere(nome, cond, extra=""):
    global falhas; falhas += 0 if cond else 1
    print(("PASS " if cond else "FAIL ") + nome, "" if cond else extra)

def mac(t): return hmac.new(KEY.encode(), t.encode(), hashlib.sha256).hexdigest()
def assina(d):
    s = json.dumps(d, separators=(",", ":")); return s[:-1] + ',"mac":"' + mac(s) + '"}'
def api(m, p, corpo=None, tok="tok-e2e"):
    r = urllib.request.Request("http://127.0.0.1:8793" + p, method=m, data=json.dumps(corpo).encode() if corpo else None,
                               headers={"Authorization": "Bearer " + tok})
    try: x = urllib.request.urlopen(r, timeout=5); return x.status, json.loads(x.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read())

# ---- "ESP32" simulado: valida o comando como o firmware faz
ult_seq, vent, modo, rejeitados = 0, 0, "auto", []
def ao_msg(c, _, msg):
    global ult_seq, vent, modo
    d = json.loads(msg.payload); seq = d["seq"]
    if seq <= ult_seq: return
    if not hmac.compare_digest(d.get("mac", ""), mac(f"{seq}|{d['cmd']}|{d['valor']}")):
        rejeitados.append(seq); return
    ult_seq = seq
    if d["cmd"] == "ventilador": modo = {"on": "manual_on", "off": "manual_off", "auto": "auto"}[d["valor"]]; vent = 1 if d["valor"] == "on" else 0
    c.publish(BASE + "ack", assina({"seq": seq, "cmd": d["cmd"], "ok": True, "motivo": "ok", "ventilador": vent, "modo": modo, "ciclo": 1, "ts": int(time.time())}), qos=1, retain=True)

def novo(): 
    try: c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    except (AttributeError, TypeError): c = mqtt.Client()
    c.tls_set(ca_certs=str(CA), cert_reqs=ssl.CERT_REQUIRED); return c

W = subprocess.Popen([sys.executable, "-u", str(RAIZ / "servico" / "ponte.py")], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
try:
    time.sleep(5)
    confere("ponte subiu e API responde (401 sem token)", api("GET", "/estado", tok="x")[0] == 401)

    esp = novo(); esp.on_message = ao_msg; esp.connect("test.mosquitto.org", 8883, 30); esp.loop_start()
    time.sleep(1)
    tele = {"v": 1, "silo": SILO, "ts": int(time.time()), "ciclo": 1, "temp_c": 28.1, "umid_pct": 83.5, "ventilador": 1,
            "modo": "auto", "sensor_ok": True, "bat_v": 3.9, "rssi": -55, "atrasada": False}
    esp.publish(BASE + "telemetria", assina(tele), qos=1); time.sleep(3)
    s, e = api("GET", "/estado")
    confere("telemetria assinada chegou na ponte via TLS", e["telemetria"].get("umid_pct") == 83.5, json.dumps(e)[:200])
    confere("ponte marcou o silo online", e["online"] is True)
    confere("umidade 83,5% gerou alerta umidade_critica", any(a["tipo"] == "umidade_critica" for a in e["alertas"]))

    esp.publish(BASE + "telemetria", '{"silo":"silo01","umid_pct":5,"ventilador":0}', qos=1); time.sleep(2)  # forjada
    confere("telemetria forjada nao alterou o estado", api("GET", "/estado")[1]["telemetria"].get("umid_pct") == 83.5)

    # ESP32 "dormindo": ainda NAO assinou o comando. Painel envia, comando fica retido no broker.
    esp.unsubscribe(BASE + "comando")
    s, r = api("POST", "/comando", {"cmd": "ventilador", "valor": "on"})
    confere("POST /comando devolve seq e pendente", s == 200 and r["status"] == "pendente", str(r)); seq = r.get("seq")
    time.sleep(2)
    confere("sem ESP32 acordado: comando segue pendente", api("GET", f"/comando?seq={seq}")[1]["status"] == "pendente")
    # ESP32 "acorda": assina o topico e recebe o comando RETIDO
    esp.subscribe(BASE + "comando", qos=1); time.sleep(3)
    st = api("GET", f"/comando?seq={seq}")[1]["status"]
    confere("ESP32 acorda, recebe o retido, devolve ack -> executado", st == "executado", st)
    confere("ESP32 simulado aplicou: modo manual_on", modo == "manual_on")

    # ataque: comandos falsos no topico (com o broker real)
    ant = (ult_seq, modo)
    for corpo in ({"seq": ult_seq + 5, "cmd": "ventilador", "valor": "off"},
                  {"seq": ult_seq + 6, "cmd": "ventilador", "valor": "off", "mac": "0" * 64}):
        esp.publish(BASE + "comando", json.dumps(corpo), qos=1, retain=True); time.sleep(1.5)
    confere("2 comandos falsos rejeitados; estado do ESP32 inalterado", len(rejeitados) == 2, str(rejeitados))
    confere("ESP32 nao mudou de modo nem de seq", (ult_seq, modo) == ant)
    esp.loop_stop(); esp.disconnect()
finally:
    W.terminate()
    try: saida = W.communicate(timeout=5)[0]
    except Exception: saida = ""
    print("\n--- log da ponte ---\n" + "\n".join(saida.splitlines()[-14:]))
    # limpa as mensagens retidas deste grupo aleatorio no broker publico
    lim = novo(); lim.connect("test.mosquitto.org", 8883, 30); lim.loop_start()
    for t in ("comando", "ack", "estado"): lim.publish(BASE + t, b"", retain=True)
    time.sleep(1); lim.loop_stop()
print(f"\n{falhas} FALHA(S)" if falhas else "\nTODOS OS TESTES PASSARAM"); sys.exit(1 if falhas else 0)
