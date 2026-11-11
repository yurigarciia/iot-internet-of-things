"""TESTE DE ATAQUE (Etapa 10): publica comandos FALSOS no topico de comando do silo.

O ESP32 tem que IGNORAR todos (e o ventilador nao pode mudar). Rode com o ESP32/Wokwi ligado,
espere o proximo despertar e confira no Serial: "REJEITADO: assinatura invalida" / "ja visto".

  pip install paho-mqtt
  python teste/ataque_comando_falso.py              (usa MQTT_HOST/GRUPO/SILO do servico/.env)
"""
import json, os, ssl, sys, time
from pathlib import Path
import paho.mqtt.client as mqtt

env = Path(__file__).parent.parent / "servico" / ".env"
if env.exists():
    for l in env.read_text(encoding="utf-8").splitlines():
        if "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1); os.environ.setdefault(k.strip(), v.strip())
host = os.environ.get("MQTT_HOST", "test.mosquitto.org")
topico = f"sis1a/{os.environ.get('GRUPO','yuripaim')}/{os.environ.get('SILO','silo01')}/comando"
# so a ultima mensagem retida fica no broker: para o ESP32 ver CADA ataque, espere ele acordar (SLEEP_S) entre eles
ESPERA = float(os.environ.get("ATAQUE_ESPERA", "1"))
ca = Path(__file__).parent.parent / "esp32" / "silo" / "mosquitto_ca.pem"

ataques = {
    "sem assinatura":            {"seq": int(time.time()) + 10, "cmd": "ventilador", "valor": "off"},
    "assinatura inventada":      {"seq": int(time.time()) + 11, "cmd": "ventilador", "valor": "off", "mac": "0" * 64},
    "limites absurdos, sem mac": {"seq": int(time.time()) + 12, "cmd": "limites", "valor": "95,94,60,58"},
    "seq gigante p/ travar":     {"seq": 4000000000, "cmd": "ventilador", "valor": "off", "mac": "f" * 64},
}
try:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
except (AttributeError, TypeError):
    c = mqtt.Client()
c.tls_set(ca_certs=str(ca) if ca.exists() else None, cert_reqs=ssl.CERT_REQUIRED)
c.connect(host, 8883, 30); c.loop_start()
for nome, corpo in ataques.items():
    print("atacando:", nome); c.publish(topico, json.dumps(corpo), qos=1, retain=True).wait_for_publish(); time.sleep(ESPERA)
c.loop_stop(); c.disconnect()
print("\nAtencao: o ultimo ataque ficou RETIDO no topico. O ESP32 vai rejeitar (HMAC), mas o comando legitimo\n"
      "so volta a valer quando a ponte publicar um novo (qualquer botao do painel).")
