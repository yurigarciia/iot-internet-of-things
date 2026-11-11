"""Testa o PAINEL num Chrome headless (Selenium) com Worker local + ponte real + broker real.
Semeia 24 h de historico no Worker, publica telemetria assinada, clica em "Ligar", confere o
ciclo enviado -> executado e salva um print.   Uso: python teste/teste_painel.py [pasta-do-print]"""
import hashlib, hmac, json, os, secrets, ssl, subprocess, sys, time, urllib.request
from pathlib import Path
import paho.mqtt.client as mqtt
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

RAIZ = Path(__file__).parent.parent
PRINT = Path(sys.argv[1]) if len(sys.argv) > 1 else RAIZ / "docs"
GRUPO, SILO, KEY = "pnl" + secrets.token_hex(4), "silopnl", secrets.token_hex(16)
CA = RAIZ / "esp32" / "silo" / "mosquitto_ca.pem"; BASE = f"sis1a/{GRUPO}/{SILO}/"
env = {**os.environ, "GRUPO": GRUPO, "SILO": SILO, "HMAC_KEY": KEY, "SLEEP_S": "20", "API_PORT": "8794",
       "TOKEN_ESCRITA": "teste-escrita-123", "TOKEN_COMANDO": "tok-pnl", "CA_FILE": str(CA)}
falhas = 0
def confere(n, c, x=""):
    global falhas; falhas += 0 if c else 1; print(("PASS " if c else "FAIL ") + n, "" if c else x)
def mac(t): return hmac.new(KEY.encode(), t.encode(), hashlib.sha256).hexdigest()
def assina(d): s = json.dumps(d, separators=(",", ":")); return s[:-1] + ',"mac":"' + mac(s) + '"}'
def worker(rota, corpo): 
    r = urllib.request.Request("http://127.0.0.1:8788" + rota, method="POST", data=json.dumps(corpo).encode(),
        headers={"Authorization": "Bearer teste-escrita-123", "Content-Type": "application/json"}); return urllib.request.urlopen(r).read()

# historico de 24 h: umidade sobe ate 74 e o ventilador liga, depois cai
agora = int(time.time() * 1000)
for i in range(48):
    h = 24 - i / 2; u = 60 + 14 * max(0, 1 - abs(i - 24) / 10) + (i % 3) * 0.4
    worker("/ingest", {"silo": SILO, "ts": int(agora - h * 3600e3 + 1000), "temp_c": 26 + (i % 5) * 0.5, "umid_pct": round(u, 1),
                       "ventilador": 1 if u >= 70 else 0, "sensor_ok": True, "bat_v": 3.9, "rssi": -60})
worker("/evento", {"silo": SILO, "tipo": "ventilador", "detalhe": "ventilador LIGADO (modo auto, U=72%, T=27 C)"})

try: esp = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
except (AttributeError, TypeError): esp = mqtt.Client()
esp.tls_set(ca_certs=str(CA), cert_reqs=ssl.CERT_REQUIRED)
def ao_msg(c, _, m):
    d = json.loads(m.payload)
    if hmac.compare_digest(d.get("mac", ""), mac(f"{d['seq']}|{d['cmd']}|{d['valor']}")):
        c.publish(BASE + "ack", assina({"seq": d["seq"], "cmd": d["cmd"], "ok": True, "motivo": "ok", "ventilador": 1, "modo": "manual_on", "ciclo": 9, "ts": int(time.time())}), qos=1, retain=True)
esp.on_message = ao_msg

P = subprocess.Popen([sys.executable, "-u", str(RAIZ / "servico" / "ponte.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
op = Options(); op.add_argument("--headless=new"); op.add_argument("--window-size=1100,1900"); op.add_argument("--allow-file-access-from-files")
drv = None
try:
    time.sleep(5); esp.connect("test.mosquitto.org", 8883, 30); esp.loop_start(); time.sleep(1)
    esp.publish(BASE + "estado", assina({"ts": int(time.time()), "ventilador": 0, "modo": "auto", "manual_ttl": 0, "liga_u": 70, "desliga_u": 65,
                "liga_t": 35, "desliga_t": 32, "seq": 0, "sleep_s": 20, "bat_baixa": False, "fw": "1.0"}), qos=1, retain=True)
    esp.publish(BASE + "telemetria", assina({"v": 1, "silo": SILO, "ts": int(time.time()), "ciclo": 8, "temp_c": 27.4, "umid_pct": 68.2, "ventilador": 0,
                "modo": "auto", "sensor_ok": True, "bat_v": 3.92, "rssi": -58, "atrasada": False}), qos=1); time.sleep(2)

    drv = webdriver.Chrome(options=op)
    drv.get((RAIZ / "painel" / "index.html").as_uri())
    drv.execute_script("localStorage.setItem('silo_cfg', JSON.stringify(arguments[0]))",
        {"ponte": "http://127.0.0.1:8794", "tokP": "tok-pnl", "worker": "http://127.0.0.1:8788", "tokW": "teste-leitura-456", "silo": SILO})
    drv.get((RAIZ / "painel" / "index.html").as_uri()); time.sleep(3)
    txt = lambda i: drv.find_element(By.ID, i).text
    confere("umidade 68.2 aparece", txt("u") == "68.2", txt("u")); confere("temperatura 27.4", txt("t") == "27.4")
    confere("bateria 3.92", txt("b") == "3.92"); confere("chip online", "online" in txt("chipOnline") and "SEM" not in txt("chipOnline"), txt("chipOnline"))
    confere("chip ventilador desligado", "desligado" in txt("chipFan"), txt("chipFan"))
    confere("regra mostra limites do ESP32", "70%" in txt("regra") and "65%" in txt("regra"), txt("regra"))
    confere("campos de limite preenchidos", drv.find_element(By.ID, "lLU").get_attribute("value") == "70")
    confere("grafico desenhou a linha e pontos do ventilador", len(drv.find_elements(By.CSS_SELECTOR, "#grafico polyline")) == 1 and len(drv.find_elements(By.CSS_SELECTOR, "#grafico circle")) > 0)
    linhas = drv.find_elements(By.CSS_SELECTOR, "#resumo tr")
    confere("resumo SQL por hora tem linhas", len(linhas) >= 20 and "colspan" not in linhas[0].get_attribute("innerHTML"), str(len(linhas)))
    confere("evento do Worker listado", "ventilador LIGADO" in txt("eventos"))
    # comando: enviado -> executado
    drv.find_element(By.CSS_SELECTOR, "[data-val=on]").click(); time.sleep(0.6)
    confere("apos clicar: 'aguardando o ESP32' (nao 'executado')", "aguardando" in txt("cmds") and "executado" not in txt("cmds"), txt("cmds"))
    esp.subscribe(BASE + "comando", qos=1); time.sleep(6)         # ESP32 "acorda": recebe o retido e devolve o ack
    confere("apos o ack: 'executado'", "executado" in txt("cmds"), txt("cmds"))
    # umidade critica -> faixa vermelha
    esp.publish(BASE + "telemetria", assina({"v": 1, "silo": SILO, "ts": int(time.time()) + 1, "ciclo": 9, "temp_c": 27.0, "umid_pct": 85.0, "ventilador": 1,
                "modo": "auto", "sensor_ok": True, "bat_v": 3.9, "rssi": -58, "atrasada": False}), qos=1); time.sleep(6)
    confere("faixa de umidade critica aparece", "crítica" in txt("banner") or "critica" in txt("banner").lower(), txt("banner"))
    PRINT.mkdir(exist_ok=True); drv.save_screenshot(str(PRINT / "painel_teste.png"))
    # sem comunicacao: espera passar 2,5 ciclos (50 s)
    time.sleep(52)
    confere("sem telemetria por >2,5 ciclos: SEM COMUNICACAO", "SEM COMUNICA" in txt("chipOnline"), txt("chipOnline"))
finally:
    if drv: drv.quit()
    esp.loop_stop(); P.terminate()
    lim = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1); lim.tls_set(ca_certs=str(CA), cert_reqs=ssl.CERT_REQUIRED); lim.connect("test.mosquitto.org", 8883, 30); lim.loop_start()
    for t in ("comando", "ack", "estado"): lim.publish(BASE + t, b"", retain=True)
    time.sleep(1); lim.loop_stop()
print(f"\n{falhas} FALHA(S)" if falhas else "\nTODOS OS TESTES PASSARAM"); sys.exit(1 if falhas else 0)
