"""Baixa a CA do broker e gera ca_cert.h para o sketch.

Uso (na pasta esp32/silo):   python baixar_ca.py
Opcional: python baixar_ca.py <url-da-ca.crt>

A CA e PUBLICA (nao e segredo) — pode ser versionada. Ela e o que permite ao
ESP32 CONFERIR que esta falando com o servidor certo, em vez de setInsecure().
"""
import sys
import urllib.request
from pathlib import Path

URL = sys.argv[1] if len(sys.argv) > 1 else "https://test.mosquitto.org/ssl/mosquitto.org.crt"
pem = urllib.request.urlopen(URL, timeout=20).read().decode().strip()
assert pem.startswith("-----BEGIN CERTIFICATE-----"), "isso nao parece um certificado PEM"

saida = Path(__file__).with_name("ca_cert.h")
saida.write_text(
    f"// Gerado por baixar_ca.py a partir de {URL}\n"
    f'const char CA_CERT[] PROGMEM = R"EOF(\n{pem}\n)EOF";\n',
    encoding="utf-8",
)
Path(__file__).with_name("mosquitto_ca.pem").write_text(pem + "\n", encoding="utf-8")
print("ok ->", saida)
