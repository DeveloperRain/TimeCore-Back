Arquitectura
============

TIMECORE utiliza una arquitectura organizada por responsabilidades.

Estructura principal
--------------------

``app.routes``
   Define los endpoints HTTP de FastAPI.

``app.services``
   Contiene la lógica de negocio, sincronización y operaciones de datos.

``app.models``
   Define los modelos ORM de SQLAlchemy.

``app.schemas``
   Define los modelos de entrada y salida de Pydantic.

``app.database``
   Administra la conexión y las sesiones de PostgreSQL.

``app.middleware``
   Gestiona errores y comportamiento transversal de la API.

``app.utils``
   Contiene funciones auxiliares y respuestas reutilizables.

Flujo general
-------------

#. El frontend realiza una solicitud HTTP.
#. El router valida y recibe los datos.
#. El servicio ejecuta la lógica de negocio.
#. SQLAlchemy consulta o modifica PostgreSQL.
#. La API devuelve una respuesta estructurada al frontend.