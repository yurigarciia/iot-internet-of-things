"""Testa a ponte SEM broker e SEM ESP32: injeta mensagens MQTT assinadas e forjadas
direto nos callbacks, com o Worker local de verdade (npm run dev rodando).

  Uso:  python teste/teste_ponte.py        (da pasta 'trabalho G2')
"""
import json, os, sys, time
from pathlib import Path

os.environ.update({
    "HMAC_KEY": "chave-de-teste", "TOKEN_ESCRITA": "teste-escrita-123", "TOKEN_COMANDO": "tok-cmd",
    "SILO": "silote" + str(int(time.time()) % 100000), "SLEEP_S": "30", "COOLDOWN_S": "60",
    "WORKER_URL": os.environ.get("WORKER_URL", "http://127.0.0.1:8788"),
    "CA_FILE": __file__,  # so precisa existir; este teste nao abre conexao TLS
})
sys.path.insert(0, str(Path(__file__).parent.parent / "servico"))
import ponte  # noqa: E402

falhas = 0
def confere(nome, cond, extra=""):
    global falhas
    print(("PASS " if cond else "FAIL ") + nome, "" if cond else extra)
    falhas += 0 if cond else 1

class Msg:  # imita paho.MQTTMessage
    def __init__(s, topic, payload): s.topic, s.payload = topic, payload if isinstance(payload, bytes) else payload.encode()

class Falso:  # imita o cliente MQTT: so anota o que seria publicado
    def __init__(s): s.pub = []
    def publish(s, topic, payload, **kw): s.pub.append((topic, json.loads(payload), kw))
    def subscribe(s, *a, **kw): pass
fake = Falso(); ponte.cliente = fake

def esp_assina(d):  # o mesmo que String assinar() do silo.ino: HMAC do JSON inteiro, "mac" como ultimo campo
    s = json.dumps(d, separators=(",", ":"))
    return s[:-1] + ',"mac":"' + ponte.assinatura(s) + '"}'

def tele(umid, vent, ts=None, ok=True, bat=3.9, ciclo=1, **kw):
    d = {"v": 1, "silo": ponte.SILO, "ts": ts or int(time.time()), "ciclo": ciclo,
         "temp_c": 27.5 if ok else None, "umid_pct": umid if ok else None, "ventilador": vent,
         "modo": "auto", "sensor_ok": ok, "bat_v": bat, "rssi": -60, "atrasada": False, **kw}
    return esp_assina(d)

def hist():
    import requests
    r = requests.get(f"{ponte.WORKER}/historico?silo={ponte.SILO}&horas=24", headers={"Authorization": "Bearer teste-leitura-456"})
    return r.json()

T = ponte.T_TELE
# 1) telemetria autentica entra no historico
ponte.ao_receber(fake, None, Msg(T, tele(68.0, 0, ciclo=1)))
confere("telemetria assinada e gravada no D1", len(hist()) == 1, str(hist()))

# 2) forjada (sem mac / mac errado / corpo adulterado) e descartada
bom = tele(90.0, 0, ts=int(time.time()) + 1, ciclo=2)
ponte.ao_receber(fake, None, Msg(T, '{"silo":"x","umid_pct":10,"ventilador":0}'))
ponte.ao_receber(fake, None, Msg(T, bom.replace("90.0", "30.0")))                 # adulterada depois de assinar
ponte.ao_receber(fake, None, Msg(T, bom[:-5] + "0000\"}"))                         # mac trocado
confere("3 mensagens forjadas descartadas (nada novo no D1)", len(hist()) == 1, str(len(hist())))

# 3) umidade critica -> alerta publicado; segunda vez cai no cooldown
n0 = len([p for p in fake.pub if p[0] == ponte.T_ALERTA])
ponte.ao_receber(fake, None, Msg(T, bom))
ponte.ao_receber(fake, None, Msg(T, tele(91.0, 1, ts=int(time.time()) + 2, ciclo=3)))
al = [p for p in fake.pub if p[0] == ponte.T_ALERTA]
confere("umidade critica dispara 1 alerta", len(al) - n0 == 1 and al[-1][1]["tipo"] == "umidade_critica", str(al))
confere("2o alerta igual suprimido pelo cooldown (KV)", len(al) - n0 == 1)

# 4) sensor falhou -> alerta sensor_falha (tipo diferente: nao e barrado pelo cooldown da umidade)
ponte.ao_receber(fake, None, Msg(T, tele(0, 1, ts=int(time.time()) + 3, ok=False, ciclo=4)))
confere("sensor invalido gera alerta sensor_falha", any(p[1].get("tipo") == "sensor_falha" for p in fake.pub if p[0] == ponte.T_ALERTA))

# 5) comando: so assina cmd/valor validos; formato e seq iguais ao que o ESP32 espera
for cmd, val in (("abrir_portao", "1"), ("ventilador", "talvez"), ("limites", "70;65;35;32")):
    try: ponte.enviar_comando(cmd, val); ok = False
    except ValueError: ok = True
    confere(f"comando invalido recusado: {cmd}={val}", ok)
s1 = ponte.enviar_comando("ventilador", "on")
s2 = ponte.enviar_comando("ventilador", "auto")
c1, c2 = [p for p in fake.pub if p[0] == ponte.T_CMD][-2:]
confere("seq cresce a cada comando", c2[1]["seq"] > c1[1]["seq"] == s1 and c2[1]["seq"] == s2)
confere("comando vai RETIDO com QoS 1", c1[2].get("retain") is True and c1[2].get("qos") == 1)
confere("mac do comando = HMAC(seq|cmd|valor)", c1[1]["mac"] == ponte.assinatura(f"{s1}|ventilador|on"))

# 6) ack do ESP32 -> comando vira 'executado'; sem ack vira 'sem_confirmacao' depois do timeout
ack = esp_assina({"seq": s1, "cmd": "ventilador", "ok": True, "motivo": "ok", "ventilador": 1, "modo": "manual_on", "ciclo": 5, "ts": int(time.time())})
confere("antes do ack: pendente", ponte.status_cmd(ponte.comandos[s1])["status"] == "pendente")
ponte.ao_receber(fake, None, Msg(ponte.T_ACK, ack))
confere("depois do ack assinado: executado", ponte.status_cmd(ponte.comandos[s1])["status"] == "executado")
ack_falso = '{"seq":%d,"cmd":"ventilador","ok":true,"motivo":"ok"}' % s2
ponte.ao_receber(fake, None, Msg(ponte.T_ACK, ack_falso))
confere("ack forjado nao confirma comando", ponte.status_cmd(ponte.comandos[s2])["status"] == "pendente")
ponte.comandos[s2]["criado"] -= (ponte.timeout_cmd() + 1) * 1000
confere("sem ack dentro do timeout: sem_confirmacao", ponte.status_cmd(ponte.comandos[s2])["status"] == "sem_confirmacao")

print(f"\n{falhas} FALHA(S)" if falhas else "\nTODOS OS TESTES PASSARAM")
sys.exit(1 if falhas else 0)
