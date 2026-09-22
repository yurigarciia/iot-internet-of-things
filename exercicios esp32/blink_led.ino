// Blink LED no ESP32 - liga por 500ms e apaga em loop
#define LED_PIN 2

void setup() {
  pinMode(LED_PIN, OUTPUT);
}

void loop() {
  digitalWrite(LED_PIN, HIGH); 
  delay(500);                  

  digitalWrite(LED_PIN, LOW); 
  delay(500);                  
}
