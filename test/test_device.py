from zk import ZK

IP_RELOJ = "192.168.1.50"


def call_if_available(conn, method_name, default="Desconocido"):
    method = getattr(conn, method_name, None)
    if not callable(method):
        return default

    try:
        value = method()
        return default if value is None else value
    except Exception:
        return default


zk = ZK(IP_RELOJ, port=4370, timeout=5)
conn = None

try:
    print("Conectando al reloj...")

    conn = zk.connect()
    print("Conectado")

    print("Informacion del dispositivo:")
    print(f"Nombre: {call_if_available(conn, 'get_device_name')}")
    print(f"Firmware: {call_if_available(conn, 'get_firmware_version')}")
    print(f"Serial: {call_if_available(conn, 'get_serialnumber')}")
    print(f"Hora reloj: {call_if_available(conn, 'get_time')}")
    print(f"MAC: {call_if_available(conn, 'get_mac')}")
    print(f"IP: {IP_RELOJ}")

except Exception as e:
    print("Error:", e)
finally:
    if conn:
        conn.disconnect()
