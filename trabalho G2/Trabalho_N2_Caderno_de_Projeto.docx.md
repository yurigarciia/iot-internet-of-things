Faculdade Antonio Meneghetti · Sistemas de Informação  
IoT (Internet das Coisas) · G0813 · Prof. Leonam V.  Hemann · Turma AMF 2026-02

**TRABALHO N2 — CADERNO DE PROJETO**

**Da ideia ao sistema: decidir, montar e justificar**

| Integrantes (pode ser em dupla) *papéis: montagem · código · nuvem e painel · caderno e testes* |  |
| :---- | :---- |
| **Desafio escolhido** |  |
| **Link do repositório no GitHub** |  |

# **COMO USAR ESTE CADERNO**

Este caderno é ao mesmo tempo o **roteiro** do projeto e a **entrega**. Ele leva o grupo, etapa por etapa, pelas decisões que todo sistema IoT precisa tomar. Em cada etapa vocês encontram:

* **Entenda:** um resumo do que já vimos em aula, para ajudar a decidir.

* **Decidam:** os campos que o grupo preenche. Toda escolha vem com o **porquê**.

# **COMO VAI SER AVALIADO**

| Critério | Etapas | Pontos |
| :---- | :---- | :---- |
| Ideia, problema e requisitos medíveis | 0 e 1 | 1,5 |
| Sentir, decidir e agir funcionando, com estado seguro | 2 e 3 | 2,0 |
| Comunicação: MQTT com TLS e padrão de tópicos | 4 | 1,5 |
| Histórico com consulta de resumo | 5 | 1,0 |
| Painel com comando confirmado e alerta com *cooldown* | 6 | 1,5 |
| Segurança aplicada e testada | 7 | 1,0 |
| Extra com evidência | 8 | 0,5 |
| Arquitetura, testes e apresentação | 11 | 1,0 |
| **Total** |  | **10,0** |

# **ETAPA 0 — ESCOLHAM O DESAFIO**

Escolham **um** caminho: um dos desafios prontos (opção A) ou uma ideia própria (opção B). Vale montar na placa ou no **Wokwi**.

## **Opção A — Desafios prontos**

| Desafio | O problema | Kit sugerido | A decisão mais difícil |
| :---- | :---- | :---- | :---- |
| **Geladeira de vacinas** | O posto guarda vacinas a 2–8 °C e precisa provar, pelo histórico, que elas nunca saíram da faixa. | DHT · distância (porta) · buzzer | O que fazer com as leituras se a internet cair? |
| **Silo de grãos** | Grão úmido estraga. O ventilador liga quando precisa, e não há tomada no silo. | DHT · LED ou relé (ventilador) | Quanto tempo o ESP32 pode ficar acordado para a bateria durar? |
| **Armário de empréstimo** | Laboratório: registrar quem pegou cada equipamento e quando devolveu. | botões (senha) ou RFID · servo (trava) · distância | Como impedir que alguém abra o armário com um comando falso? |
| **Poste inteligente da praça** | Luz forte só com gente perto. A prefeitura vê e comanda todos os postes de um painel. | LDR · distância ou PIR · LEDs (PWM) | Como organizar os tópicos para 100 postes? |

## 

## **Opção B — Criem a ideia de vocês**

Escolham (ou sorteiem) um item de cada coluna e transformem em um produto. A restrição é o que deixa a ideia interessante: ela obriga a tomar decisões de rede, energia ou segurança.

| Lugar | Sensor | Atuador | Restrição |
| :---- | :---- | :---- | :---- |
| escola · fazenda · hospital · fábrica · rua · supermercado · academia · casa de idoso · estacionamento · biblioteca | LDR · DHT11 · LM35 · PIR · ultrassônico · RFID · umidade do solo · potenciômetro · botão | LED · LED RGB · buzzer · servo · relé · motor DC | sem Wi-Fi · bateria de 1 ano · dado sensível (LGPD) · 1.000 unidades · usuário sem celular · até R\$ 60 · tem que funcionar sem internet · decidir em menos de 1 s |

**Frase da ideia:** *"Para \[quem\], que sofre com \[problema\], o \[nome do produto\] sente \[sensor\], decide \[regra\] e age com \[atuador\], mesmo com \[restrição\]."*

## **Decidam**

| Desafio (A) ou ideia própria (B) |  |
| :---- | :---- |
| **Por que esse problema importa? Quem ganha com a solução? \- Frase da ideia** |  |

# **ETAPA 1 — PROBLEMA E REQUISITOS**

## **Entenda**

* **Requisito funcional** diz **o que** o sistema faz. Modelo: *"O dispositivo deve \[ação\] quando \[condição\], em até \[tempo ou limite\]."*

* **Requisito não funcional** diz **como e quanto**: energia, custo, rede disponível, ambiente (frio, umidade), tempo de resposta.

* Um bom requisito é **medível**: "alarme se T \> 8 °C por mais de 5 min", e não "alarme se esquentar".

## **Decidam**

| Código | Requisito (o dispositivo deve...) | Como vamos comprovar |
| :---- | :---- | :---- |
| **RF1** |  |  |
| **RF2** |  |  |
| **RF3** |  |  |
| **RF4** |  |  |

| Código | Requisito não funcional (como e quanto) | Por que é importante neste problema |
| :---- | :---- | :---- |
| **RNF1** |  |  |
| **RNF2** |  |  |
| **RNF3** |  |  |

# **ETAPA 2 — SENTIR E AGIR: COMPONENTES**

## **Entenda**

* No kit o atuador é pequeno, mas **representa** algo real: o LED pode ser uma lâmpada (relé), o servo uma válvula ou trava, o buzzer uma sirene. Digam o que ele representa.

* Todo sensor falha um dia (DHT devolve NaN, fio solta). Decidam o **estado seguro**: o que o atuador faz quando a leitura é inválida.

## **Decidam**

| Componente | Mede ou aciona o quê | GPIO | Faixa ou limite | Se falhar, o sistema... |
| :---- | :---- | :---- | :---- | :---- |
|  |  |  |  |  |
|  |  |  |  |  |
|  |  |  |  |  |

# **ETAPA 3 — ONDE DECIDIR: ESP32 OU NUVEM?**

## **Entenda**

| Pergunta | Se a resposta for sim, a decisão tende a ir para... |
| :---- | :---- |
| Precisa reagir em menos de 1 segundo? | ESP32 (borda): não depende da rede |
| Tem que funcionar se a internet cair? | ESP32 (borda) |
| A regra muda com frequência ou é ajustada por alguém de fora? | Nuvem (Worker), ou limite guardado no KV e lido pelo ESP32 |
| Precisa cruzar dados de vários dispositivos? | Nuvem |
| O dado é sensível e não deveria sair do local? | ESP32 (borda): envie só o resultado |

**Histerese:** use dois limites (liga em 8 °C, desliga em 7 °C) para o atuador não ficar ligando e desligando quando o valor oscila perto do limite.

## **Decidam**

| Regra de decisão em pseudocódigo (com histerese ou tempo mínimo) *ex.: se T \> 8 por 5 min → alarme \= ligado; se T \< 7 → alarme \= desligado* |  |
| :---- | :---- |
| **Onde a regra roda e por quê** |  |
| **O que acontece se a internet cair? E quando ela voltar?** |  |

# **ETAPA 4 — COMUNICAR: PROTOCOLO, TÓPICOS E MENSAGEM**

## **Entenda**

| Protocolo | Bom para | Cuidado |
| :---- | :---- | :---- |
| MQTT | Muitos dispositivos, publicar e assinar, comandos em tempo real | Broker público: quem souber o tópico lê e publica |
| HTTP (Worker) | Gravar no KV/D1 e consultar o histórico | ESP32 pergunta; a nuvem não consegue "chamar" o ESP32 |
| WebSocket | Painel no navegador atualizando sozinho | A conexão precisa ficar aberta |

**Padrão de tópicos:** sis1a/\<grupo\>/\<local\>/telemetria, …/estado, …/comando, …/alerta. Minúsculas, sem acento, unidade no nome do campo (temp\_c, dist\_cm).

## **Decidam**

| Protocolo(s) escolhido(s) e por quê |  |
| :---- | :---- |
| **Árvore de tópicos (todos)** *um por linha, dizendo quem publica e quem assina* |  |
| **JSON de exemplo da telemetria** |  |
| **TLS: qual porta e como o ESP32 confere o servidor?** *lembrem: setInsecure() não confere* |  |

# **ETAPA 5 — GUARDAR: O HISTÓRICO**

## **Entenda**

|  | KV (chave-valor) | D1 (banco relacional) |
| :---- | :---- | :---- |
| **Guarda** | Um valor por chave: último estado, configuração, limite | Linhas e colunas: cada leitura é um registro |
| **Consulta** | Pela chave exata | SQL: filtros, médias, GROUP BY por hora |
| **Use quando** | Precisa só do valor mais recente ou de um ajuste remoto | Precisa responder perguntas sobre o passado |

* Pensem também em **por quanto tempo** guardar. Se o dado é pessoal (quem entrou, quem pegou o equipamento), a LGPD pede que se guarde só o necessário, pelo tempo necessário.

## **Decidam**

| KV, D1 ou os dois? Por quê? |  |
| :---- | :---- |
| **Estrutura: tabela(s) e colunas, ou chaves** |  |
| **De quanto em quanto tempo grava?** |  |
| **Consulta de resumo (SQL) e a pergunta que ela responde** *ex.: temperatura máxima por hora nas últimas 24 h* |  |
| **Por quanto tempo guardar? Há dado pessoal?** |  |

# **ETAPA 6 — MOSTRAR E COMANDAR: O PAINEL**

## **Entenda**

* **Comando enviado não é comando executado.** O painel só mostra "executado" quando o ESP32 devolve uma confirmação (ack). Se o ESP32 estiver dormindo ou offline, o painel tem que deixar isso claro.

* Um alerta que chega 30 vezes por minuto é ignorado. Usem um **cooldown**: o mesmo alerta não se repete antes de um tempo mínimo.

## **Decidam**

| O que o painel mostra (estado, gráfico, resumo) |  |
| :---- | :---- |
| **Comando remoto: qual, por qual tópico ou rota** |  |
| **Como o painel sabe que o comando foi executado? Quanto tempo espera?** |  |
| **Alerta: quando dispara, por onde chega e qual o cooldown** |  |
| **Polling ou WebSocket? Por quê?** |  |

# **ETAPA 7 — PROTEGER: SEGURANÇA**

## **Entenda**

Os cinco buracos que vimos na Estação Cofre. Para cada um, digam se ele existe no sistema de vocês e como foi fechado.

| Buraco | Existe no nosso sistema? | Como fechamos (camada) |
| :---- | :---- | :---- |
| **1\. MQTT sem TLS (porta 1883\)** |  |  |
| **2\. setInsecure() no HTTPS** |  |  |
| **3\. Rota de gravação aceita qualquer um** |  |  |
| **4\. Tópico de comando aberto** |  |  |
| **5\. Segredo no GitHub ou no Serial** |  |  |

# **ETAPA 8 — EXTRA: ESCOLHAM UM**

| Extra | O que fazer | Evidência no caderno |
| :---- | :---- | :---- |
| **Energia e autonomia** | Deep sleep e cálculo de quanto a bateria dura | Corrente média \= Σ (corrente × tempo) ÷ período; autonomia \= capacidade útil ÷ corrente média |
| **Tempo real** | Painel atualizado por WebSocket, sem recarregar | Print ou vídeo curto do painel mudando sozinho |

## **Decidam**

| Extra escolhido e por que combina com o problema |  |
| :---- | :---- |
| **Evidência (cálculo, print ou comparação)** |  |

# **ETAPA 9 — ARQUITETURA FINAL**

Descrevam o sistema em quatro camadas. Se quiserem, colem também um desenho ou print do esquemático (Wokwi, Fritzing ou foto da montagem).

| Camada | O que tem nela no nosso sistema |
| :---- | :---- |
| **Dispositivo** |  |
| **Rede** |  |
| **Nuvem** |  |
| **Interface** |  |

| Desenho ou print do sistema *cole aqui a imagem* |  |
| :---- | :---- |

# **ETAPA 10 — TESTES ANTES DE APRESENTAR**

| Teste | Como fizemos | Resultado |
| :---- | :---- | :---- |
| **Isolado: cada peça sozinha** |  |  |
| **No limite: forçar o sensor** |  |  |
| **Na falha: tirar o sensor ou o Wi-Fi** |  |  |
| **No reinício: tirar e ligar o USB** |  |  |
| **No ataque: comando falso** |  |  |
| **Na duração: 10 min ligado** |  |  |

# **ETAPA 11 — APRESENTAÇÃO E ENTREGA**

## **Roteiro da apresentação (4 minutos)**

1. Problema e quem usa (a frase da ideia).

2. Arquitetura: do sensor ao painel.

3. Escolhas: onde decide, qual protocolo, KV ou D1, que segurança. Por quê.

4. Demonstração ao vivo, funcionando.

5. O que falta para virar produto (1.000 unidades, bateria, custo).

**A turma pode perguntar:** *"e se a internet cair?" · "e se alguém publicar no seu tópico?" · "e com 1.000 unidades?"*

## **Checklist de entrega (até 24/11)**

|  | Item |
| :---- | :---- |
| ☐ | Este caderno preenchido (.docx ou PDF) na pasta docs/ do repositório e no Classroom |
| ☐ | Código do ESP32 e do Worker no GitHub, sem senhas nem chaves |
| ☐ | README curto: o que o sistema faz, como montar e como testar |
| ☐ | Print ou vídeo curto do sistema funcionando (para o caso de falhar na hora) |

