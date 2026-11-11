# Silo de grãos — IoT (Trabalho N2)

Nó com bateria que **sente** umidade e temperatura do silo (DHT22), **decide sozinho** (borda) quando ligar o
ventilador e **age** (LED = ventilador; na prática, um relé). O resultado vai por **MQTT/TLS** a uma ponte que
grava o histórico num **Worker** (D1 + KV) e alimenta um **painel** com comando confirmado e alertas com cooldown.

Caderno do projeto (decisões e justificativas): [`docs/Caderno_de_Projeto_Silo.docx`](docs/Caderno_de_Projeto_Silo.docx)
(fonte em [`docs/Caderno_de_Projeto_Silo.md`](docs/Caderno_de_Projeto_Silo.md)).

```
ESP32 + DHT22 + ventilador ──MQTT/TLS 8883──► broker ◄──MQTT/TLS── ponte.py ──HTTP+token──► Worker (D1 + KV)
   decide offline, dorme                                              │  ▲                          ▲
                                                                      ▼  │ comando assinado         │ GET histórico
                                                                  API local 127.0.0.1:8790 ◄── painel/index.html
```

## O que cada pasta faz
| Pasta | Conteúdo |
|---|---|
| `esp32/silo/` | Firmware (`silo.ino`). `config.example.h` → `config.h` (segredos, fora do Git). `baixar_ca.py` gera `ca_cert.h`. |
| `wokwi/` | `diagram.json` e `libraries.txt` para simular no Wokwi (DHT22 + LED + potenciômetro = bateria). |
| `worker/` | Cloudflare Worker (`worker.js`), `schema.sql` (D1), `wrangler.toml`, teste `teste_worker.mjs`. |
| `servico/` | `ponte.py`: confere assinatura, grava, alerta com cooldown, vigia o silo, assina e envia comandos. |
| `painel/` | `index.html`: estado, gráfico 24 h, comando com confirmação, alertas, resumo SQL por hora. |
| `teste/` | `teste_ponte.py`, `e2e_broker.py`, `teste_painel.py` (automáticos), `ataque_comando_falso.py` (ataque ao tópico de comando). |
| `docs/` | Caderno, `autonomia.py` (cálculo da bateria). |

## Como montar e rodar

**Contas:** nenhuma nova se você já tem GitHub e usa o Wokwi. O Worker roda **local** (`wrangler dev --local`, sem conta
Cloudflare) e o broker é o público `test.mosquitto.org` (sem conta). Para publicar o Worker depois: ver `wrangler.toml`.

1. **CA do broker** (uma vez): `cd esp32/silo && python baixar_ca.py` → gera `ca_cert.h` e `mosquitto_ca.pem`.
2. **Segredos:**
   - `esp32/silo/config.example.h` → `config.h` (Wi-Fi, `HMAC_KEY` aleatória: `python -c "import secrets;print(secrets.token_hex(32))"`).
   - `worker/.dev.vars.example` → `worker/.dev.vars` (dois tokens).
   - `servico/.env.example` → `servico/.env` (mesma `HMAC_KEY`, `TOKEN_ESCRITA` igual ao do Worker, `TOKEN_COMANDO`).
3. **Worker:** `cd worker && npm install && npm run db:init && npm run dev` (porta 8788).
4. **Ponte:** `pip install paho-mqtt requests && python servico/ponte.py`.
5. **ESP32:** no Wokwi, crie o projeto com `wokwi/diagram.json`, `wokwi/libraries.txt`, `silo.ino`, `config.h` e `ca_cert.h`
   (use uma `HMAC_KEY` **de teste** no Wokwi, nunca a da produção). Na placa real, abra `silo.ino` na Arduino IDE
   (ESP32 board package; bibliotecas: PubSubClient, ArduinoJson 7, DHT sensor library).
6. **Painel:** abra `painel/index.html`, expanda *Conexões e tokens* e informe `TOKEN_COMANDO` e `TOKEN_LEITURA`.

## Como testar
```bash
# Worker (precisa estar rodando)
cd worker && TOKEN_ESCRITA=... TOKEN_LEITURA=... node teste_worker.mjs     # 25 verificações
# Ponte (precisa do Worker rodando; não precisa de broker nem ESP32)
python teste/teste_ponte.py                                                # 15 verificações
# Ataque: comandos falsos no tópico (com o ESP32/Wokwi ligado)
python teste/ataque_comando_falso.py
# Ponta a ponta com broker real (internet) e painel num Chrome headless
python teste/e2e_broker.py
python teste/teste_painel.py
# Autonomia
python docs/autonomia.py
```
Roteiro dos testes no hardware/Wokwi (limite, falha, reinício, 10 min): Etapa 10 do caderno.

## Decisões em uma linha
- **Decide na borda:** o grão não pode esperar a rede; o ESP32 dorme e a nuvem não consegue "chamá-lo".
- **Histerese** (liga 70 %, desliga 65 %) e **estado seguro** (3 falhas seguidas do sensor → ventila + alerta).
- **Comando retido + HMAC + sequência:** o ESP32 acorda, recebe, valida e confirma (ack) em ~1,5 s de rádio; broker público não é confiável.
- **Painel por polling:** o dado só muda a cada ciclo (minutos); WebSocket manteria conexão aberta à toa.
- **Sem rede:** decide local, guarda até 24 leituras na RTC e reenvia na volta.
