CREATE TABLE IF NOT EXISTS leituras (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,  -- numero unico de cada linha
  sensor    TEXT    NOT NULL,                   -- "temp" ou "umid"
  valor     REAL    NOT NULL,                   -- o numero medido
  timestamp INTEGER NOT NULL                    -- quando foi medido (ms)
);

CREATE TABLE IF NOT EXISTS conexoes (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ip        TEXT,               -- IP que o ESP32 recebeu na rede
  rssi      INTEGER,            -- forca do sinal Wi-Fi (dBm)
  tempo_ms  INTEGER,            -- tempo que levou para conectar (ms)
  internet  INTEGER,            -- 1 = internet respondeu, 0 = nao
  timestamp INTEGER NOT NULL
);
