from zk import ZK

IP_RELOJ="192.168.1.50"

zk = ZK(IP_RELOJ, port=4370, timeout=5)

try:
    print("Conectando al reloj...")

    conn = zk.connect()
    print("Conectado")

    UID = 99

    conn.delete_user(uid=UID)

    print(f"Usuario {UID} eliminado")


    conn.disconnect()

except Exception as e:
    print("Error:", e)

    