-- D1: historico. Uma linha por leitura (temperatura e umidade juntas),
-- porque o resumo por hora cruza as duas grandezas.
CREATE TABLE IF NOT EXISTS leituras (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  silo        TEXT    NOT NULL,            -- "silo01"
  ts          INTEGER NOT NULL,            -- quando foi medido (ms desde 1970)
  temp_c      REAL,                        -- NULL quando o sensor falhou
  umid_pct    REAL,                        -- NULL quando o sensor falhou
  ventilador  INTEGER NOT NULL,            -- 1 = ligado, 0 = desligado
  sensor_ok   INTEGER NOT NULL,            -- 1 = leitura valida
  bat_v       REAL,                        -- tensao da bateria (V)
  rssi        INTEGER,                     -- forca do Wi-Fi (dBm)
  atrasada    INTEGER NOT NULL DEFAULT 0,  -- 1 = ficou guardada no ESP32 enquanto estava sem rede
  recebido_ts INTEGER NOT NULL             -- quando o Worker recebeu (ms)
);
-- impede gravar a mesma leitura duas vezes (reenvio do broker / reinicio do servico)
CREATE UNIQUE INDEX IF NOT EXISTS ux_leituras_silo_ts ON leituras (silo, ts);

-- Eventos: mudancas de ventilador, comandos confirmados, alertas disparados.
CREATE TABLE IF NOT EXISTS eventos (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  silo    TEXT    NOT NULL,
  ts      INTEGER NOT NULL,
  tipo    TEXT    NOT NULL,                -- ventilador | comando | alerta
  detalhe TEXT
);
CREATE INDEX IF NOT EXISTS ix_eventos_silo_ts ON eventos (silo, ts);
