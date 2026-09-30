# FERRAMENTA DE TESTE — NAO e o firmware do ESP32.
#
# Publica, no broker publico test.mosquitto.org, exatamente os mesmos topicos
# que o "esp32/estacao_conexao.ino" publicaria (temp, umid, led, logs e
# ciclos), para validar o "servico/servico.py" sem precisar do hardware
# fisico ligado. Usado so para gerar as evidencias locais do ENTREGA.md.
#
# Rodar: pip install paho-mqtt && python simulate_esp32.py

import json
import random
import time

import paho.mqtt.client as mqtt

BROKER = "test.mosquitto.org"
NOME = "yuripaim"                 # mesmo NOME do .ino e do servico.py
BASE = f"sis1a/{NOME}/"

limite = 30.0
led_on = False
ciclos = 0


def ao_receber(cliente, userdata, msg):
    global limite, led_on
    payload = msg.payload.decode()
    print(f"  [comando recebido] {msg.topic} = {payload}")
    if payload.startswith("limite:"):
        limite = float(payload.split(":", 1)[1])
        print(f"   -> novo limite = {limite}")
    elif payload.startswith("led:"):
        led_on = payload.split(":", 1)[1].upper() in ("ON", "1")
        cliente.publish(BASE + "led", "ON" if led_on else "OFF")
        print(f"   -> LED forcado para {'ON' if led_on else 'OFF'}")


try:
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
except (AttributeError, TypeError):
    cliente = mqtt.Client()

cliente.on_message = ao_receber
cliente.connect(BROKER, 1883, 30)
cliente.subscribe(BASE + "comando")
cliente.loop_start()

print(f"Simulador publicando em {BASE}* (Ctrl+C para parar)\n")

try:
    while True:
        ciclos += 1
        temp = round(random.uniform(26.0, 32.0), 1)
        umid = round(random.uniform(55.0, 65.0), 1)
        novo_led = temp > limite
        if novo_led != led_on:
            led_on = novo_led
            cliente.publish(BASE + "led", "ON" if led_on else "OFF")

        cliente.publish(BASE + "temp", str(temp))
        cliente.publish(BASE + "umid", str(umid))

        wifi_log = json.dumps({
            "ssid": "MinhaRede", "rssi": random.randint(-70, -45),
            "ip": "192.168.0.42", "ms": random.randint(400, 1200)
        })
        cliente.publish(BASE + "log/wifi", wifi_log)

        hora_log = json.dumps({
            "hora": time.strftime("%Y-%m-%d %H:%M:%S"), "relogio_ok": True
        })
        cliente.publish(BASE + "log/hora", hora_log)

        cliente.publish(BASE + "log/ciclos", str(ciclos))

        print(f"[ciclo {ciclos}] temp={temp} umid={umid} led={'ON' if led_on else 'OFF'} "
              f"(limite={limite}) wifi={wifi_log}")

        time.sleep(10)
except KeyboardInterrupt:
    pass
finally:
    cliente.loop_stop()
    cliente.disconnect()
    print("Simulador encerrado.")
