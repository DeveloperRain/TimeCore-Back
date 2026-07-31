Instalación
===========

Requisitos
----------

* Python 3.12 o superior.
* PostgreSQL.
* Acceso de red a los relojes checadores.
* Entorno virtual de Python.

Preparación
-----------

Desde la raíz del backend:

.. code-block:: console

   python -m venv .venv
   .venv\Scripts\activate
   python -m pip install -r requirements.txt

Ejecución
---------

.. code-block:: console

   uvicorn app.routes.main:app --reload

La API estará disponible en:

* ``http://127.0.0.1:8000``
* ``http://127.0.0.1:8000/docs``
* ``http://127.0.0.1:8000/redoc``