"""Calculo de autonomia do no do silo (Etapa 8). Rode: python docs/autonomia.py

Corrente media = soma(corrente x tempo) / periodo      autonomia = capacidade util / corrente media
Valores de corrente sao TIPICOS de datasheet/medicoes publicadas do ESP32 (nao medidos aqui): confirme com
um multimetro em serie ou um Power Profiler antes de prometer "1 ano" para o cliente.
"""
FASES = [                      # (nome, segundos, mA)
    ("boot + leitura do DHT22", 2.5, 45),     # CPU ativa, radio desligado (+ 3 tentativas so se falhar)
    ("Wi-Fi + NTP",             3.0, 130),    # associar, DHCP, hora
    ("TLS + MQTT + comando",    3.0, 140),    # handshake TLS (cripto), subscribe, 1,5 s de janela, publish
]
SONO_MA = 0.06                 # ESP32 10 uA + DHT22 em standby ~50 uA (modulo nu, sem chip USB-serial)
CAPACIDADE_MAH = 2 * 3000      # 2 celulas 18650 em paralelo
USO = 0.80                     # so 80% e aproveitavel (corte de tensao, envelhecimento, frio)

ativo_s = sum(s for _, s, _ in FASES)
carga_ativa = sum(s * ma for _, s, ma in FASES) / 3600        # mAh por despertar

print(f"Tempo acordado por ciclo: {ativo_s:.1f} s | carga por despertar: {carga_ativa:.4f} mAh")
print(f"Bateria: {CAPACIDADE_MAH} mAh x {USO:.0%} = {CAPACIDADE_MAH*USO:.0f} mAh uteis\n")
print(f"{'cenario':<34}{'periodo':>9}{'I media':>11}{'autonomia':>14}")

def linha(nome, periodo_s, i_media):
    horas = CAPACIDADE_MAH * USO / i_media
    print(f"{nome:<34}{periodo_s:>8}s{i_media:>9.3f}mA{horas/24:>11.0f} dias")

linha("sem deep sleep (Wi-Fi sempre on)", "-", 80.0)        # media tipica de ESP32 com Wi-Fi conectado
for p in (30, 900, 1800, 3600):
    sono = (p - ativo_s) * SONO_MA / 3600
    linha("deep sleep" + (" (demo)" if p == 30 else ""), p, (carga_ativa + sono) * 3600 / p)

# decisao de projeto: comando RETIDO (janela de 1,5 s) em vez de ficar 5 s acordado esperando (Trab. 4)
extra = (5 - 1.5) * 100 / 3600                               # 3,5 s a mais, radio ligado ~100 mA
p = 1800
i_ret = (carga_ativa + (p - ativo_s) * SONO_MA / 3600) * 3600 / p
i_jan = (carga_ativa + extra + (p - ativo_s - 3.5) * SONO_MA / 3600) * 3600 / p
print(f"\nPeriodo de 30 min: janela de 5 s esperando comando gasta {i_jan:.3f} mA "
      f"({(i_jan/i_ret-1):.0%} a mais que a janela de 1,5 s com mensagem retida).")
