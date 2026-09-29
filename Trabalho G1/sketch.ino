/*
 * Leitor RFID de controle de acesso — ESP32 + MFRC522 + MQTT
 * Trabalho G1 — IoT — Yuri Garcia
 *
 * Requisitos cobertos: R1 (leitura/UID), R2 (MAC com retain),
 * R3 (hora via NTP), R4 (modo cadastro), R5 (REMOVER/LISTAR),
 * R6 (acesso liberado/negado), R7 (Serial Monitor).
 *
 * Bibliotecas necessárias (Library Manager do Wokwi):
 *   - MFRC522 (Miguel Balboa)
 *   - PubSubClient
 */

#include <SPI.h>
#include <MFRC522.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <time.h>

// ---------- Configuração ----------
#define SS_PIN   5
#define RST_PIN  22
#define LED_PIN  2

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASS = "";
const int   WIFI_CHANNEL = 6;

const char* MQTT_BROKER = "test.mosquitto.org";
const int   MQTT_PORT   = 1883;

// Troque "yuri-garcia" pelo seu nome, se necessário.
const String BASE_TOPIC = "sisla/yuri-garcia/rfid/";
const String TOPIC_MAC      = BASE_TOPIC + "mac";
const String TOPIC_CADASTRO = BASE_TOPIC + "cadastro";
const String TOPIC_ACESSO   = BASE_TOPIC + "acesso";
const String TOPIC_LISTA    = BASE_TOPIC + "lista";
const String TOPIC_CMD      = BASE_TOPIC + "cmd";

const long  GMT_OFFSET_SEC = -3 * 3600; // horário de Brasília
const int   DAYLIGHT_OFFSET_SEC = 0;
const char* NTP_SERVER = "pool.ntp.org";

const unsigned long DEBOUNCE_MS        = 2000;  // R1: ignora mesmo cartão em <2s
const unsigned long CADASTRO_DURACAO   = 15000; // R4: janela de 15s
const unsigned long RECONNECT_MQTT_MS  = 5000;
const unsigned long RECONNECT_WIFI_MS  = 5000;
const int           MAX_TAGS           = 10;    // R4: máximo de 10 cartões

// ---------- Objetos globais ----------
MFRC522 mfrc522(SS_PIN, RST_PIN);
WiFiClient espClient;
PubSubClient client(espClient);

// ---------- Estado: cartões cadastrados ----------
String uidList[MAX_TAGS];
int uidCount = 0;

// ---------- Estado: modo de operação ----------
enum Modo { MODO_NORMAL, MODO_CADASTRO };
Modo modoAtual = MODO_NORMAL;
unsigned long cadastroInicio = 0;

// ---------- Estado: debounce de leitura ----------
String lastUid = "";
unsigned long lastReadTime = 0;

// ---------- Estado: reconexão ----------
unsigned long lastWifiAttempt = 0;
unsigned long lastMqttAttempt = 0;

// ---------- Estado: LED não bloqueante ----------
enum LedMode { LED_OFF, LED_BLINK_CADASTRO, LED_HOLD_LIBERADO, LED_BLINK_NEGADO };
LedMode ledMode = LED_OFF;
unsigned long ledTimer = 0;
bool ledState = false;
int ledBlinkCount = 0;

// =====================================================================
// Utilitários
// =====================================================================

String formatUid(MFRC522::Uid uid) {
  String result = "";
  for (byte i = 0; i < uid.size; i++) {
    if (i > 0) result += " ";
    if (uid.uidByte[i] < 0x10) result += "0";
    result += String(uid.uidByte[i], HEX);
  }
  result.toUpperCase();
  return result;
}

String getHora() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo, 1000)) {
    return "00:00:00";
  }
  char buf[9];
  strftime(buf, sizeof(buf), "%H:%M:%S", &timeinfo);
  return String(buf);
}

int findUid(const String& uid) {
  for (int i = 0; i < uidCount; i++) {
    if (uidList[i] == uid) return i;
  }
  return -1;
}

bool addUid(const String& uid) {
  if (uidCount >= MAX_TAGS) return false;
  uidList[uidCount++] = uid;
  return true;
}

bool removeUid(const String& uid) {
  int idx = findUid(uid);
  if (idx == -1) return false;
  for (int i = idx; i < uidCount - 1; i++) {
    uidList[i] = uidList[i + 1];
  }
  uidCount--;
  return true;
}

// =====================================================================
// LED — controle não bloqueante (nunca usa delay())
// =====================================================================

void startLedCadastro() {
  ledMode = LED_BLINK_CADASTRO;
  ledTimer = millis();
  ledState = false;
  digitalWrite(LED_PIN, LOW);
}

void startLedLiberado() {
  ledMode = LED_HOLD_LIBERADO;
  ledTimer = millis();
  digitalWrite(LED_PIN, HIGH);
}

void startLedNegado() {
  ledMode = LED_BLINK_NEGADO;
  ledTimer = millis();
  ledBlinkCount = 0;
  ledState = true;
  digitalWrite(LED_PIN, HIGH);
}

void stopLed() {
  ledMode = LED_OFF;
  digitalWrite(LED_PIN, LOW);
}

void atualizarLed() {
  unsigned long now = millis();
  switch (ledMode) {
    case LED_OFF:
      break; // nada a fazer, LED já está no estado definido por quem chamou

    case LED_BLINK_CADASTRO:
      if (now - ledTimer >= 300) {
        ledTimer = now;
        ledState = !ledState;
        digitalWrite(LED_PIN, ledState ? HIGH : LOW);
      }
      break;

    case LED_HOLD_LIBERADO:
      if (now - ledTimer >= 2000) {
        stopLed();
      }
      break;

    case LED_BLINK_NEGADO:
      if (now - ledTimer >= 150) {
        ledTimer = now;
        ledState = !ledState;
        digitalWrite(LED_PIN, ledState ? HIGH : LOW);
        ledBlinkCount++;
        if (ledBlinkCount >= 6) { // 3 piscadas = 6 transições on/off
          stopLed();
        }
      }
      break;
  }
}

// =====================================================================
// Publicações MQTT (JSON montado manualmente — sem depender de libs extras)
// =====================================================================

void publicarMac() {
  String payload = "{\"mac\":\"" + WiFi.macAddress() +
                    "\",\"ip\":\"" + WiFi.localIP().toString() +
                    "\",\"hora\":\"" + getHora() + "\"}";
  client.publish(TOPIC_MAC.c_str(), payload.c_str(), true); // retain
  Serial.println("[MQTT] -> " + TOPIC_MAC + " (retain) " + payload);
}

void publicarCadastro(const String& uid, const String& status) {
  String payload = "{\"mac\":\"" + WiFi.macAddress() +
                    "\",\"uid\":\"" + uid +
                    "\",\"status\":\"" + status + "\"}";
  client.publish(TOPIC_CADASTRO.c_str(), payload.c_str());
  Serial.println("[MQTT] -> " + TOPIC_CADASTRO + " " + payload);
}

void publicarAcesso(const String& uid, const String& resultado) {
  String payload = "{\"mac\":\"" + WiFi.macAddress() +
                    "\",\"uid\":\"" + uid +
                    "\",\"resultado\":\"" + resultado +
                    "\",\"hora\":\"" + getHora() + "\"}";
  client.publish(TOPIC_ACESSO.c_str(), payload.c_str());
  Serial.println("[MQTT] -> " + TOPIC_ACESSO + " " + payload);
}

void publicarLista() {
  String tags = "";
  for (int i = 0; i < uidCount; i++) {
    if (i > 0) tags += ",";
    tags += "\"" + uidList[i] + "\"";
  }
  String payload = "{\"mac\":\"" + WiFi.macAddress() +
                    "\",\"tags\":[" + tags + "]}";
  client.publish(TOPIC_LISTA.c_str(), payload.c_str());
  Serial.println("[MQTT] -> " + TOPIC_LISTA + " " + payload);
}

// =====================================================================
// Modo cadastro (R4)
// =====================================================================

void entrarModoCadastro() {
  if (uidCount >= MAX_TAGS) {
    Serial.println("[MODO] Lista ja esta cheia, cadastro nao iniciado");
    publicarCadastro("", "lista cheia");
    return;
  }
  modoAtual = MODO_CADASTRO;
  cadastroInicio = millis();
  startLedCadastro();
  Serial.println("[MODO] CADASTRO iniciado, aguardando cartao por 15s...");
}

void sairModoCadastro() {
  modoAtual = MODO_NORMAL;
  stopLed();
  Serial.println("[MODO] Voltando para NORMAL");
}

void verificarTimeoutCadastro() {
  if (modoAtual != MODO_CADASTRO) return;
  if (millis() - cadastroInicio >= CADASTRO_DURACAO) {
    Serial.println("[MODO] Tempo esgotado no modo cadastro");
    publicarCadastro("", "tempo esgotado");
    sairModoCadastro();
  }
}

void processarCadastro(const String& uid) {
  if (findUid(uid) != -1) {
    Serial.println("[CADASTRO] Cartao ja cadastrado: " + uid);
    publicarCadastro(uid, "ja_cadastrada");
  } else if (uidCount >= MAX_TAGS) {
    Serial.println("[CADASTRO] Lista cheia: " + uid);
    publicarCadastro(uid, "lista cheia");
  } else {
    addUid(uid);
    Serial.println("[CADASTRO] Cartao cadastrado: " + uid);
    publicarCadastro(uid, "cadastrada");
  }
  sairModoCadastro();
}

// =====================================================================
// Modo normal — acesso do dia a dia (R6)
// =====================================================================

void processarAcesso(const String& uid) {
  if (findUid(uid) != -1) {
    Serial.println("[ACESSO] Liberado: " + uid);
    publicarAcesso(uid, "liberado");
    startLedLiberado();
  } else {
    Serial.println("[ACESSO] Negado: " + uid);
    publicarAcesso(uid, "negado");
    startLedNegado();
  }
}

// =====================================================================
// Leitura de cartão (R1)
// =====================================================================

void lerCartao() {
  if (!mfrc522.PICC_IsNewCardPresent() || !mfrc522.PICC_ReadCardSerial()) {
    return;
  }

  String uid = formatUid(mfrc522.uid);
  unsigned long now = millis();

  bool duplicado = (uid == lastUid) && (now - lastReadTime < DEBOUNCE_MS);
  lastUid = uid;
  lastReadTime = now;

  mfrc522.PICC_HaltA();
  mfrc522.PCD_StopCrypto1();

  if (duplicado) {
    return; // ignora o mesmo cartão lido de novo em menos de 2s
  }

  Serial.println("[RFID] UID lido: " + uid + " (modo atual: " +
                  (modoAtual == MODO_CADASTRO ? "CADASTRO" : "NORMAL") + ")");

  if (modoAtual == MODO_CADASTRO) {
    processarCadastro(uid);
  } else {
    processarAcesso(uid);
  }
}

// =====================================================================
// Comandos recebidos em .../cmd
// =====================================================================

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  String msg;
  for (unsigned int i = 0; i < length; i++) {
    msg += (char)payload[i];
  }
  msg.trim();

  Serial.println("[CMD] Recebido em " + String(topic) + ": \"" + msg + "\"");

  String upperMsg = msg;
  upperMsg.toUpperCase();

  if (upperMsg == "CADASTRO") {
    entrarModoCadastro();

  } else if (upperMsg == "LISTAR") {
    publicarLista();

  } else if (upperMsg.startsWith("REMOVER")) {
    String uid = msg.substring(7); // tamanho de "REMOVER"
    uid.trim();
    uid.toUpperCase();
    if (uid.length() == 0) {
      Serial.println("[CMD] REMOVER sem UID informado, ignorado");
      return;
    }
    if (removeUid(uid)) {
      Serial.println("[CMD] Cartao removido: " + uid);
      publicarCadastro(uid, "removida");
    } else {
      Serial.println("[CMD] Cartao nao encontrado: " + uid);
      publicarCadastro(uid, "nao_encontrada");
    }

  } else {
    Serial.println("[CMD] Comando desconhecido: " + msg);
  }
}

// =====================================================================
// Conectividade: Wi-Fi, NTP e MQTT
// =====================================================================

void conectarWifiInicial() {
  Serial.print("[WiFi] Conectando a " + String(WIFI_SSID));
  WiFi.begin(WIFI_SSID, WIFI_PASS, WIFI_CHANNEL);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();
  Serial.println("[WiFi] Conectado! IP: " + WiFi.localIP().toString());
}

void manterWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  unsigned long now = millis();
  if (now - lastWifiAttempt < RECONNECT_WIFI_MS) return;
  lastWifiAttempt = now;
  Serial.println("[WiFi] Conexao perdida, tentando reconectar...");
  WiFi.reconnect();
}

void sincronizarHora() {
  Serial.print("[NTP] Sincronizando hora");
  configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);
  struct tm timeinfo;
  int tentativas = 0;
  while (!getLocalTime(&timeinfo, 1000) && tentativas < 20) {
    Serial.print(".");
    tentativas++;
  }
  Serial.println();
  Serial.println("[NTP] Hora atual: " + getHora());
}

bool conectarMqtt() {
  String clientId = "ESP32-yuri-garcia-" + String(random(0xFFFF), HEX);
  Serial.println("[MQTT] Conectando a " + String(MQTT_BROKER) +
                  " como " + clientId + " ...");
  if (client.connect(clientId.c_str())) {
    Serial.println("[MQTT] Conectado!");
    client.subscribe(TOPIC_CMD.c_str());
    Serial.println("[MQTT] Inscrito em " + TOPIC_CMD);
    publicarMac();
    return true;
  }
  Serial.println("[MQTT] Falha ao conectar, rc=" + String(client.state()));
  return false;
}

void manterMqtt() {
  if (client.connected()) {
    client.loop();
    return;
  }
  unsigned long now = millis();
  if (now - lastMqttAttempt < RECONNECT_MQTT_MS) return;
  lastMqttAttempt = now;
  conectarMqtt();
}

// =====================================================================
// setup() / loop()
// =====================================================================

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n=== Leitor RFID de controle de acesso ===");

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  SPI.begin();
  mfrc522.PCD_Init();
  Serial.println("[RFID] MFRC522 inicializado");

  conectarWifiInicial();
  sincronizarHora();

  randomSeed(micros());
  client.setBufferSize(512); // .../lista com 10 UIDs de 7 bytes passa de 256 bytes
  client.setKeepAlive(60);   // keepalive maior que o padrão (15s) evita quedas
                             // por latência da rede simulada do Wokwi
  client.setServer(MQTT_BROKER, MQTT_PORT);
  client.setCallback(mqttCallback);

  conectarMqtt();

  Serial.println("[MODO] Iniciando em modo NORMAL");
}

void loop() {
  manterWifi();
  manterMqtt();

  lerCartao();
  verificarTimeoutCadastro();
  atualizarLed();
}
