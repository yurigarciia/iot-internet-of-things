# ANTONIO MENEGHETTI FACULDADE

## SISTEMAS DE INFORMAÇÃO

**Nome:** Yuri Gracia\
**Disciplina:** IoT (Internet of Things)\
**Professor:** Prof. Leonam V. Hemann

------------------------------------------------------------------------

# O PEDIDO

A Ana coordena o laboratório de informática e quer saber **quem entra e
quando**. Ela comprou leitores RFID para instalar nas portas e
distribuiu cartões para os alunos. O problema: o prédio vai ter **vários
leitores**, e a central precisa saber de **qual leitor veio cada
mensagem**.

Ela explicou o que precisa assim:

-   "Quando eu ligar um leitor, quero que ele se apresente na rede com o
    MAC dele, para eu saber que ele está lá."
-   "Quero cadastrar um **cartão novo pelo computador**: eu mando um
    comando, o aluno passa o cartão e pronto, sem mexer no código."
-   "No dia a dia, cada vez que alguém passar o cartão, quero receber na
    hora se foi **liberado ou negado**, e a que horas."
-   "Também preciso remover um cartão perdido e ver a lista de quem está
    cadastrado."

A Ana não entende de programação. Você vai construir o leitor e, no
final, **apresentar tudo funcionando** para ela (o professor faz o papel
da Ana).

## AMBIENTE: SIMULADOR WOKWI (SEM MONTAGEM FÍSICA)

Toda a prova é feita no **wokwi.com**, que simula o ESP32 com Wi-Fi e
internet de verdade.

-   Crie um projeto **ESP32 (Arduino)**, adicione as peças pelo botão
    "+" e ligue os fios clicando nos pinos.
-   Instale as bibliotecas na aba **Library Manager**: **MFRC522**
    (Miguel Balboa) e **PubSubClient**.
-   Wi-Fi do simulador: `WiFi.begin("Wokwi-GUEST", "", 6);` (sem senha).
-   Salve o projeto com frequência e não feche a aba durante a prova.
-   A rede do simulador é pública: não envie dados sensíveis. Broker:
    **test.mosquitto.org**, porta **1883**.

## LIGAÇÕES NO WOKWI

Peças: **ESP32 DevKit, MFRC522 RFID Reader e LED com resistor de 220 Ω
(ânodo no GPIO 2, cátodo pelo resistor até o GND).**

------------------------------------------------------------------------

## LIGAÇÕES

  MFRC522   ESP32
  --------- -----------
  SDA       GPIO 5
  SCK       GPIO 18
  MOSI      GPIO 23
  MISO      GPIO 19
  RST       GPIO 22
  3.3V      3V3
  GND       GND
  IRQ       não ligar

Para "passar" um cartão: clique no leitor durante a simulação, escolha o
cartão (Blue, Green, Yellow, Red, NFC Tag ou Key Fob) e clique em
**Tap**. Cada cartão tem um **UID** diferente. O NFC Tag tem **7 bytes**
em vez de 4.

# TÓPICOS MQTT

Todos os tópicos começam com o prefixo `sisla/SEU-NOME/rfid/` (troque
**SEU-NOME** pelo seu nome).

  ---------------------------------------------------------------------------------------------------------------------------------------
  Tópico                  Quem publica            Conteúdo (exemplo)
  ----------------------- ----------------------- ---------------------------------------------------------------------------------------
  `.../mac`               ESP32, com retain, ao   `{ "mac": "24:0A:C4:00:01:10", "ip": "10.10.0.2", "hora": "15:40:02" }`
                          conectar                

  `.../cadastro`          ESP32, quando cadastra  `{ "mac": "...", "uid": "A3 4F 12 9C", "status": "cadastrada" }`
                          ou remove               

  `.../acesso`            ESP32, a cada cartão no `{ "mac": "...", "uid": "A3 4F 12 9C", "resultado": "liberado", "hora": "15:42:10" }`
                          modo normal             

  `.../lista`             ESP32, ao receber       `{ "mac": "...", "tags": ["A3 4F 12 9C", "..."] }`
                          LISTAR                  

  `.../cmd`               a central (Ana)         comandos: `CADASTRO`, `REMOVER <uid>`, `LISTAR`
  ---------------------------------------------------------------------------------------------------------------------------------------

No Wokwi, o MAC pode sair igual para todos os alunos. Por isso, o seu
nome no tópico é o que separa os leitores.

# O QUE CONSTRUIR

**R1 --- Leitura do cartão.** Ler o UID e formatá-lo em hexadecimal
separado por espaços (ex.: `A3 4F 12 9C`), funcionando com UIDs de 4 e
de 7 bytes (`mfrc522.uid.size`). Ignorar o mesmo cartão lido de novo em
menos de 2 s.

**R2 --- O leitor se apresenta (MAC).** Ao conectar ao broker, publicar
em `.../mac`, com retain, o MAC (`WiFi.macAddress()`), o IP e a hora.
Todas as mensagens de cadastro e acesso levam o campo `mac`.

------------------------------------------------------------------------

**R3 --- Hora certa.** Sincronizar a hora por NTP no `setup()`
(`configTime(-3 * 3600, 0, "pool.ntp.org")`) e usar a hora local nas
mensagens.

**R4 --- Cadastro pelo computador.** Ao receber `CADASTRO` em `.../cmd`,
o leitor entra em modo cadastro por **15 s**, com o LED piscando. O
próximo cartão lido é cadastrado e publicado em `.../cadastro` com o
status:

-   `cadastrada`: cartão novo, adicionado à lista (máximo de 10
    cartões);
-   `ja_cadastrada`: o cartão já estava na lista;
-   `tempo esgotado`: passaram 15 s sem nenhum cartão;
-   `lista cheia`: já existem 10 cartões.

**R5 --- Remover e listar.** `REMOVER A3 4F 12 9C` tira o cartão da
lista e publica em `.../cadastro` o status `removida` (ou
`nao_encontrada`), `LISTAR` publica em `.../lista` todos os UIDs
cadastrados.

**R6 --- Uso do dia a dia (acesso).** Fora do modo cadastro, cada cartão
publica em `.../acesso`:

-   cartão cadastrado --- **liberado**, LED aceso por 2 s;
-   cartão desconhecido --- **negado**, LED pisca 3 vezes rápido.

**R7 --- Serial Monitor.** Mostrar o MAC, as conexões, o modo atual,
cada UID lido e cada comando recebido.

Para testar (MQTT Explorer ou terminal):

``` bash
mosquitto_sub -h test.mosquitto.org -t "sisla/SEU-NOME/rfid/#" -v
mosquitto_pub -h test.mosquitto.org -t "sisla/SEU-NOME/rfid/cmd" -m "CADASTRO"
```

# ENTREGA E APRESENTAÇÃO

-   Link do projeto no Wokwi (salvo).
-   `ENTREGA.md` com prints de: a mensagem retida em `.../mac`, um
    cadastro, um cadastro repetido, um tempo esgotado, um acesso
    liberado e um negado, um **REMOVER** e o **LISTAR**.
-   **Apresentação para a Ana (professor):** ela manda `CADASTRO` → você
    passa o cartão Green → ele aparece em `.../cadastro` → o Green é
    liberado e o Red é negado, com a hora → ela remove o Green e confere
    com `LISTAR`.

# CRITÉRIOS DE AVALIAÇÃO

  -----------------------------------------------------------------------
  Critério                                                         Pontos
  ------------------------------ ----------------------------------------
  R1 --- Leitor ligado e UID                                          1,5
  lido e formatado (4 e 7 bytes) 

  R2 --- MAC publicado com                                            1,0
  retain ao conectar e presente  
  nas mensagens                  

  R3 --- Hora por NTP nas                                             1,0
  mensagens                      

  R4 --- Modo cadastro por                                            2,5
  comando, com os quatro status  

  R5 --- REMOVER e LISTAR                                             1,5
  funcionando                    

  R6 --- Acesso liberado/negado                                       1,5
  publicado e LED correspondente 

  Organização: reconexão                                              1,0
  automática, código legível,    
  Serial claro (R7)              

  **Total**                                                      **10,0**
  -----------------------------------------------------------------------
