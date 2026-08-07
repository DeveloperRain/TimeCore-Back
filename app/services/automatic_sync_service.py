"""Sincronización automática configurable por reloj."""

import asyncio
from datetime import datetime, timedelta
from threading import Lock

from app.config.logger import get_logger, log_exception
from app.services.db_service import DBService
from app.services.zk_service import ZKService

logger = get_logger("services.auto_sync")

CHECK_INTERVAL_SECONDS = 30
STARTUP_DELAY_SECONDS = 10
_sync_lock = Lock()


def _is_due(device, now: datetime) -> bool:
    """
    Determina si un dispositivo debe ejecutar su sincronización automática.

    :param device: Dispositivo cuya configuración de sincronización se evalúa.
    :type device: object
    :param now: Fecha y hora utilizadas para verificar el intervalo de sincronización.
    :type now: datetime
    :return: Indica si el dispositivo está activo, tiene habilitada la sincronización automática y su intervalo ya se cumplió.
    :rtype: bool
    """
    if not bool(getattr(device, "is_active", True)):
        return False
    if not bool(getattr(device, "auto_sync_enabled", True)):
        return False

    interval = max(1, min(int(getattr(device, "sync_interval_minutes", 4) or 4), 60))
    last_sync = getattr(device, "last_sync_at", None)
    return last_sync is None or now >= last_sync + timedelta(minutes=interval)


def sync_due_devices() -> dict:
    """
    Sincroniza los relojes cuyo intervalo de sincronización automática ya se cumplió.

    :return: Resumen con el estado de la ejecución y las cantidades de dispositivos y asistencias procesadas.
    :rtype: dict
    """
    if not _sync_lock.acquire(blocking=False):
        logger.warning("[AUTO-SYNC] Se omitió la revisión: otra sincronización sigue activa")
        return {"skipped": True, "devices_synced": 0, "devices_failed": 0, "attendance_synced": 0}

    try:
        now = datetime.utcnow()
        devices = [device for device in DBService.get_all_devices() if _is_due(device, now)]

        if not devices:
            return {"skipped": False, "devices_synced": 0, "devices_failed": 0, "attendance_synced": 0}

        logger.info("[AUTO-SYNC] %s reloj(es) requieren sincronización", len(devices))
        devices_synced = 0
        devices_failed = 0
        attendance_synced = 0

        for device in devices:
            interval = max(1, min(int(getattr(device, "sync_interval_minutes", 4) or 4), 60))
            try:
                attendance = ZKService.get_attendance_records(
                    ip=device.ip,
                    port=device.port,
                    password=getattr(device, "password", ""),
                    on_disconnect=lambda _details, device_id=device.id, ip=device.ip, port=device.port: (
                        ZKService.mark_device_disconnected(
                            ip,
                            port,
                            reason="Desconectado durante sincronización automática",
                        ),
                        DBService.update_device_status(
                            device_id=device_id,
                            estado="Desconectado",
                        ),
                    ),
                )
                for record in attendance:
                    record["branch_id"] = device.branch_id
                    record["device_id"] = device.id

                new_records = int(DBService.save_bulk_attendance(attendance) or 0)
                synced_at = datetime.utcnow()
                ZKService.mark_device_connected(device.ip, device.port)
                DBService.update_device_sync_status(
                    device_id=device.id,
                    estado="Conectado",
                    synced_at=synced_at,
                )
                devices_synced += 1
                attendance_synced += new_records
                logger.info(
                    "[AUTO-SYNC] %s (%s): %s nueva(s). Intervalo: %s min",
                    getattr(device, "name", f"Reloj {device.id}"),
                    device.ip,
                    new_records,
                    interval,
                )
            except Exception as exc:
                devices_failed += 1
                try:
                    ZKService.mark_device_disconnected(
                        device.ip,
                        device.port,
                        reason=str(exc),
                    )
                    DBService.update_device_status(device_id=device.id, estado="Desconectado")
                except Exception:
                    pass
                log_exception(logger, exc, f"[AUTO-SYNC] Error en reloj {getattr(device, 'id', '?')}")

        return {
            "skipped": False,
            "devices_synced": devices_synced,
            "devices_failed": devices_failed,
            "attendance_synced": attendance_synced,
        }
    finally:
        _sync_lock.release()


async def automatic_sync_loop() -> None:
    """
    Ejecuta continuamente las revisiones de sincronización automática de los relojes.

    :return: No devuelve ningún valor.
    :rtype: None
    """
    logger.info(
        "[AUTO-SYNC] Servicio por reloj iniciado. Primera revisión en %s segundos; revisiones cada %s segundos",
        STARTUP_DELAY_SECONDS,
        CHECK_INTERVAL_SECONDS,
    )
    await asyncio.sleep(STARTUP_DELAY_SECONDS)

    while True:
        try:
            await asyncio.to_thread(sync_due_devices)
        except asyncio.CancelledError:
            logger.info("[AUTO-SYNC] Servicio detenido")
            raise
        except Exception as exc:
            log_exception(logger, exc, "[AUTO-SYNC] Error inesperado en el ciclo")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)