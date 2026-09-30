// ================================================================
//  ESTACAO MQTT — topicos separados, logs organizados e Deep Sleep.
//  Evolucao do ponto de partida (que publicava tudo em um unico
//  topico "dados"). Ver README para o enunciado completo.
// ================================================================
#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <time.h>
#include "config.h"

// >>> TROQUE "NOME" por algo UNICO seu (nome/matricula) <<<
#define NOME "yuripaim"

#define DHTPIN 4
#define DHTTYPE DHT11
#define LED 2

DHT dht(DHTPIN, DHTTYPE);
WiFiClient wifi;
PubSubClient mqtt(wifi);

// ---- Tarefa 1/2/3: um topico por variavel, em vez de um "dados" so ----
String BASE           = String("sis1a/") + NOME + "/";
String TOPICO_TEMP    = BASE + "temp";        // temperatura
String TOPICO_UMID    = BASE + "umid";        // umidade
String TOPICO_LED     = BASE + "led";         // estado do LED (ON/OFF)
String TOPICO_WIFI    = BASE + "log/wifi";    // log de Wi-Fi (JSON: ssid, rssi, ip, ms)
String TOPICO_HORA    = BASE + "log/hora";    // log de TLS (hora local)
String TOPICO_CICLOS  = BASE + "log/ciclos";  // Tarefa 4: contador de despertares
String TOPICO_CMD     = BASE + "comando";     // recebimento

float limite = 30.0;          // a REGRA: acende o LED acima disso
bool  ledOn  = false;
long  tempoConexao = 0;       // quanto tempo levou p/ conectar no Wi-Fi (ms)

// Tarefa 4: sobrevive ao deep sleep, conta quantos ciclos (despertares) ja houve
RTC_DATA_ATTR int ciclos = 0;

String horaLocal() {
  struct tm t;
  if (!getLocalTime(&t)) return "sem-hora";
  char buf[25];
  strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", &t);
  return String(buf);
}

// RECEBIMENTO: comando vindo do serviço (Python/HTML)
void aoReceber(char* topico, byte* payload, unsigned int len) {
  String msg;
  for (unsigned int i = 0; i < len; i++) msg += (char)payload[i];
  Serial.printf("RECEBIDO [%s]: %s\n", topico, msg.c_str());
  if (msg.startsWith("limite:")) {
    limite = msg.substring(7).toFloat();
    Serial.printf(" -> novo limite = %.1f\n", limite);
  } else if (msg.startsWith("led:")) {
    String e = msg.substring(4);
    ledOn = (e == "ON" || e == "1");
    digitalWrite(LED, ledOn ? HIGH : LOW);
    mqtt.publish(TOPICO_LED.c_str(), ledOn ? "ON" : "OFF");   // Tarefa 2: publica a mudanca
  }
}

void conectar() {
  while (!mqtt.connected()) {
    Serial.print("Conectando ao Mosquitto...");
    String id = String("esp32-") + NOME + "-" + String(random(9999));
    if (mqtt.connect(id.c_str())) {
      Serial.println(" ok");
      mqtt.subscribe(TOPICO_CMD.c_str());   // ouve o comando
    } else {
      Serial.printf(" falhou rc=%d (2s)\n", mqtt.state());
      delay(2000);
    }
  }
}

// Tarefa 1: publica temperatura e umidade em topicos separados
void publicarSensores() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();

  bool novoEstado = (!isnan(t) && t > limite);
  if (novoEstado != ledOn) {                          // Tarefa 2: so publica quando MUDA
    ledOn = novoEstado;
    mqtt.publish(TOPICO_LED.c_str(), ledOn ? "ON" : "OFF");
  }
  digitalWrite(LED, ledOn ? HIGH : LOW);

  if (!isnan(t)) mqtt.publish(TOPICO_TEMP.c_str(), String(t, 1).c_str());
  if (!isnan(h)) mqtt.publish(TOPICO_UMID.c_str(), String(h, 1).c_str());

  Serial.printf("temp=%.1f umid=%.1f led=%s (limite=%.1f)\n",
                t, h, ledOn ? "ON" : "OFF", limite);
}

// Tarefa 3: logs de Wi-Fi e de TLS em topicos proprios
void publicarLogs() {
  String wifiJson = String("{\"ssid\":\"") + WiFi.SSID() + "\",\"rssi\":" + String(WiFi.RSSI()) +
                    ",\"ip\":\"" + WiFi.localIP().toString() + "\",\"ms\":" + String(tempoConexao) + "}";
  mqtt.publish(TOPICO_WIFI.c_str(), wifiJson.c_str());

  bool relogioOk = (horaLocal() != "sem-hora");
  String tlsJson = String("{\"hora\":\"") + horaLocal() + "\",\"relogio_ok\":" + (relogioOk ? "true" : "false") + "}";
  mqtt.publish(TOPICO_HORA.c_str(), tlsJson.c_str());

  mqtt.publish(TOPICO_CICLOS.c_str(), String(ciclos).c_str());

  Serial.printf("log/wifi=%s\n", wifiJson.c_str());
  Serial.printf("log/hora=%s\n", tlsJson.c_str());
  Serial.printf("log/ciclos=%d\n", ciclos);
}

void setup() {
  Serial.begin(115200);
  pinMode(LED, OUTPUT);
  dht.begin();

  ciclos++;   // Tarefa 4: conta este despertar (RTC_DATA_ATTR sobreviveu ao deep sleep)
  Serial.printf("=== Ciclo #%d ===\n", ciclos);

  unsigned long t0 = millis();
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Conectando ao WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
  tempoConexao = millis() - t0;
  Serial.printf("\n ok | IP=%s | RSSI=%d dBm | %ld ms\n",
                WiFi.localIP().toString().c_str(), WiFi.RSSI(), tempoConexao);

  configTime(-3 * 3600, 0, "pool.ntp.org", "time.nist.gov");  // hora local (UTC-3) p/ o log de TLS

  mqtt.setServer("test.mosquitto.org", 1883);   // broker publico Eclipse Mosquitto
  mqtt.setCallback(aoReceber);
  conectar();

  // Publica tudo neste ciclo (topicos separados)
  publicarSensores();
  publicarLogs();

  // Tarefa 4: janela para RECEBER um comando antes de dormir (trade-off:
  // energia x resposta imediata — ver ENTREGA.md, pergunta 6)
  unsigned long janela = millis();
  while (millis() - janela < 5000) { mqtt.loop(); delay(10); }

  // Dorme para economizar energia; ao acordar, reinicia no setup()
  const uint64_t DORME_SEG = 30;
  Serial.printf("Dormindo por %llu s...\n", DORME_SEG);
  Serial.flush();
  esp_sleep_enable_timer_wakeup(DORME_SEG * 1000000ULL);
  esp_deep_sleep_start();
}

void loop() { }   // nunca executa: tudo esta no setup() por causa do Deep Sleep
