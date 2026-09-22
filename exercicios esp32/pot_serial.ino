// Leitura de potenciômetro no ESP32 - exibe valores continuamente no Monitor Serial

#define POT_PIN 34   // entrada analógica (ADC1)

void setup() {
  Serial.begin(115200);
}

void loop() {
  int valor = analogRead(POT_PIN);
  Serial.print("Valor do sensor: ");
  Serial.println(valor);
  delay(300);
}
