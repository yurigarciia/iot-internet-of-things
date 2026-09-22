// Leitura de potenciômetro no ESP32 - formato compatível com Edge Impulse Data Forwarder

#define POT_PIN 34   // entrada analógica (ADC1)

void setup() {
  Serial.begin(115200);
}

void loop() {
  int valor = analogRead(POT_PIN);
  Serial.println(valor);
  delay(300);
}
