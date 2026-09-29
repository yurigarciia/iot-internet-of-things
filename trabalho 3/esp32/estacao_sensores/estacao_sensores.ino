#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include "config.h"

#define DHTPIN  4
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

RTC_DATA_ATTR int envios = 0;          // sobrevive ao deep sleep

// Envia um valor de sensor (POST /insert). Devolve o codigo HTTP.
int enviar(const char* sensor, float valor) {
  HTTPClient http;
  http.begin(String(WORKER_URL) + "/insert");
  http.addHeader("Content-Type", "application/json");
  String corpo = String("{\"sensor\":\"") + sensor + "\",\"valor\":" + String(valor, 1) + "}";
  int code = http.POST(corpo);
  Serial.printf("  %s=%.1f -> HTTP %d\n", sensor, valor, code);
  http.end();
  return code;
}

// Envia o log de conexao (POST /log)
void enviarLog(String ip, int rssi, long tempo_ms, int internet) {
  HTTPClient http;
  http.begin(String(WORKER_URL) + "/log");
  http.addHeader("Content-Type", "application/json");
  String corpo = "{\"ip\":\"" + ip + "\",\"rssi\":" + String(rssi) +
                 ",\"tempo_ms\":" + String(tempo_ms) +
                 ",\"internet\":" + String(internet) + "}";
  int code = http.POST(corpo);
  Serial.printf("  LOG (ip=%s rssi=%d %ldms net=%d) -> HTTP %d\n",
                ip.c_str(), rssi, tempo_ms, internet, code);
  http.end();
}

void setup() {
  Serial.begin(115200);
  dht.begin();

  // 1) Conecta no Wi-Fi medindo o tempo
  unsigned long t0 = millis();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Conectando ao WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(200); Serial.print("."); }
  long tempo = millis() - t0;                 // tempo para conectar (ms)
  String ip  = WiFi.localIP().toString();     // IP recebido na rede
  int   rssi = WiFi.RSSI();                    // forca do sinal (dBm)
  Serial.printf("\n ok | IP=%s | RSSI=%d dBm | %ld ms\n", ip.c_str(), rssi, tempo);

  // 2) Le o DHT11 e envia temperatura E umidade
  envios++;
  Serial.printf("Envio #%d\n", envios);
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  int code = 0;
  if (!isnan(t)) code = enviar("temp", t);
  if (!isnan(h)) enviar("umid", h);

  // 3) Envia o log de conexao (internet = a nuvem respondeu?)
  int internet = (code > 0) ? 1 : 0;
  enviarLog(ip, rssi, tempo, internet);

  // 4) Deep sleep para economizar energia
  const uint64_t DORME_SEG = 30;
  Serial.printf("Dormindo por %llu s...\n", DORME_SEG);
  Serial.flush();
  esp_sleep_enable_timer_wakeup(DORME_SEG * 1000000ULL);
  esp_deep_sleep_start();
}

void loop() { }   // nunca executa: tudo esta no setup()
