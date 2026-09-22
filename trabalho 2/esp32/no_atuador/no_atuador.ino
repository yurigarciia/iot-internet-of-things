#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "config.h"

#define LED    2          // LED embutido de muitas placas ESP32
#define LIMITE 30.0       // acende acima disso

void setup() {
  Serial.begin(115200);
  pinMode(LED, OUTPUT);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println(" WiFi ok");
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(String(WORKER_URL) + "/get?sensor=temp");
    int code = http.GET();

    if (code == 200) {
      String payload = http.getString();
      StaticJsonDocument<200> doc;
      deserializeJson(doc, payload);
      float valor = doc["valor"];
      Serial.printf("temp = %.1f C\n", valor);
      digitalWrite(LED, valor > LIMITE ? HIGH : LOW);   // reage ao valor
    }
    http.end();
  }
  delay(10000);   // consulta a cada 10 s (este no fica ligado, por isso nao dorme)
}
