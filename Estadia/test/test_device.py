from zk import ZK

IP_RELOJ="192.168.1.50"

zk = ZK(IP_RELOJ, port=4370, timeout=5)

try: 
    print("Conectando al reloj...")

    conn = zk.connect()
    print("Conectado")

    info = conn.get_device_info()

    print(f"Información del dispositivo:")
    print(f"Nombre: {info.name}")
    print(f"Firmware: {info.firmware}")
    print(f"Serial: {info.serial}")
    print(f"Hora reloj: {info.device_time}")
    print(f"MAC: {info.mac}")
    print (f"Red: {info.network}")

    conn.disconnect()

except Exception as e:
    print("Error:", e)