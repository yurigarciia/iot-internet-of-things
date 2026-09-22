// Fade LED no ESP32 - aumenta brilho, mantém 5s, diminui brilho, mantém 5s (loop)
#define LED_PIN 25       
#define PWM_CHANNEL 0
#define PWM_FREQ 5000 
#define PWM_RESOLUTION 8

void setup() {
  ledcSetup(PWM_CHANNEL, PWM_FREQ, PWM_RESOLUTION);
  ledcAttachPin(LED_PIN, PWM_CHANNEL);
}

void loop() {
  for (int duty = 0; duty <= 255; duty++) {
    ledcWrite(PWM_CHANNEL, duty);
    delay(15);
  }

  delay(5000);

  for (int duty = 255; duty >= 0; duty--) {
    ledcWrite(PWM_CHANNEL, duty);
    delay(15);
  }

  delay(5000);
}
