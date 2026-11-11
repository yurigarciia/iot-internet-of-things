"""Ponte do Silo: MQTT (TLS) <-> Worker (D1/KV) <-> Painel.

Roda no seu computador (ou em qualquer maquina sempre ligada). Faz quatro coisas:
  1. Telemetria, estado e ack do ESP32: CONFERE a assinatura HMAC e so entao grava no Worker.
  2. Alertas com cooldown (o cooldown mora no KV do Worker: sobrevive a reinicio da ponte).
  3. Vigia: se o silo nao fala ha mais de 2,5 ciclos -> alerta "silo_offline".
  4. API local (127.0.0.1) para o painel: ler estado e ENVIAR COMANDO ASSINADO.

Uso:   pip install paho-mqtt requests
       copie .env.example para .env e preencha
       python ponte.py
"""
import hashlib
import hmac
import json
import os
import re
import ssl
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import paho.mqtt.client as mqtt
import requests


def carregar_env():
    """Le servico/.env (CHAVE=valor). Variaveis de ambiente reais tem prioridade."""
    arq = Path(__file__).with_name(".env")
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


carregar_env()


def cfg(nome, padrao=None):
    v = os.environ.get(nome, padrao)
    if v is None:
        raise SystemExit(f"Falta {nome} no servico/.env (veja .env.example)")
    return v


GRUPO = cfg("GRUPO", "yuripaim")
SILO = cfg("SILO", "silo01")
BROKER = cfg("MQTT_HOST", "test.mosquitto.org")
PORTA = int(cfg("MQTT_PORT", "8883"))
CA_FILE = cfg("CA_FILE", str(Path(__file__).parent.parent / "esp32" / "silo" / "mosquitto_ca.pem"))
HMAC_KEY = cfg("HMAC_KEY").encode()
WORKER = cfg("WORKER_URL", "http://127.0.0.1:8788").rstrip("/")
TOKEN_ESCRITA = cfg("TOKEN_ESCRITA")
TOKEN_COMANDO = cfg("TOKEN_COMANDO")           # o painel usa este para falar com a ponte
SLEEP_S = int(cfg("SLEEP_S", "30"))            # tem que ser o mesmo SLEEP_S do ESP32
COOLDOWN_S = int(cfg("COOLDOWN_S", "1800"))    # mesmo alerta nao repete antes disso
UMID_CRITICA = float(cfg("UMID_CRITICA", "80"))
BAT_BAIXA_V = float(cfg("BAT_BAIXA_V", "3.4"))
API_PORT = int(cfg("API_PORT", "8790"))

BASE = f"sis1a/{GRUPO}/{SILO}/"
T_TELE, T_ESTADO, T_CMD, T_ACK, T_ALERTA = (BASE + x for x in ("telemetria", "estado", "comando", "ack", "alerta"))

# ---------------------------------------------------------------- estado em memoria
lock = threading.Lock()
ultima_tele = {}
ultimo_estado = {}
ultimo_ack = {}
alertas_recentes = deque(maxlen=20)
comandos = {}                 # seq -> {cmd, valor, criado, status, motivo}
ultimo_visto = 0.0            # quando chegou a ultima telemetria autentica
ultimo_vent = None
fila_worker = deque(maxlen=500)   # gravacoes que falharam (Worker fora): reenviadas depois
ARQ_SEQ = Path(__file__).with_name("seq.json")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------- HMAC
def assinatura(texto: str) -> str:
    return hmac.new(HMAC_KEY, texto.encode(), hashlib.sha256).hexdigest()


def verificar(bruto: bytes):
    """O ESP32 anexa ,"mac":"<64 hex>" como ultimo campo. Confere e devolve o dict (ou None)."""
    try:
        txt = bruto.decode()
    except UnicodeDecodeError:
        return None
    m = re.match(r'^(.*),"mac":"([0-9a-f]{64})"\}$', txt, re.S)
    if not m:
        return None
    corpo = m.group(1) + "}"
    if not hmac.compare_digest(assinatura(corpo), m.group(2)):
        return None
    try:
        return json.loads(corpo)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------- Worker
def worker(metodo, rota, corpo=None, tentar_depois=True):
    try:
        r = requests.request(metodo, WORKER + rota, json=corpo, timeout=8,
                             headers={"Authorization": f"Bearer {TOKEN_ESCRITA}"})
        if r.status_code >= 500 and tentar_depois:
            raise requests.RequestException(f"HTTP {r.status_code}")
        return r
    except requests.RequestException as e:
        if tentar_depois and metodo == "POST":
            fila_worker.append((rota, corpo))
            log(f"Worker indisponivel ({e}); guardado para reenviar ({len(fila_worker)} na fila)")
        return None


def esvaziar_fila():
    for _ in range(len(fila_worker)):
        rota, corpo = fila_worker.popleft()
        if worker("POST", rota, corpo, tentar_depois=False) is None:
            fila_worker.appendleft((rota, corpo))
            break


def evento(tipo, detalhe, ts=None):
    worker("POST", "/evento", {"silo": SILO, "tipo": tipo, "detalhe": detalhe, "ts": ts or int(time.time() * 1000)})


# ---------------------------------------------------------------- alertas
def disparar_alerta(tipo, mensagem, cliente):
    """Pergunta ao Worker (KV com TTL) se pode avisar; se sim, publica e registra."""
    r = worker("POST", "/alerta/tentar", {"silo": SILO, "tipo": tipo, "cooldown_s": COOLDOWN_S}, tentar_depois=False)
    if r is not None and r.ok and not r.json().get("permitido"):
        log(f"(alerta {tipo} suprimido: cooldown de {COOLDOWN_S}s)")
        return
    reg = {"tipo": tipo, "mensagem": mensagem, "ts": int(time.time() * 1000)}
    with lock:
        alertas_recentes.appendleft(reg)
    cliente.publish(T_ALERTA, json.dumps(reg), qos=1)
    evento("alerta", f"{tipo}: {mensagem}")
    log(f"*** ALERTA [{tipo}] {mensagem}")


def avaliar(tele, cliente):
    u, t, ok = tele.get("umid_pct"), tele.get("temp_c"), tele.get("sensor_ok")
    if not ok:
        disparar_alerta("sensor_falha", "sensor do silo devolveu leitura invalida; ventilador em estado seguro (ligado)", cliente)
    elif u is not None and u >= UMID_CRITICA:
        disparar_alerta("umidade_critica", f"umidade {u:.1f}% >= {UMID_CRITICA:.0f}% (temp {t:.1f} C)", cliente)
    bat = tele.get("bat_v")
    if bat is not None and 0.5 < bat < BAT_BAIXA_V:
        disparar_alerta("bateria_baixa", f"bateria em {bat:.2f} V (< {BAT_BAIXA_V} V)", cliente)


# ---------------------------------------------------------------- MQTT
def ao_conectar(cl, userdata, flags, rc, *args):
    if rc != 0:
        log("MQTT recusou a conexao, rc =", rc)
        return
    log(f"MQTT/TLS conectado em {BROKER}:{PORTA}; ouvindo {BASE}*")
    for t in (T_TELE, T_ESTADO, T_ACK):
        cl.subscribe(t, qos=1)


def ao_receber(cl, userdata, msg):
    global ultimo_visto, ultimo_vent
    dado = verificar(msg.payload)
    if dado is None:
        log(f"DESCARTADO [{msg.topic}]: assinatura ausente/invalida (possivel forjado)")
        evento("seguranca", f"mensagem sem assinatura valida em {msg.topic}")
        return

    if msg.topic == T_TELE:
        with lock:
            ultimo_visto = time.time()
        if not dado.get("atrasada"):
            with lock:
                ultima_tele.clear(); ultima_tele.update(dado)
        ts_ms = int(dado.get("ts", 0)) * 1000 if dado.get("ts") else int(time.time() * 1000)
        corpo = {**dado, "ts": ts_ms}
        r = worker("POST", "/ingest", corpo)
        log(f"telemetria ciclo={dado.get('ciclo')} T={dado.get('temp_c')} U={dado.get('umid_pct')} "
            f"vent={dado.get('ventilador')} -> worker {'ok' if r is not None and r.ok else 'FILA'}")
        if not dado.get("atrasada"):
            vent = dado.get("ventilador")
            if ultimo_vent is not None and vent != ultimo_vent:
                evento("ventilador", f"ventilador {'LIGADO' if vent else 'DESLIGADO'} (modo {dado.get('modo')}, "
                                     f"U={dado.get('umid_pct')}%, T={dado.get('temp_c')} C)", ts_ms)
            ultimo_vent = vent
            avaliar(dado, cl)

    elif msg.topic == T_ESTADO:
        with lock:
            ultimo_estado.clear(); ultimo_estado.update(dado)

    elif msg.topic == T_ACK:
        with lock:
            ultimo_ack.clear(); ultimo_ack.update(dado)
            c = comandos.get(dado.get("seq"))
            if c and c["status"] == "pendente":
                c["status"] = "executado" if dado.get("ok") else "rejeitado"
                c["motivo"] = dado.get("motivo")
                c["confirmado"] = int(time.time() * 1000)
        if c:
            evento("comando", f"seq {dado.get('seq')} {c['cmd']}={c['valor']} -> {c['status']} ({dado.get('motivo')})")
            log(f"ACK seq={dado.get('seq')} {c['cmd']}={c['valor']} -> {c['status']}")


try:
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id=f"ponte-{GRUPO}-{SILO}-{os.getpid()}")
except (AttributeError, TypeError):
    cliente = mqtt.Client(client_id=f"ponte-{GRUPO}-{SILO}-{os.getpid()}")
cliente.on_connect = ao_conectar
cliente.on_message = ao_receber


# ---------------------------------------------------------------- comandos (assinados)
CMDS_OK = {
    "ventilador": lambda v: v in ("auto", "on", "off"),
    "limites": lambda v: bool(re.fullmatch(r"\d+(\.\d+)?(,\d+(\.\d+)?){3}", v)),
}


def enviar_comando(cmd, valor):
    if cmd not in CMDS_OK or not CMDS_OK[cmd](str(valor)):
        raise ValueError("comando ou valor invalido")   # nunca assina lixo
    with lock:
        ultimo = 0
        if ARQ_SEQ.exists():
            try:
                ultimo = json.loads(ARQ_SEQ.read_text())["seq"]
            except (ValueError, KeyError):
                pass
        seq = max(int(time.time()), ultimo + 1)          # cresce sempre, mesmo se o arquivo se perder
        ARQ_SEQ.write_text(json.dumps({"seq": seq}))
        corpo = {"seq": seq, "cmd": cmd, "valor": str(valor)}
        corpo["mac"] = assinatura(f"{seq}|{cmd}|{valor}")
        comandos[seq] = {"seq": seq, "cmd": cmd, "valor": str(valor), "criado": int(time.time() * 1000),
                         "status": "pendente", "motivo": None}
    # retido + QoS1: o ESP32 (que dorme) recebe assim que acordar e se inscrever
    cliente.publish(T_CMD, json.dumps(corpo), qos=1, retain=True)
    log(f"comando enviado seq={seq} {cmd}={valor} (aguardando o ESP32 acordar)")
    return seq


def timeout_cmd():
    return 2 * SLEEP_S + 30      # ESP32 pode estar no dobro do sono (bateria baixa) + margem


def status_cmd(c):
    with lock:
        if c["status"] == "pendente" and time.time() * 1000 - c["criado"] > timeout_cmd() * 1000:
            c["status"] = "sem_confirmacao"
        return dict(c)


# ---------------------------------------------------------------- vigia
def vigia():
    while True:
        time.sleep(10)
        try:
            esvaziar_fila()
            with lock:
                visto = ultimo_visto
            if visto and time.time() - visto > 2.5 * SLEEP_S:
                disparar_alerta("silo_offline", f"sem telemetria ha {int(time.time() - visto)} s "
                                                f"(esperado a cada {SLEEP_S} s)", cliente)
        except Exception as e:                              # a vigia nunca pode morrer
            log("vigia:", e)


# ---------------------------------------------------------------- API local para o painel
class Api(BaseHTTPRequestHandler):
    def _resp(self, status, obj):
        corpo = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")   # seguro: exige token e so escuta em 127.0.0.1
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(corpo)

    def _auth(self):
        h = self.headers.get("Authorization", "")
        return hmac.compare_digest(h.encode(), f"Bearer {TOKEN_COMANDO}".encode())

    def do_OPTIONS(self):
        self._resp(204, {})

    def do_GET(self):
        if not self._auth():
            return self._resp(401, {"erro": "nao autorizado"})
        u = urlparse(self.path)
        if u.path == "/estado":
            with lock:
                visto = ultimo_visto
                out = {"telemetria": dict(ultima_tele), "estado": dict(ultimo_estado), "ack": dict(ultimo_ack),
                       "alertas": list(alertas_recentes), "sleep_s": SLEEP_S, "agora": int(time.time() * 1000),
                       "ultimo_visto": int(visto * 1000), "umid_critica": UMID_CRITICA}
            out["online"] = bool(visto) and time.time() - visto <= 2.5 * SLEEP_S
            out["comandos"] = [status_cmd(c) for c in list(comandos.values())[-8:]]
            return self._resp(200, out)
        if u.path == "/comando":
            try:
                seq = int(parse_qs(u.query).get("seq", ["0"])[0])
            except ValueError:
                seq = 0
            c = comandos.get(seq)
            return self._resp(200, status_cmd(c)) if c else self._resp(404, {"erro": "seq desconhecido"})
        self._resp(404, {"erro": "rota inexistente"})

    def do_POST(self):
        if not self._auth():
            return self._resp(401, {"erro": "nao autorizado"})
        if urlparse(self.path).path != "/comando":
            return self._resp(404, {"erro": "rota inexistente"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            b = json.loads(self.rfile.read(min(n, 2048)))
            seq = enviar_comando(b.get("cmd"), b.get("valor"))
        except (ValueError, TypeError, KeyError) as e:
            return self._resp(400, {"erro": str(e)})
        self._resp(200, {"seq": seq, "status": "pendente", "timeout_s": timeout_cmd()})

    def log_message(self, *a):   # silencia o log padrao do http.server
        pass


# ---------------------------------------------------------------- main
if __name__ == "__main__":
    if not Path(CA_FILE).exists():
        raise SystemExit(f"CA do broker nao encontrada em {CA_FILE}\n"
                         "Rode 'python baixar_ca.py' em esp32/silo (gera mosquitto_ca.pem e ca_cert.h).")
    # TLS COM verificacao do servidor (CERT_REQUIRED + hostname). Nada de tls_insecure_set(True).
    cliente.tls_set(ca_certs=CA_FILE, cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    cliente.reconnect_delay_set(1, 30)
    cliente.connect_async(BROKER, PORTA, 30)
    cliente.loop_start()
    threading.Thread(target=vigia, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", API_PORT), Api)
    log(f"API do painel em http://127.0.0.1:{API_PORT} | Worker em {WORKER}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    cliente.loop_stop()
