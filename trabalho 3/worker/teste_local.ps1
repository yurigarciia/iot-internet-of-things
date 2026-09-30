Write-Host "=== POST /insert temp ==="
Invoke-RestMethod -Uri "http://127.0.0.1:8787/insert" -Method POST -Body (@{sensor="temp";valor=27.8}|ConvertTo-Json) -ContentType "application/json"

Write-Host "`n=== POST /insert umid ==="
Invoke-RestMethod -Uri "http://127.0.0.1:8787/insert" -Method POST -Body (@{sensor="umid";valor=61}|ConvertTo-Json) -ContentType "application/json"

Write-Host "`n=== GET /list?sensor=temp ==="
Invoke-RestMethod -Uri "http://127.0.0.1:8787/list?sensor=temp"

Write-Host "`n=== GET /list?sensor=umid ==="
Invoke-RestMethod -Uri "http://127.0.0.1:8787/list?sensor=umid"

Write-Host "`n=== GET /media?sensor=temp ==="
Invoke-RestMethod -Uri "http://127.0.0.1:8787/media?sensor=temp"

Write-Host "`n=== GET /resumo ==="
Invoke-RestMethod -Uri "http://127.0.0.1:8787/resumo"

Write-Host "`n=== POST /log ==="
Invoke-RestMethod -Uri "http://127.0.0.1:8787/log" -Method POST -Body (@{ip="192.168.0.42";rssi=-58;tempo_ms=812;internet=1}|ConvertTo-Json) -ContentType "application/json"

Write-Host "`n=== GET /logs ==="
Invoke-RestMethod -Uri "http://127.0.0.1:8787/logs"
