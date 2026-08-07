# EPi Platform — Eficiencia y Precisión Industrial S.L.

## NUEVO en esta revisión (V6): identificar un elemento suelto por foto

Módulo independiente del stub `/api/v1/photo/redesign` (que rediseña una
instalación completa y sigue sin desarrollar). Este es más simple y ya
funcional:

1. `POST /api/v1/photo/identify-item` — el cliente sube una foto de UN
   elemento suelto (válvula, bomba, sensor...). Por debajo llama a Google
   Cloud Vision API (`app/services/vision_service.py`), pero el cliente
   nunca ve esa marca — solo ve "EPi ha analizado la foto". Requiere la
   variable de entorno `EPI_VISION_API_KEY`; si no está configurada,
   responde con una identificación de respaldo pidiendo que el cliente
   escriba el elemento a mano, sin romper el flujo.
2. El cliente confirma o corrige el elemento detectado.
3. `POST /api/v1/photo/quote-item` — si el cliente quiere oferta de ese
   elemento, se busca el precio (catálogo interno en
   `app/services/scraper.py::lookup_generic_item`, punto de extensión
   para búsqueda web real más adelante), se aplican los mismos márgenes
   de siempre (+40% / +38%), se generan los 2 PDFs (oferta cliente +
   informe interno), se envía el email si hay contacto, y se archiva como
   lead (`profile_selected = "ELEMENTO_UNICO"`), igual que el resto de
   ofertas de EPi.

## Qué ha cambiado en esta revisión

1. **Reorganización de archivos.** Los archivos que subiste tenían el
   contenido cruzado respecto a su nombre (p. ej. lo que se llamaba
   `requirements.txt` era en realidad `main.py`). Aquí cada archivo está
   en su sitio correcto, con nombres coherentes con lo que hace.

2. **Se elimina el login obligatorio del cliente.** Antes había que crear
   usuario/contraseña (`cliente` / `epi2026`) para poder usar el chat y
   generar una oferta. Ahora esos endpoints (`/api/v1/interview/chat`,
   `/api/v1/solution/oneshot`, `/api/v1/report/client-pdf`) son públicos.

3. **Nuevo formulario de contacto opcional** (`ContactInfo`): nombre de
   contacto, empresa, teléfono y email. Ningún campo es obligatorio.

4. **Envío automático de la oferta por email.** Si el visitante deja su
   email, al pulsar "Nosotros nos encargamos" se le envía automáticamente
   el PDF de la oferta (`app/services/email_service.py`, vía SMTP).

5. **Archivado por empresa/contacto.** Cada oferta generada se guarda en
   una nueva tabla `leads` (`app/db/models.py`) con los datos de contacto,
   el precio final y una copia completa de la solución — así queda
   registrada "esa empresa y persona de contacto" aunque nunca haya creado
   una cuenta. Consultable por el personal interno vía `GET /api/v1/leads`.

6. **El login (JWT) se mantiene solo para el personal interno**
   (admin/engineer), que sigue siendo el único que puede ver el Informe
   Interno con costes reales y proveedores.

## Variables de entorno para el envío de email

```
EPI_SMTP_HOST=smtp.tu-proveedor.com
EPI_SMTP_PORT=587
EPI_SMTP_USER=usuario
EPI_SMTP_PASSWORD=contraseña
EPI_SMTP_USE_TLS=true
EPI_MAIL_FROM=ofertas@eficienciayprecision.com
```

Si `EPI_SMTP_HOST` no está configurado, la generación de la oferta sigue
funcionando con normalidad; simplemente no se envía el correo (útil en
desarrollo local).

## Puesta en marcha

```bash
pip install -r requirements.txt --break-system-packages
python -m app.db.seed        # crea catálogo de bombas + usuario admin interno
uvicorn app.main:app --reload
```

La interfaz web queda en `http://localhost:8000/ui/`.

## Nota sobre el margen de contingencia (38%)

El motor comercial (`app/engine/commercial.py`) sigue aplicando el +40%
sobre componentes web y el +38% de contingencia tal como especifica el
dossier. Te comenté aparte que ocultar activamente ese porcentaje al
cliente puede ser un punto delicado de transparencia comercial; el código
no cambia esa lógica de negocio (es tu decisión), pero el documento
cliente sigue mostrando un precio final único, no un desglose de "costes
reales + recargo oculto".
