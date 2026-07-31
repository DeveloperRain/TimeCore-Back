Sincronización de relojes
=========================

Sincronización individual
-------------------------

TIMECORE establece conexión con un reloj, descarga empleados y eventos
de asistencia, y almacena la información nueva en PostgreSQL.

Sincronización general
----------------------

La opción ``Sincronizar Todo`` procesa los relojes de manera secuencial.

Si un reloj está desconectado o pierde conexión durante el proceso,
TIMECORE registra el fallo y continúa inmediatamente con el siguiente
dispositivo.

Conservación de información
---------------------------

La eliminación de un empleado o reloj desde la interfaz no borra
físicamente sus datos de PostgreSQL. El registro se conserva y cambia
a estado inactivo para mantener su historial.