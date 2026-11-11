// Copie para "config.h" e preencha. NAO versione o config.h (esta no .gitignore).
// No Wokwi: crie um arquivo config.h na aba do projeto com estes valores.

#define WIFI_SSID   "Wokwi-GUEST"      // simulador; na placa real: sua rede 2,4 GHz
#define WIFI_PASS   ""
#define WIFI_CANAL  6                  // so Wokwi; apague esta linha na placa real

#define GRUPO       "yuripaim"         // mesmo nome no servico, no painel e nos topicos
#define SILO        "silo01"

#define MQTT_HOST   "test.mosquitto.org"
#define MQTT_PORT   8883               // TLS (a 1883 e texto puro: NAO usar)

// Chave compartilhada que assina os comandos (HMAC-SHA256). Gere uma propria:
//   python -c "import secrets; print(secrets.token_hex(32))"
// Tem que ser IDENTICA a HMAC_KEY do servico/.env
#define HMAC_KEY    "TROQUE-ESTA-CHAVE-POR-UMA-ALEATORIA-DE-64-HEX"

#define SLEEP_S     30                 // demo: 30 s. Producao: 1800 (30 min) -> ~350 dias de bateria (docs/autonomia.py)
