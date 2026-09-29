# PLANO — Leitor RFID de Controle de Acesso (Wokwi + MQTT)

Baseado em [ENUNCIADO.md](ENUNCIADO.md). Objetivo final: projeto Wokwi salvo,
funcionando de ponta a ponta, com `ENTREGA.md` (prints) pronto para a
apresentação para a Ana (professor).

Prefixo MQTT adotado: `sisla/yuri-garcia/rfid/` (confirmar grafia do nome
antes da entrega final).

---

## Etapa 0 — Preparação do projeto Wokwi

**Objetivo:** ambiente pronto para escrever código.

- [ ] Criar projeto novo ESP32 (Arduino) no wokwi.com
- [ ] Adicionar peças: ESP32 DevKit, MFRC522 RFID, LED + resistor 220 Ω
- [ ] Ligar os fios conforme tabela do enunciado (SDA→5, SCK→18, MOSI→23,
      MISO→19, RST→22, 3V3, GND; IRQ não ligar; LED ânodo→GPIO2,
      cátodo→resistor→GND)
- [ ] Instalar bibliotecas no Library Manager: `MFRC522` (Miguel Balboa) e
      `PubSubClient`
- [ ] Criar `diagram.json` e `libraries.txt` versionados no repo local,
      espelhando o projeto Wokwi
- [ ] Salvar o projeto e anotar o link

**Definição de pronto:** projeto abre no Wokwi, compila um sketch vazio
(`setup()`/`loop()` em branco) sem erro, e o link está salvo.

---

## Etapa 1 — Esqueleto de conectividade (Wi-Fi + NTP + MQTT)

**Objetivo:** ESP32 conecta ao Wi-Fi do simulador, sincroniza hora e conecta
no broker, publicando o `.../mac` retido. Cobre R2, R3 e metade do R7.

- [ ] `WiFi.begin("Wokwi-GUEST", "", 6);` com espera e log no Serial
- [ ] `configTime(-3*3600, 0, "pool.ntp.org")` + espera por `getLocalTime()`
      antes de seguir (não publicar hora zerada)
- [ ] Conectar ao `test.mosquitto.org:1883` com **client ID único**
      (nome + sufixo aleatório/millis) — evitar colisão com outros alunos
- [ ] `client.setBufferSize(512)` (ou maior) antes de conectar — necessário
      para a `.../lista` com 10 UIDs de 7 bytes não estourar o padrão de
      256 bytes
- [ ] Ao conectar (e reconectar), publicar em `.../mac` com **retain**:
      `{ "mac", "ip", "hora" }`
- [ ] Rotina de reconexão automática (Wi-Fi caiu / broker caiu) sem travar
      `loop()` com `delay()` longo
- [ ] Assinar `.../cmd`
- [ ] Serial mostrando: IP obtido, hora sincronizada, conexão/reconexão ao
      broker, tópico assinado

**Definição de pronto:** ao rodar a simulação, o `mosquitto_sub` mostra a
mensagem retida em `.../mac` com MAC, IP e hora corretos; ao reiniciar a
simulação, a mensagem retida aparece imediatamente antes mesmo de nova
publicação. Derrubar o Wi-Fi (ou trocar de aba) e o ESP32 reconecta sozinho.

---

## Etapa 2 — Leitura do cartão (R1)

**Objetivo:** UID lido e formatado corretamente, com debounce.

- [ ] Inicializar SPI + `MFRC522` no `setup()`
- [ ] No `loop()`, checar `PICC_IsNewCardPresent()` +
      `PICC_ReadCardSerial()`
- [ ] Formatar UID como hex maiúsculo separado por espaço, usando
      `mfrc522.uid.size` (não fixar em 4) — testar com NFC Tag (7 bytes)
- [ ] Debounce: ignorar o mesmo UID lido de novo em menos de 2 s
      (`millis()`, não `delay()`)
- [ ] Serial: imprimir cada UID lido, independente do modo atual

**Definição de pronto:** tap no Blue/Green/Yellow/Red/Key Fob imprime UID de
4 bytes correto; tap no NFC Tag imprime UID de 7 bytes correto; tap duplo
rápido no mesmo cartão gera só uma leitura no Serial.

---

## Etapa 3 — Modo cadastro (R4) — maior peso (2,5 pts)

**Objetivo:** máquina de estados de cadastro completa, com os 4 status.

- [ ] Estrutura de dados: array de até 10 UIDs (string), contador de
      quantidade
- [ ] Ao receber `CADASTRO` em `.../cmd`:
  - [ ] Se lista já tem 10 cartões → publicar `lista cheia` imediatamente,
        **não** entrar em modo cadastro
  - [ ] Senão, entrar em "modo cadastro", registrar `millis()` de início,
        LED piscando (sem `delay()`)
- [ ] Durante o modo cadastro, ao ler um cartão:
  - [ ] Se já está na lista → publicar `ja_cadastrada`, sair do modo
        cadastro
  - [ ] Se lista está cheia (checagem redundante de segurança) → `lista
        cheia`
  - [ ] Senão → adicionar à lista, publicar `cadastrada`, sair do modo
        cadastro
- [ ] Se passarem 15 s sem leitura → publicar `tempo esgotado`, sair do
      modo cadastro, LED para de piscar
- [ ] Toda mensagem de `.../cadastro` inclui `mac`, `uid` (quando houver) e
      `status`
- [ ] Serial: mostrar entrada/saída do modo cadastro e o motivo de saída

**Definição de pronto:** os 4 cenários reproduzem exatamente o texto de
status pedido (`cadastrada`, `ja_cadastrada`, `tempo esgotado`,
`lista cheia`), confirmados por `mosquitto_sub`, com LED piscando durante a
janela de 15 s e parando ao sair do modo.

---

## Etapa 4 — Remover e Listar (R5)

**Objetivo:** comandos administrativos completos.

- [ ] Parser de `.../cmd`: separar comando de argumento (`REMOVER <uid>`
      tem espaços no UID — pegar tudo após o primeiro espaço, `trim()`,
      normalizar para maiúsculas antes de comparar)
- [ ] `REMOVER <uid>`: se encontrado, remove da lista e publica `removida`;
      senão publica `nao_encontrada` — ambos em `.../cadastro` com `mac` e
      `uid`
- [ ] `LISTAR`: publica em `.../lista` um JSON com `mac` e array `tags`
      com todos os UIDs cadastrados (lista vazia → array `[]`, não travar)
- [ ] Serial: mostrar comando recebido e resultado

**Definição de pronto:** `REMOVER` de um UID existente e de um inexistente
retornam os status certos; `LISTAR` reflete exatamente o estado atual da
lista (inclusive depois de um `REMOVER`), verificado via `mosquitto_sub`.

---

## Etapa 5 — Acesso do dia a dia (R6)

**Objetivo:** fluxo normal de leitura fora do modo cadastro.

- [ ] Fora do modo cadastro, cada leitura de cartão (respeitando debounce
      de 2 s) verifica se o UID está na lista
- [ ] Cadastrado → publicar `.../acesso` com `resultado: "liberado"` e
      `hora`; LED aceso por 2 s (sem `delay()`)
- [ ] Desconhecido → publicar `.../acesso` com `resultado: "negado"` e
      `hora`; LED pisca 3 vezes rápido (sem `delay()`)
- [ ] Garantir que o modo cadastro sempre tem prioridade sobre o modo
      acesso (não confundir os dois fluxos de leitura)
- [ ] Serial: mostrar resultado de cada leitura em modo normal

**Definição de pronto:** cartão cadastrado libera com LED aceso 2 s; cartão
não cadastrado nega com LED piscando 3x; ambos publicam em `.../acesso` com
hora correta, sem interferir no modo cadastro.

---

## Etapa 6 — Revisão de organização e robustez (R7 + critério "Organização")

**Objetivo:** o "1,0 organização" e o R7 completos.

- [ ] Revisar todo o `loop()`: nenhum `delay()` bloqueante que impeça
      `client.loop()` ou a leitura de novos comandos
- [ ] Reconexão automática testada: Wi-Fi cai e volta, broker cai e volta
- [ ] Código organizado em funções (ex.: `conectarWifi()`,
      `conectarMQTT()`, `publicarMac()`, `entrarModoCadastro()`,
      `processarComando()`, `formatarUid()`, `atualizarLed()`) com nomes
      claros e comentários pontuais
- [ ] Serial cobre: MAC, cada conexão/reconexão, modo atual, cada UID lido,
      cada comando recebido — revisar se algo ficou faltando
- [ ] Passar uma revisão de código (`/code-review` ou leitura manual) antes
      de fechar

**Definição de pronto:** releitura do sketch por alguém que não escreveu
consegue seguir o fluxo; Serial Monitor conta a história completa de uma
sessão de testes sem precisar olhar o código.

---

## Etapa 7 — Testes de ponta a ponta via terminal/MQTT Explorer

**Objetivo:** validar os 7 requisitos juntos, simulando a Ana.

Roteiro de teste (mesmo do enunciado):

- [ ] `mosquitto_sub -h test.mosquitto.org -t "sisla/SEU-NOME/rfid/#" -v`
      rodando durante todo o teste
- [ ] Reiniciar simulação → conferir `.../mac` retido
- [ ] `mosquitto_pub ... -t .../cmd -m "CADASTRO"` → tap Green → conferir
      `cadastrada`
- [ ] `CADASTRO` de novo → tap Green de novo → conferir `ja_cadastrada`
- [ ] `CADASTRO` → não passar nada por 15 s → conferir `tempo esgotado`
- [ ] Cadastrar 10 cartões distintos (usar os 6 disponíveis + repetir
      taps de "cartões" diferentes se o simulador permitir múltiplas
      instâncias, ou simular o limite via lista interna) → no 11º
      `CADASTRO`, conferir `lista cheia`
- [ ] Tap Green (cadastrado) em modo normal → `liberado`, LED 2 s
- [ ] Tap Red (não cadastrado) em modo normal → `negado`, LED pisca 3x
- [ ] `REMOVER <uid do Green>` → conferir `removida`
- [ ] `REMOVER <uid inexistente>` → conferir `nao_encontrada`
- [ ] `LISTAR` → conferir array de UIDs bate com o estado esperado

**Definição de pronto:** todos os itens acima reproduzidos e capturados em
print, sem precisar reiniciar a simulação no meio (exceto o teste do
`.../mac` retido, que exige reinício).

---

## Etapa 8 — Entrega e apresentação

**Objetivo:** `ENTREGA.md` completo e ensaio da apresentação.

- [ ] Criar `ENTREGA.md` com:
  - [ ] Link do projeto Wokwi salvo
  - [ ] Print: mensagem retida em `.../mac`
  - [ ] Print: cadastro (`cadastrada`)
  - [ ] Print: cadastro repetido (`ja_cadastrada`)
  - [ ] Print: tempo esgotado
  - [ ] Print: acesso liberado
  - [ ] Print: acesso negado
  - [ ] Print: `REMOVER`
  - [ ] Print: `LISTAR`
- [ ] Ensaiar o roteiro de apresentação exato do enunciado:
      `CADASTRO` → tap Green → aparece em `.../cadastro` → Green liberado,
      Red negado com hora → `REMOVER` do Green → `LISTAR` confere remoção
- [ ] Conferir se o projeto Wokwi está salvo e a aba não vai ser fechada
      antes da apresentação

**Definição de pronto:** `ENTREGA.md` commitado com todos os prints e link;
roteiro de apresentação rodado do início ao fim sem falhas, dentro do
próprio Wokwi.

---

## Marcos (checkpoints para avaliar progresso)

| Marco | O que precisa estar pronto | Cobre |
|---|---|---|
| M1 | Etapas 0–1 | Projeto monta, conecta Wi-Fi/NTP/MQTT, publica `.../mac` retido |
| M2 | Etapa 2 | Leitura de UID (4 e 7 bytes) com debounce |
| M3 | Etapa 3 | Modo cadastro com os 4 status — maior peso da nota |
| M4 | Etapas 4–5 | REMOVER/LISTAR e fluxo de acesso liberado/negado |
| M5 | Etapa 6 | Código revisado, sem bloqueios, Serial completo |
| M6 | Etapas 7–8 | Testes ponta a ponta gravados, `ENTREGA.md` pronto, ensaio da apresentação feito |

## Riscos / pontos de atenção já identificados

- Buffer padrão do `PubSubClient` (256 bytes) estoura na `.../lista` com
  10 UIDs de 7 bytes — resolvido na Etapa 1 com `setBufferSize`.
- `delay()` bloqueante mata `client.loop()` — todas as animações de LED e
  o timeout de 15 s usam `millis()`.
- Client ID de MQTT repetido entre alunos (MAC igual no simulador) pode
  causar desconexões cruzadas — client ID inclui nome + valor aleatório.
- Nomenclatura dos status mistura espaço (`tempo esgotado`, `lista cheia`)
  e underscore (`ja_cadastrada`, `nao_encontrada`) — manter exatamente como
  no enunciado.
- Confirmar grafia do nome do aluno no prefixo do tópico antes da entrega
  final (enunciado grafa "Gracia", possivelmente "Garcia").
