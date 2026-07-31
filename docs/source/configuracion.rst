Configuración
=============

TIMECORE utiliza un archivo ``.env`` para almacenar la configuración de la
base de datos, los relojes biométricos y otros parámetros del sistema.

El repositorio incluye un archivo ``.env.example`` con la estructura de las
variables requeridas, sin exponer credenciales reales.

Por seguridad, el archivo ``.env`` se encuentra excluido del control de
versiones mediante ``.gitignore``.

Ejemplo
-------

.. code-block:: text

   DATABASE_URL=postgresql://usuario:contraseña@localhost:5433/timecore
   SECRET_KEY=CAMBIAR_EN_PRODUCCION
   ACCESS_TOKEN_EXPIRE_MINUTES=60

Seguridad
---------

Los archivos que contienen credenciales no deben incluirse en el
repositorio. Se recomienda utilizar un archivo ``.env`` y agregarlo
a ``.gitignore``.