from zk import ZK

IP_RELOJ="192.168.1.50"

zk = ZK(IP_RELOJ, port=4370, timeout=5)

try:
    print("Conectando al reloj...")

    conn = zk.connect()
    print("Conectado")

    asistencias = conn.get_attendance()

    print(f"Asistencias encontradas: {len(asistencias)}")

    for a in asistencias:
        print(f"ID:{a.user_id} Fecha: {a.timestamp} Tipo: {a.status}")

    conn.disconnect()

except Exception as e:
    print("Error:", e)
    