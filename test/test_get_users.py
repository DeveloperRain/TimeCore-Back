from zk import ZK

IP_RELOJ="192.168.1.50"
port=4370

zk = ZK(IP_RELOJ, port=4370, timeout=5)

try:
    print("Conectando al reloj...")

    conn = zk.connect()
    print("Conectado")

    usuarios = conn.get_users()

    print(f"Usuarios encontrados: {len(usuarios)}")

    for u in usuarios:
        print(f"ID:{u.user_id} Nombre: {u.name}")

    conn.disconnect()

except Exception as e:
    print("Error:", e)
