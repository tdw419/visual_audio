#!/bin/bash
# Quick VNC handshake test - prints bytes received from server

host="127.0.0.1"
port=5901

echo "[*] Connecting to $host:$port..."

(
    echo -ne "RFB 003.008\n"
    sleep 0.5
    # Read version response
    read -t 1 response
    echo "[+] Server version: $response"

    # Try security types
    read -t 1 sec_count
    if [ -n "$sec_count" ]; then
        dec=$(echo "$sec_count" | xxd -p)
        echo "[+] Security type count: $dec"
        read -t 1 sec_types
        echo "[+] Security types: $(echo "$sec_types" | xxd -p)"

        # Request None auth (type 1)
        echo -ne "\x01"
        sleep 0.5
        read -t 1 auth_result
        echo "[+] Auth result: $(echo "$auth_result" | xxd -p)"
    fi
) | nc "$host" "$port"

echo "[*] Connection closed"