from zk import ZK

IP_RELOJ="192.168.1.50"

zk = ZK(IP_RELOJ, port=4370, timeout=5)

try:
    print("Conectando al reloj...")

    conn = zk.connect()
    print("Conectado")

    conn.set_user(
        uid=99,
        name="usuario de prueba",
        password=' ',
        group_id=' ',
        user_id='99 '
    )

    print("Usuario creado")

    conn.disconnect()

except Exception as e:
    print("Error:", e)