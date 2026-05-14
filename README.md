# horizon-finanzas

Proyecto Flask de finanzas personales listo para desplegar en Render.

## Despliegue en Render

1. Asegúrate de que el repositorio esté en Git y listo para subir.
2. En Render, crea un nuevo servicio de tipo `Web Service` basado en el repositorio.
3. Usa el comando de inicio:

   `gunicorn app:app`

4. Configura las variables de entorno en Render:
   - `DATABASE_URL` (PostgreSQL o base de datos gestionada)
   - `SECRET_KEY`

5. El servicio instalará dependencias con `pip install -r requirements.txt`.

## Archivos importantes para Render

- `Procfile`: define el comando de inicio para el servicio web.
- `render.yaml`: configura el servicio de Render de forma declarativa.
- `.env.example`: muestra las variables de entorno necesarias.
