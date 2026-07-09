"""Sincronización automática de asistencias de los relojes registrados.

La tarea corre en segundo plano y nunca bloquea las peticiones HTTP.
"""

import asyncio
from datetime import datetime
from threading import Lock

from app.config.logger import get_logger, log_exception
from app.services.db_service import DBService
from app.services.zk_service import ZKService

logger = get_logger("services.auto_sync")

SYNC_INTERVAL_SECONDS = 4 * 60
STARTUP_DELAY_SECONDS = 10

_sync_lock = Lock()


def _is_active_device(device) -> bool:
    """Considera únicamente relojes habilitados; también reintenta los desconectados."""
    return bool(getattr(device, "is_active", True))


def sync_attendance_for_registered_devices() -> dict:
    """Sincroniza asistencias de todos los relojes activos.

    Se ejecuta en un hilo mediante ``asyncio.to_thread`` para no bloquear FastAPI.
    Si otra sincronización automática sigue en curso, omite esta vuelta.
    """
    if not _sync_lock.acquire(blocking=False):
        logger.warning(
            "[AUTO-SYNC] Se omitió una ejecución porque la sincronización anterior sigue activa"
        )
        return {
            "skipped": True,
            "devices_synced": 0,
            "devices_failed": 0,
            "attendance_synced": 0,
        }

    try:
        devices = [
            device
            for device in DBService.get_all_devices()
            if _is_active_device(device)
        ]

        devices_synced = 0
        devices_failed = 0
        attendance_synced = 0

        logger.info(
            "[AUTO-SYNC] Iniciando sincronización automática de %s reloj(es)",
            len(devices),
        )

        for device in devices:
            try:
                attendance = ZKService.get_attendance_records(
                    ip=device.ip,
                    port=device.port,
                    password=getattr(device, "password", ""),
                )

                new_records = DBService.save_bulk_attendance(attendance)
                attendance_synced += int(new_records or 0)
                devices_synced += 1

                DBService.update_device_status(
                    device_id=device.id,
                    estado="Conectado",
                    ultima_sincronizacion=datetime.utcnow(),
                )

                logger.info(
                    "[AUTO-SYNC] %s (%s): %s asistencia(s) nueva(s)",
                    getattr(device, "name", f"Reloj {device.id}"),
                    device.ip,
                    int(new_records or 0),
                )

            except Exception as exc:
                devices_failed += 1

                try:
                    DBService.update_device_status(
                        device_id=device.id,
                        estado="Desconectado",
                    )
                except Exception:
                    pass

                log_exception(
                    logger,
                    exc,
                    f"[AUTO-SYNC] Error en reloj {getattr(device, 'id', '?')}",
                )

        logger.info(
            "[AUTO-SYNC] Finalizada. Relojes: %s correctos, %s con error. "
            "Asistencias nuevas: %s. Próxima ejecución en 4 minutos",
            devices_synced,
            devices_failed,
            attendance_synced,
        )

        return {
            "skipped": False,
            "devices_synced": devices_synced,
            "devices_failed": devices_failed,
            "attendance_synced": attendance_synced,
        }

    finally:
        _sync_lock.release()


async def automatic_sync_loop() -> None:
    """Bucle permanente de sincronización automática."""
    logger.info(
        "[AUTO-SYNC] Servicio iniciado. Primera sincronización en %s segundos; "
        "después se ejecutará cada 4 minutos",
        STARTUP_DELAY_SECONDS,
    )

    await asyncio.sleep(STARTUP_DELAY_SECONDS)

    while True:
        try:
            await asyncio.to_thread(sync_attendance_for_registered_devices)
        except asyncio.CancelledError:
            logger.info("[AUTO-SYNC] Servicio detenido")
            raise
        except Exception as exc:
            log_exception(logger, exc, "[AUTO-SYNC] Error inesperado en el ciclo")

        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
