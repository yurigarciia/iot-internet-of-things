#!/bin/bash
BASE="http://127.0.0.1:8788"

echo "=== POST /insert temp ==="
curl -s -X POST "$BASE/insert" -H "Content-Type: application/json" -d '{"sensor":"temp","valor":27.8}'
echo

echo -e "\n=== POST /insert umid ==="
curl -s -X POST "$BASE/insert" -H "Content-Type: application/json" -d '{"sensor":"umid","valor":61}'
echo

echo -e "\n=== GET /list?sensor=temp ==="
curl -s "$BASE/list?sensor=temp"
echo

echo -e "\n=== GET /list?sensor=umid ==="
curl -s "$BASE/list?sensor=umid"
echo

echo -e "\n=== GET /media?sensor=temp ==="
curl -s "$BASE/media?sensor=temp"
echo

echo -e "\n=== GET /resumo ==="
curl -s "$BASE/resumo"
echo

echo -e "\n=== POST /log ==="
curl -s -X POST "$BASE/log" -H "Content-Type: application/json" -d '{"ip":"192.168.0.42","rssi":-58,"tempo_ms":812,"internet":1}'
echo

echo -e "\n=== GET /logs ==="
curl -s "$BASE/logs"
echo
