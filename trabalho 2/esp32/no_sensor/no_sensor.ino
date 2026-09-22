#include <WiFi.h>
#include <HTTPClient.h>
#include <DHT.h>
#include "config.h"

#define DHTPIN  4
#define DHTTYPE DHT11
DHT dht(DHTPIN, DHTTYPE);

RTC_DATA_ATTR int envios = 0;          // sobrevive ao deep sleep

void setup() {
  Serial.begin(115200);
  dht.begin();

  // 1) Conecta no Wi-Fi
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Conectando ao WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println(" ok");

  // 2) Le o sensor fisico
  float temp = dht.readTemperature();          // graus Celsius
  if (isnan(temp)) {
    Serial.println("Falha ao ler o DHT11!");
  } else {
    // 3) Envia para a nuvem
    HTTPClient http;
    http.begin(String(WORKER_URL) + "/insert");
    http.addHeader("Content-Type", "application/json");
    String corpo = "{\"sensor\":\"temp\",\"valor\":" + String(temp, 1) + "}";
    int code = http.POST(corpo);
    envios++;
    Serial.printf("Envio #%d -> HTTP %d | temp=%.1f C\n", envios, code, temp);
    http.end();                                // libera memoria
  }

  // 4) Dorme para economizar energia
  const uint64_t DORME_SEG = 30;
  Serial.printf("Dormindo por %llu s...\n", DORME_SEG);
  Serial.flush();
  esp_sleep_enable_timer_wakeup(DORME_SEG * 1000000ULL);
  esp_deep_sleep_start();                       // ao acordar, reinicia no setup()
}

void loop() { }   // nunca executa: o trabalho todo esta no setup()
