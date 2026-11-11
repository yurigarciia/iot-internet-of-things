// ================================================================
//  SILO DE GRAOS — no sensor/atuador com bateria (ESP32 + DHT + ventilador)
//
//  Ciclo (tudo acontece no setup(), porque o deep sleep reinicia a placa):
//    acorda -> le sensor -> DECIDE SOZINHO (borda) -> aciona ventilador
//           -> Wi-Fi + NTP + MQTT/TLS -> recebe comando (retido) -> ack
//           -> publica telemetria/estado -> dorme (ventilador segue como esta)
//
//  Seguranca: TLS com CA conferida (nunca setInsecure); comandos que ENTRAM
//  e dados que SAEM assinados com HMAC-SHA256 (comando tambem tem numero de
//  sequencia contra replay); segredos so no config.h (fora do Git) e nunca
//  impressos no Serial.
// ================================================================
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <Preferences.h>
#include <time.h>
#include "mbedtls/md.h"
#include "driver/gpio.h"
#include "config.h"      // Wi-Fi, grupo, broker, chave HMAC, tempo de sono (NAO versionar)
#include "ca_cert.h"     // CA do broker (gerado por baixar_ca.py)

// ---------------- Hardware ----------------
#define DHTPIN   4
#define DHTTYPE  DHT22      // kit fisico com DHT11? troque para DHT11
#define FAN_PIN  2          // LED = ventilador (na pratica: rele/MOSFET)
#define BAT_PIN  34         // divisor de tensao 1:1 da bateria (potenciometro no Wokwi)

// ---------------- Regra (padroes; podem ser trocados por comando) ----------------
#define LIGA_U_PADRAO     70.0f   // liga se umidade >= 70 %
#define DESLIGA_U_PADRAO  65.0f   // desliga se umidade <= 65 %   (histerese de 5 pontos)
#define LIGA_T_PADRAO     35.0f   // liga se temperatura >= 35 C  (ponto quente no grao)
#define DESLIGA_T_PADRAO  32.0f   // desliga se temperatura <= 32 C
#define FALHAS_MAX        3       // leituras invalidas seguidas ate entrar em estado seguro
#define MANUAL_CICLOS     8       // modo manual vale por N despertares e volta para auto
#define BAT_BAIXA_V       3.4f    // abaixo disso: dorme o dobro e avisa
#define FILA_N            24      // leituras guardadas na RTC enquanto estiver sem internet

// ---------------- Memoria que sobrevive ao deep sleep ----------------
struct Amostra { uint32_t ts; int16_t t10; int16_t u10; uint8_t vent; uint8_t ok; };
RTC_DATA_ATTR uint32_t ciclo = 0;
RTC_DATA_ATTR uint8_t  filaN = 0;
RTC_DATA_ATTR Amostra  fila[FILA_N];

// Estado que decide o ventilador: fica na NVS (e nao so na RTC) porque a histerese precisa dele
// para sempre. Se a placa reiniciar por falta de energia (ou num simulador que perde a RTC no
// "sono", como o Wokwi), a RTC volta a zero e o ventilador ligado seria desligado a 68 %.
// So escreve quando o valor MUDA (poucas vezes por dia), entao nao gasta a flash.
uint8_t ventilador = 0;
uint8_t modo = 0;                           // 0 = auto, 1 = manual ligado, 2 = manual desligado
int8_t  manualTtl = 0;
uint8_t falhas = 0;

// ---------------- Memoria permanente (NVS): sobrevive a queda de energia ----------------
Preferences prefs;
uint32_t ultSeq = 0;
float ligaU, desligaU, ligaT, desligaT;

DHT dht(DHTPIN, DHTTYPE);
WiFiClientSecure rede;
PubSubClient mqtt(rede);

String BASE = String("sis1a/") + GRUPO + "/" + SILO + "/";
String T_TELE = BASE + "telemetria";
String T_ESTADO = BASE + "estado";
String T_CMD = BASE + "comando";
String T_ACK = BASE + "ack";

float temp = NAN, umid = NAN, batV = 0;
bool  sensorOk = false;

// ================================================================
//  Utilidades
// ================================================================
uint32_t agora() {                       // epoch em s, ou 0 se o relogio nunca foi acertado
  time_t t = time(nullptr);
  return t > 1700000000 ? (uint32_t)t : 0;
}

void salvarEstado() {
  if (prefs.getUChar("vent", 0) != ventilador) prefs.putUChar("vent", ventilador);
  if (prefs.getUChar("modo", 0) != modo)       prefs.putUChar("modo", modo);
  if (prefs.getChar("ttl", 0) != manualTtl)    prefs.putChar("ttl", manualTtl);
  if (prefs.getUChar("falhas", 0) != falhas)   prefs.putUChar("falhas", falhas);
}

void aplicarVentilador() {
  gpio_hold_dis((gpio_num_t)FAN_PIN);    // libera o pino que ficou "preso" durante o sono
  pinMode(FAN_PIN, OUTPUT);
  digitalWrite(FAN_PIN, ventilador ? HIGH : LOW);
}

const char* nomeModo() { return modo == 0 ? "auto" : (modo == 1 ? "manual_on" : "manual_off"); }

bool hmacHex(const String& msg, char out[65]) {
  uint8_t h[32];
  const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if (mbedtls_md_hmac(info, (const uint8_t*)HMAC_KEY, strlen(HMAC_KEY),
                      (const uint8_t*)msg.c_str(), msg.length(), h) != 0) return false;
  for (int i = 0; i < 32; i++) sprintf(out + 2 * i, "%02x", h[i]);
  return true;
}

bool igualConstante(const char* a, const char* b, size_t n) {   // nao vaza onde diferiu
  uint8_t d = 0;
  for (size_t i = 0; i < n; i++) d |= (uint8_t)(a[i] ^ b[i]);
  return d == 0;
}

// Assina o JSON que SAI do ESP32: HMAC do texto inteiro, anexado como ultimo campo "mac".
// O servico confere antes de gravar: quem so conhece o topico nao consegue forjar telemetria.
String assinar(const String& s) {
  char mac[65];
  if (!hmacHex(s, mac)) return s;
  return s.substring(0, s.length() - 1) + ",\"mac\":\"" + mac + "\"}";
}

// ================================================================
//  Sensor
// ================================================================
void lerSensores() {
  for (int i = 0; i < 3; i++) {                        // DHT as vezes falha: tenta 3x
    temp = dht.readTemperature();
    umid = dht.readHumidity();
    if (!isnan(temp) && !isnan(umid)) break;
    if (i < 2) delay(2100);                            // DHT22 precisa de >= 2 s entre leituras
  }
  sensorOk = !isnan(temp) && !isnan(umid);
  falhas = sensorOk ? 0 : (falhas < 250 ? falhas + 1 : falhas);
  batV = analogReadMilliVolts(BAT_PIN) * 2.0f / 1000.0f;   // divisor 1:1
  Serial.printf("temp=%.1f umid=%.1f ok=%d falhas=%u bat=%.2fV\n", temp, umid, sensorOk, falhas, batV);
}

// ================================================================
//  DECISAO (roda na borda, sem depender de rede)
// ================================================================
void decidir() {
  if (modo == 1)      ventilador = 1;
  else if (modo == 2) ventilador = 0;
  else if (!sensorOk) {
    if (falhas >= FALHAS_MAX) ventilador = 1;          // ESTADO SEGURO: sem dado, ventila
    // senao: mantem o estado anterior ate confirmar a falha
  } else if (!ventilador && (umid >= ligaU || temp >= ligaT)) {
    ventilador = 1;
  } else if (ventilador && umid <= desligaU && temp <= desligaT) {
    ventilador = 0;
  }
  aplicarVentilador();
  salvarEstado();
  Serial.printf("ventilador=%s modo=%s\n", ventilador ? "ON" : "OFF", nomeModo());
}

// ================================================================
//  Comandos assinados
// ================================================================
void publicarAck(uint32_t seq, const char* cmd, bool ok, const char* motivo) {
  JsonDocument d;
  d["seq"] = seq; d["cmd"] = cmd; d["ok"] = ok; d["motivo"] = motivo;
  d["ventilador"] = ventilador; d["modo"] = nomeModo(); d["ciclo"] = ciclo; d["ts"] = agora();
  String s; serializeJson(d, s);
  mqtt.publish(T_ACK.c_str(), assinar(s).c_str(), true);   // retido: o servico ve o ultimo ack
}

void aoReceber(char* topico, byte* payload, unsigned int len) {
  JsonDocument d;
  if (deserializeJson(d, payload, len)) { Serial.println("comando: JSON invalido, ignorado"); return; }
  uint32_t seq = d["seq"].as<uint32_t>();   // "| 0" truncaria seq > 2^31 para 0
  String cmd = d["cmd"] | "";
  String valor = d["valor"] | "";
  const char* mac = d["mac"] | "";

  if (seq <= ultSeq) {                                  // replay ou comando ja tratado: silencio
    Serial.printf("comando seq=%u ja visto (ultimo=%u), ignorado\n", seq, ultSeq);
    return;
  }
  char esperado[65];
  String msg = String(seq) + "|" + cmd + "|" + valor;
  if (!hmacHex(msg, esperado) || strlen(mac) != 64 || !igualConstante(mac, esperado, 64)) {
    Serial.printf("comando seq=%u REJEITADO: assinatura invalida\n", seq);
    publicarAck(seq, cmd.c_str(), false, "assinatura_invalida");
    return;                                             // NAO avanca ultSeq: atacante nao queima sequencia
  }

  bool ok = true; const char* motivo = "ok";
  if (cmd == "ventilador") {
    if (valor == "auto")     { modo = 0; manualTtl = 0; }
    else if (valor == "on")  { modo = 1; manualTtl = MANUAL_CICLOS; }
    else if (valor == "off") { modo = 2; manualTtl = MANUAL_CICLOS; }
    else { ok = false; motivo = "valor_invalido"; }
  } else if (cmd == "limites") {                        // valor = "ligaU,desligaU,ligaT,desligaT"
    float a, b, c, e;
    if (sscanf(valor.c_str(), "%f,%f,%f,%f", &a, &b, &c, &e) == 4 &&
        a >= 40 && a <= 95 && b >= 30 && b <= a - 2 && c >= 20 && c <= 60 && e >= 10 && e <= c - 2) {
      ligaU = a; desligaU = b; ligaT = c; desligaT = e;
      prefs.putFloat("ligaU", a); prefs.putFloat("desligaU", b);
      prefs.putFloat("ligaT", c); prefs.putFloat("desligaT", e);
    } else { ok = false; motivo = "limites_invalidos"; }
  } else { ok = false; motivo = "cmd_desconhecido"; }

  ultSeq = seq; prefs.putUInt("seq", seq);              // so consome a sequencia de comando AUTENTICO
  Serial.printf("comando seq=%u %s=%s -> %s\n", seq, cmd.c_str(), valor.c_str(), motivo);
  if (ok) decidir();                                    // aplica na hora, sem esperar o proximo ciclo
  publicarAck(seq, cmd.c_str(), ok, motivo);
}

// ================================================================
//  Rede
// ================================================================
bool conectarWifi() {
  WiFi.mode(WIFI_STA);
#ifdef WIFI_CANAL
  WiFi.begin(WIFI_SSID, WIFI_PASS, WIFI_CANAL);
#else
  WiFi.begin(WIFI_SSID, WIFI_PASS);
#endif
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 10000) delay(200);   // no maximo 10 s: bateria
  Serial.printf("wifi %s (%lu ms)\n", WiFi.status() == WL_CONNECTED ? "ok" : "FALHOU", millis() - t0);
  return WiFi.status() == WL_CONNECTED;
}

bool acertarRelogio() {                                  // TLS valida validade do certificado: precisa de hora
  configTime(-3 * 3600, 0, "pool.ntp.org", "time.google.com");
  unsigned long t0 = millis();
  while (agora() == 0 && millis() - t0 < 8000) delay(200);
  return agora() != 0;
}

bool conectarMqtt() {
  rede.setCACert(CA_CERT);                               // confere o servidor; sem setInsecure()
  rede.setTimeout(5);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(aoReceber);
  mqtt.setBufferSize(512);
  mqtt.setSocketTimeout(5);
  String id = String("esp32-") + GRUPO + "-" + SILO + "-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  if (!mqtt.connect(id.c_str())) {
    Serial.printf("mqtt FALHOU rc=%d\n", mqtt.state());
    return false;
  }
  mqtt.subscribe(T_CMD.c_str(), 1);
  return true;
}

// ================================================================
//  Publicacao
// ================================================================
String jsonTele(uint32_t ts, float t, float u, uint8_t vent, bool ok, bool atrasada) {
  JsonDocument d;
  d["v"] = 1; d["silo"] = SILO; d["ts"] = ts; d["ciclo"] = ciclo;
  if (ok) { d["temp_c"] = serialized(String(t, 1)); d["umid_pct"] = serialized(String(u, 1)); }
  else    { d["temp_c"] = nullptr; d["umid_pct"] = nullptr; }
  d["ventilador"] = vent; d["modo"] = nomeModo(); d["sensor_ok"] = ok;
  d["bat_v"] = serialized(String(batV, 2)); d["rssi"] = WiFi.RSSI(); d["atrasada"] = atrasada;
  String s; serializeJson(d, s);
  return assinar(s);
}

void publicarTudo() {
  for (uint8_t i = 0; i < filaN; i++) {                  // primeiro o que ficou guardado (volta da internet)
    String s = jsonTele(fila[i].ts, fila[i].t10 / 10.0f, fila[i].u10 / 10.0f, fila[i].vent, fila[i].ok, true);
    mqtt.publish(T_TELE.c_str(), s.c_str());
  }
  filaN = 0;
  mqtt.publish(T_TELE.c_str(), jsonTele(agora(), temp, umid, ventilador, sensorOk, false).c_str());

  JsonDocument d;                                        // estado retido: quem conecta depois ja ve
  d["ts"] = agora(); d["ventilador"] = ventilador; d["modo"] = nomeModo(); d["manual_ttl"] = manualTtl;
  d["liga_u"] = ligaU; d["desliga_u"] = desligaU; d["liga_t"] = ligaT; d["desliga_t"] = desligaT;
  d["seq"] = ultSeq; d["sleep_s"] = SLEEP_S; d["bat_baixa"] = batV < BAT_BAIXA_V; d["fw"] = "1.0";
  String s; serializeJson(d, s);
  mqtt.publish(T_ESTADO.c_str(), assinar(s).c_str(), true);
}

void guardarNaFila() {                                   // sem internet: nao perde a leitura
  if (filaN >= FILA_N) { memmove(&fila[0], &fila[1], sizeof(Amostra) * (FILA_N - 1)); filaN = FILA_N - 1; }
  fila[filaN++] = { agora(), (int16_t)(sensorOk ? temp * 10 : 0), (int16_t)(sensorOk ? umid * 10 : 0),
                    ventilador, (uint8_t)sensorOk };
  Serial.printf("sem rede: leitura guardada na RTC (%u/%d)\n", filaN, FILA_N);
}

void dormir() {
  uint64_t seg = SLEEP_S;
  if (batV > 0.5f && batV < BAT_BAIXA_V) seg *= 2;       // bateria baixa: acorda menos
  gpio_hold_en((gpio_num_t)FAN_PIN);                     // ventilador continua ligado/desligado dormindo
  gpio_deep_sleep_hold_en();
  Serial.printf("dormindo %llu s | acordado por %lu ms\n\n", seg, millis());
  Serial.flush();
  esp_sleep_enable_timer_wakeup(seg * 1000000ULL);
  esp_deep_sleep_start();
}

// ================================================================
void setup() {
  Serial.begin(115200);
  ciclo++;
  Serial.printf("\n=== %s ciclo #%u ===\n", SILO, ciclo);

  prefs.begin("silo", false);
  ultSeq   = prefs.getUInt("seq", 0);
  ligaU    = prefs.getFloat("ligaU", LIGA_U_PADRAO);
  desligaU = prefs.getFloat("desligaU", DESLIGA_U_PADRAO);
  ligaT    = prefs.getFloat("ligaT", LIGA_T_PADRAO);
  desligaT = prefs.getFloat("desligaT", DESLIGA_T_PADRAO);
  ventilador = prefs.getUChar("vent", 0);
  modo       = prefs.getUChar("modo", 0);
  manualTtl  = prefs.getChar("ttl", 0);
  falhas     = prefs.getUChar("falhas", 0);

  aplicarVentilador();                                   // reassume o estado guardado
  if (modo != 0 && --manualTtl <= 0) { modo = 0; manualTtl = 0; Serial.println("modo manual expirou -> auto"); }

  dht.begin();
  lerSensores();
  decidir();                                             // 1) decide ANTES da rede: funciona offline

  bool online = false;
  if (conectarWifi() && acertarRelogio() && conectarMqtt()) {
    online = true;
    unsigned long t0 = millis();                         // 2) o comando retido chega logo apos o subscribe
    while (millis() - t0 < 1500) { mqtt.loop(); delay(10); }
    publicarTudo();
    mqtt.loop(); delay(150);
    mqtt.disconnect();
  }
  if (!online) guardarNaFila();
  WiFi.disconnect(true, false);
  dormir();
}

void loop() {}
