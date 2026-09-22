#define BUTTON_PIN 4   
#define LED_PIN 2      

bool ledState = false;      
int lastButtonState = LOW;  

void setup() {
  pinMode(BUTTON_PIN, INPUT_PULLDOWN);
  pinMode(LED_PIN, OUTPUT);
}

void loop() {
  int reading = digitalRead(BUTTON_PIN);

  if (reading == HIGH && lastButtonState == LOW) {
    ledState = !ledState;            
    digitalWrite(LED_PIN, ledState);
  }

  lastButtonState = reading;
}
