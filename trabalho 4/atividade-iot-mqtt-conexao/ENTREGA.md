# Entrega — Trabalho MQTT (Mosquitto): tópicos, logs e Deep Sleep

**Turma:** AMF 2026-02
**Seu prefixo de tópico:** `sis1a/yuripaim/`
**Serviço usado:** (x) Python  ( ) HTML

---

## Checklist do que foi feito

- [x] Tarefa 1 — temperatura e umidade em **tópicos separados** (`.../temp`, `.../umid`)
- [x] Tarefa 2 — **tópico do LED** (`.../led` = ON/OFF)
- [x] Tarefa 3 — **logs** de Wi-Fi e TLS em tópicos próprios
- [x] Tarefa 4 — **Deep Sleep** com contador de ciclos (`RTC_DATA_ATTR`)
- [x] Tarefa 5 — serviço (Python) lendo os novos tópicos e enviando comando

Tópicos publicados pelo ESP32:

```
sis1a/yuripaim/temp        -> valor da temperatura
sis1a/yuripaim/umid        -> valor da umidade
sis1a/yuripaim/led         -> ON / OFF (só quando muda)
sis1a/yuripaim/log/wifi    -> {"ssid","rssi","ip","ms"}
sis1a/yuripaim/log/hora    -> {"hora","relogio_ok"}
sis1a/yuripaim/log/ciclos  -> contador de despertares (RTC_DATA_ATTR)
sis1a/yuripaim/comando     -> (assinado) recebe "limite:N" ou "led:ON/OFF"
```

---

## Evidências (`servico.py` + simulador do ESP32 em `teste/simulate_esp32.py`)

```
Comandos: um NUMERO = novo limite | 'on'/'off' = LED | 'sair' = encerrar
> Conectado ao Mosquitto. Ouvindo sis1a/yuripaim/#

  [enviado] limite:25
>   [recebido] sis1a/yuripaim/comando = limite:25
  [recebido] sis1a/yuripaim/temp = 31.2
  [recebido] sis1a/yuripaim/umid = 56.7
  [recebido] sis1a/yuripaim/log/wifi = {"ssid": "MinhaRede", "rssi": -62, "ip": "192.168.0.42", "ms": 801}
  [recebido] sis1a/yuripaim/log/hora = {"hora": "2026-09-29 21:18:05", "relogio_ok": true}
  [recebido] sis1a/yuripaim/log/ciclos = 4
  [recebido] sis1a/yuripaim/temp = 29.2
  [recebido] sis1a/yuripaim/umid = 60.6
  [recebido] sis1a/yuripaim/log/wifi = {"ssid": "MinhaRede", "rssi": -61, "ip": "192.168.0.42", "ms": 579}
  [recebido] sis1a/yuripaim/log/hora = {"hora": "2026-09-29 21:18:15", "relogio_ok": true}
  [recebido] sis1a/yuripaim/log/ciclos = 5
  [enviado] led:ON
>   [recebido] sis1a/yuripaim/comando = led:ON
  [recebido] sis1a/yuripaim/led = ON
  [recebido] sis1a/yuripaim/temp = 29.7
  [recebido] sis1a/yuripaim/umid = 60.1
  [recebido] sis1a/yuripaim/log/wifi = {"ssid": "MinhaRede", "rssi": -70, "ip": "192.168.0.42", "ms": 489}
  [recebido] sis1a/yuripaim/log/hora = {"hora": "2026-09-29 21:18:25", "relogio_ok": true}
  [recebido] sis1a/yuripaim/log/ciclos = 6
Encerrado.
```

---

## Respostas

1. **Explique pub/sub: o que é publicar, assinar e qual o papel do broker?**

No modelo publicar/assinar (pub/sub), quem tem um dado a informar **publica** uma mensagem em um
**tópico** (um "assunto"), sem saber quem vai recebê-la. Quem tem interesse naquele assunto
**assina** o tópico e passa a receber, automaticamente, toda mensagem publicada nele. O **broker**
(aqui, o Mosquitto) é o intermediário: recebe todas as publicações e as distribui para todo mundo
que assinou aquele tópico. Ninguém fala diretamente com ninguém — publicador e assinante nem
precisam existir ao mesmo tempo, só precisam estar conectados ao mesmo broker.

2. **Por que separar em vários tópicos é melhor do que mandar tudo num só? Cite uma vantagem.**

Separar permite que cada interessado assine **só o que precisa**, sem ter que baixar e filtrar um
JSON gigante toda vez. Por exemplo, um painel que só mostra a temperatura pode assinar apenas
`sis1a/yuripaim/temp`, em vez de assinar o tópico único e extrair o campo `temp` do JSON a cada
mensagem — mais simples, mais leve e mais fácil de estender (dá pra adicionar um sensor novo sem
quebrar quem já está assinando os outros).

3. **O que os logs de Wi-Fi e de TLS dizem sobre a saúde do dispositivo?**

O log de Wi-Fi (SSID, RSSI, IP, tempo de conexão) mostra se o dispositivo está numa posição boa em
relação ao roteador: um RSSI muito negativo ou um tempo de conexão crescente sugere sinal fraco ou
rede congestionada, o que pode causar desconexões no campo. O log de TLS (hora local e se o relógio
está sincronizado) mostra se o dispositivo consegue manter a hora certa via NTP — o que é pré-requisito
para validar certificados quando o dispositivo migrar para um broker com TLS.

4. **Por que o relógio (hora) importa para o TLS?**

A validação de um certificado TLS compara a data atual com o período de validade do certificado. Se
o relógio do ESP32 estiver errado, ele pode achar que um certificado válido está expirado (ou ainda
não válido), e a conexão seguro falha antes mesmo de trocar dados — por isso dispositivos IoT
sincronizam a hora por NTP assim que conectam.

5. **O que muda no código ao usar Deep Sleep (por que o trabalho vai para o `setup()`)? Para que serve o `RTC_DATA_ATTR`?**

Como o deep sleep faz o ESP32 **reiniciar** ao acordar, o `loop()` nunca chega a rodar de forma
contínua — tudo (conectar, publicar, esperar comando, dormir de novo) precisa acontecer dentro do
`setup()`, que é executado do zero a cada despertar. Isso também significa que variáveis comuns
perderiam seus valores a cada ciclo. O `RTC_DATA_ATTR` marca uma variável (no caso, `ciclos`) para
ficar guardada na memória RTC, que **sobrevive** ao deep sleep, permitindo contar quantos
despertares já aconteceram mesmo com o reinício completo do programa.

6. **Qual o trade-off do Deep Sleep com o recebimento de comandos em tempo real?**

Para receber um comando assim que ele é publicado, o dispositivo precisaria estar sempre conectado
e "ouvindo" o broker. Em deep sleep, ele só está acordado e escutando durante uma janela curta (na
nossa implementação, 5 segundos, dentro do `setup()`) antes de voltar a dormir por 30 segundos. Ou
seja, é uma troca entre **economizar energia** (dormindo a maior parte do tempo) e **responder na
hora** a um comando — um comando enviado fora da janela de escuta só será recebido no próximo
ciclo em que o dispositivo acordar.

7. **Descreva o caminho de um comando: do seu serviço até o LED acender.**

O serviço Python publica uma mensagem (ex.: `led:ON`) no tópico `sis1a/yuripaim/comando`. O broker
Mosquitto recebe essa publicação e a encaminha para todo assinante desse tópico — no caso, o ESP32,
que assinou `.../comando` assim que conectou. A função de callback `aoReceber()` no `.ino` identifica
o prefixo `led:`, atualiza o estado (`ledOn`), escreve fisicamente no pino do LED (`digitalWrite`) e
publica de volta o novo estado em `sis1a/yuripaim/led`, para que qualquer serviço assinante saiba
que o LED mudou.

---

**Entrega:** este `ENTREGA.md` + o código do ESP32 (`esp32/estacao_conexao.ino`) + o serviço usado
(`servico/servico.py`).
