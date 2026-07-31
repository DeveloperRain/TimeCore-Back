Base de datos
=============

TIMECORE utiliza PostgreSQL como sistema gestor de base de datos para
almacenar la información centralizada de empleados, sucursales,
relojes checadores, asistencias e incidencias.

Tablas principales
------------------

users
   Información de empleados.

devices
   Información de los relojes biométricos.

attendance_records
   Registros de asistencia descargados desde los dispositivos.

branches
   Sucursales registradas.

payroll_incidents
   Incidencias utilizadas para la prenómina.

Características
---------------

* Integridad mediante claves foráneas.
* Índices para optimizar consultas.
* Persistencia de la información.
* Compatibilidad con SQLAlchemy ORM.