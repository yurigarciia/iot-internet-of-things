# ENTREGA — Atividade IoT: Sensor físico na nuvem com KV + Cloudflare Workers

## 1. O que é o Cloudflare Workers e o que é o KV?

O **Cloudflare Workers** é uma plataforma de computação *serverless*: em vez de manter um
servidor próprio rodando o tempo todo, escrevemos uma função em JavaScript, fazemos o
*deploy* e a Cloudflare cuida de executá-la sob demanda, em servidores espalhados pelo mundo
("na borda"), próximos de quem faz a requisição. Ela funciona como a **porta de entrada** da
nossa API: recebe requisições HTTP e decide o que fazer com elas.

O **Cloudflare KV** é um banco de dados **chave-valor**: não tem tabelas nem SQL, apenas pares
`chave → valor` (por exemplo, `sensor:temp:last → { "valor": 27.8, "timestamp": ... }`). É
onde os dados realmente ficam armazenados, sobrevivendo a reinícios do ESP32 e a novos
*deploys* do Worker. Ele tem **consistência eventual**: uma leitura logo após a gravação pode,
por alguns segundos, ainda não refletir o valor novo.

## 2. O caminho de um dado desde o sensor físico até ficar salvo no KV

1. O nó sensor **acorda** (ou liga) e conecta-se ao **Wi-Fi** em modo estação.
2. Ele **lê a temperatura** no sensor DHT11 conectado ao GPIO 4.
3. Monta uma requisição **`POST /insert`** com corpo JSON `{ "sensor": "temp", "valor": 27.8 }`
   e envia via HTTPS para a URL do Worker.
4. O **Worker** recebe a requisição, identifica o caminho `/insert` e o método `POST`, faz o
   `await request.json()` para extrair `sensor` e `valor`.
5. O Worker chama **`env.KV_SENSOR.put(...)`**, gravando a chave `sensor:temp:last` (e, na
   versão com histórico, também `sensor:temp:<timestamp>`) com o valor e o timestamp atual.
6. O KV persiste esse par chave-valor. A partir daí, qualquer requisição `GET /get` ou
   `GET /list` pode recuperar esse dado.

## 3. O que o Deep Sleep desliga no ESP32 e por que economiza energia?

O **Deep Sleep** desliga a **CPU** e o **rádio Wi-Fi**, mantendo ativo apenas um circuito de
baixíssimo consumo (o RTC/temporizador) responsável por acordar o chip depois de um tempo
definido. Como o Wi-Fi ligado consome entre **~80 e 160 mA**, mantê-lo ativo o tempo todo
esgotaria rapidamente uma bateria. Em deep sleep, o consumo cai para a casa dos
**microamperes** — ordens de grandeza menor. A troca é que os dados só chegam **em
intervalos** (por exemplo, a cada 30 s), e não de forma contínua, mas isso é aceitável para a
maioria dos sensores ambientais, que não mudam tão rápido assim.

## 4. Por que a variável de contagem usa `RTC_DATA_ATTR`? O que aconteceria sem isso?

Ao entrar em deep sleep e depois acordar, o ESP32 **reinicia por completo** e executa o
`setup()` novamente — é como se tivesse sido religado. Toda variável comum perderia seu valor
nesse processo, voltando ao valor inicial. A variável `envios`, marcada com `RTC_DATA_ATTR`,
fica armazenada na memória RTC, que **não é apagada** durante o deep sleep (só em um reset
completo por energização ou botão reset). Sem esse atributo, a variável `envios` voltaria a
`0` a cada ciclo de sono/despertar, tornando impossível contar quantos envios já foram feitos
ao longo do tempo.

## 5. Por que o nó sensor dorme, mas o nó atuador fica ligado?

O nó sensor só precisa **acordar periodicamente**, medir e enviar um valor — não há motivo
para ficar ativo entre uma leitura e outra, então dormir economiza energia (importante para um
dispositivo a bateria). Já o nó atuador precisa estar **sempre pronto para reagir** assim que
a condição (temperatura acima do limite) for verdadeira — se ele também dormisse, poderia
demorar para perceber uma mudança de estado e acender/apagar o LED com atraso. Por isso ele
normalmente fica ligado na tomada, sem deep sleep, apenas fazendo consultas periódicas
(`GET /get`) dentro do `loop()`.

## 6. Por que o ESP32 precisa conectar no Wi-Fi antes de enviar a leitura?

Toda a comunicação com o Worker acontece via **HTTP/HTTPS sobre a rede**, e isso só é possível
se o ESP32 já tiver uma conexão de rede estabelecida (endereço IP, rota até a internet, etc.).
Se o código tentasse fazer a requisição HTTP antes do Wi-Fi estar conectado
(`WiFi.status() == WL_CONNECTED`), a chamada falharia porque não haveria caminho de rede até o
Worker — por isso o código espera ativamente a conexão ser estabelecida antes de prosseguir
para a leitura e o envio dos dados.

---

## Arquivos desta entrega

- `worker/worker.js` — Worker com `/insert`, `/get` e `/list` (histórico).
- `esp32/no_sensor/no_sensor.ino` — nó sensor (DHT11 + Wi-Fi + POST + Deep Sleep).
- `esp32/no_atuador/no_atuador.ino` — nó atuador (LED + GET + limite de temperatura).
- `esp32/config.h.example` — modelo de credenciais (copiar para `config.h`, não versionar).
