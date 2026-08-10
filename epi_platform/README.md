# EPi Platform — Eficiencia y Precisión Industrial S.L.

## FIX URGENTE 1.9.8 (agosto 2026): la entrevista se quedaba en bucle infinito

Jon reportó (con captura de pantalla) que EPi se quedaba repitiendo
"¿Qué longitud total tiene la tubería (metros)?" para siempre, sin
importar lo que contestara ("8 metros", "8", "8 metrps"). Bug real y
grave — afectaba a la entrevista principal (dimensionamiento de bomba),
no solo a un caso raro.

**Causa**: la extracción de cada campo exigía que el número y una palabra
clave concreta ("longitud"/"tubería"/"tubo" para la longitud, "altura"
para el desnivel, "mm" para el diámetro...) aparecieran en el MISMO
mensaje. La palabra clave estaba en la PREGUNTA, no hacía falta que el
cliente la repitiera en la respuesta — así que un "8 metros" o un simple
"8" nunca se capturaba, y el sistema volvía a preguntar lo mismo sin fin.
Afectaba potencialmente a los 5 campos (caudal, altura, longitud,
diámetro, fluido), no solo a longitud — fue el que Jon vio porque fue el
que le tocó responder así.

**Arreglo**: ahora, además de la extracción por palabra clave (que sigue
funcionando igual para cuando el cliente da varios datos juntos en una
frase), se empareja cada pregunta ya formulada con la respuesta que le
siguió inmediatamente. Si esa respuesta no se captó por palabra clave, se
usa tal cual como respuesta a ESA pregunta concreta (número suelto para
los campos numéricos, texto tal cual para el fluido).

**Importante — por qué el primer intento de arreglo no bastó**: el primer
parche solo miraba la pregunta más reciente en cada turno, pero como el
sistema no guarda memoria (recalcula todo desde cero cada vez, releyendo
todos los mensajes), en el turno siguiente ese dato "se olvidaba" otra vez
y el sistema retrocedía a preguntar por él. Solo se dio por bueno tras
simular la conversación completa turno a turno y comprobar que el dato NO
se pierde más adelante — no solo que la siguiente pregunta parezca
correcta en el momento.

Verificado con el caso exacto de la captura de Jon (incluida la errata
"8 metrps"), con una conversación completa de principio a fin, y
comprobando que dar todos los datos juntos en una sola frase — la otra
forma de usarlo — sigue funcionando igual que antes.

## FIX 1.9.7 (agosto 2026): bomba de clapetas (chop-check) para adhesivos viscosos

Jon pidió que para adhesivos MUY VISCOSOS/PASTOSOS se use una bomba de
clapetas (chop-check en inglés — término confirmado por búsqueda: es
justo el nombre técnico correcto), con relación de compresión entre 23:1
y 46:1, en vez de la bomba de pistón de bolas normal.

La pregunta de viscosidad ya existía en la entrevista 1K ("fluido, medio,
o muy viscoso/pastoso") — ahora `app/agents/adhesive.py` detecta la
respuesta y marca `is_viscous`, que el backend usa para elegir el
diccionario de bombas correcto.

**Referencias reales encontradas** (únicas dos en nuestra base dentro del
rango 23:1-46:1 que pidió Jon, ambas ARO):
- `AF0623S11KK47-1` — chop-check 6" 23:1 — 9.067,00 €
- `AF0646S11GF47-1` — chop-check 6" 46:1 — 9.067,00 €

Mismo criterio que con Graco: no hay tarifa real de Wagner/Binks en ese
rango de relación, así que los tres perfiles usan ARO (instrucción de Jon:
"vete siempre con lo que tengamos"), diferenciados por relación de
compresión en vez de precio — barata y calidad-precio con la de 23:1,
premium con la de 46:1 (mayor relación = más capacidad para el material
más pastoso, coherente con el posicionamiento premium aunque el precio
sea idéntico en nuestros datos).

## FIX 1.9.6 (agosto 2026): tres perfiles de bomba de pistón en la oferta de adhesivo

Jon pidió que la oferta de equipo de adhesivo (1K) tuviera tres niveles de
inversión (como el resto de EPi), cada uno con una marca de bomba de
pistón distinta: barata (Wagner/Binks), calidad-precio (Graco), premium
(ARO Ingersoll Rand). Al revisarlo con Jon salieron dos ajustes:

- **No tenemos tarifa real de Binks** (el precio que había era un dato
  suelto de la base de repuestos, no una tarifa confirmada) — se mantiene
  igualmente por ser el único dato real disponible para el nivel barato.
- **Graco no tiene precio de bomba completa en nuestros datos** — solo
  encontramos kits de reparación y una pistola suelta, no una bomba
  completa. Búsqueda web tampoco dio un precio fiable. Instrucción de Jon:
  "mientras no tengamos más en la base de datos, vete siempre con lo que
  tengamos" — así que el nivel calidad-precio usa también ARO (un modelo
  más económico que el de premium), no Graco, hasta que haya tarifa real.

**Los tres niveles ahora mismo** (todos con precio real verificado en
nuestra base de repuestos, ninguno inventado):
- BARATA: Binks `02271001` — 1.870,50 €
- CALIDAD_PRECIO: ARO Ingersoll Rand `AF0409C11FF22` (4-1/4" 9:1, 2 bolas) — 5.702,00 €
- PREMIUM: ARO Ingersoll Rand `AF0402M11KS48-1` (4-1/4" 2:1, 4 bolas, AFX) — 12.660,00 €

El resto de elementos (pistola, elevador, manguera, fotocélula/electroválvula)
no varían por perfil — solo la bomba, que es donde Jon pidió la
diferenciación. Añadido selector de perfil en el frontend, visible solo
para adhesivo 1K (no aplica a 2K, que no genera oferta con precio).

## FIX 1.9.5 (agosto 2026): croquis de instalación + bomba de pistón y manguera en adhesivo

Jon pidió que las ofertas incluyan "una foto real y un croquis simulado de
la instalación". Aviso importante, tratado con cuidado: **no se han
añadido fotos de fabricantes sacadas de internet** — usarlas en un
documento comercial de la empresa sin licencia es un riesgo real de
derechos de autor (son imágenes de terceros, no de EPi). En su lugar se
generó un **croquis esquemático propio** (`app/services/installation_sketch.py`),
en el mismo estilo de plano técnico que ya usa la web, con cada elemento
de la oferta en una caja conectada por flechas en el orden real del
proceso. Añadido a la Oferta Cliente principal (aspiración → bomba →
primeros elementos de la lista de materiales → descarga) y a la Oferta de
Equipo de Adhesivo (bidón → elevador → bomba de pistón → manguera →
pistola/automatismo).

**Adhesivo 1K — dos cosas más que pidió Jon:**
- Nueva pregunta: cuántos metros de manguera hacen falta.
- La oferta ahora incluye también la bomba de pistón (real: `02271001`,
  Binks Reinhardt-Technik, 1.870,50 €) y la manguera PTFE de alta presión
  (real: `00139000`, mismo fabricante, calculada a 152 €/m según los
  metros indicados) — antes solo se ofertaban pistola/automatismo +
  elevador.

**Fallos reales corregidos al probarlo:**
- El orden de los elementos (tabla y croquis) tenía el elevador DESPUÉS de
  la bomba de pistón — físicamente al revés (el elevador es lo que baja al
  bidón primero). Corregido en `app/main.py` y en la construcción del
  croquis.
- Al insertar el croquis en la Oferta Cliente, el contenido se desplazó a
  una segunda página — comportamiento normal de paginación, no un fallo
  (verificado generando el PDF de verdad y revisando ambas páginas).

## FIX 1.9.4 (agosto 2026): equipo de adhesivo con precio real (1K) / seguimiento (2K)

Jon pidió que, para adhesivo de 1 componente, la oferta incluya con precio y
referencia real: la pistola manual de extrusión Walther Pilot (si es
aplicación manual) o la fotocélula/electroválvula (si es automática), más
el elevador de bidón. Para 2 componentes, en cambio, no se genera oferta
con precio — se recogen los datos y se envía un correo al cliente avisando
de que un ingeniero le contactará.

**Referencias reales usadas** (localizadas en nuestra propia base de
repuestos de 14.629 líneas, no inventadas):
- Pistola manual de extrusión: `V1025000000` (Walther Spritz-und
  Lackiersysteme GmbH), 817,50 €.
- Fotocélula: `K96311100` (Zator, S.R.L.), 175,00 €.
- Electroválvula: `ELT000321` (Zator, S.R.L.), 135,80 €. El "MZ200" que
  mencionó Jon no está literalmente en nuestros datos con ese código exacto
  — sí existe toda la familia Zator "MZ..." de válvulas de extrusión
  (MZK408, MZB200, MZB300), así que se usó la electroválvula real más
  cercana en vez de inventar una referencia — a confirmar con Jon si quiere
  el código exacto.
- Elevador de bidón: no está en el catálogo de repuestos (es equipo, no
  recambio). Precio interpolado entre 9.000 € (20 L) y 12.000 € (200 L),
  siempre marcado como orientativo pendiente del diámetro exacto del bidón.

**Cambios técnicos:**
- `app/agents/adhesive.py`: añadida la pregunta de viscosidad de cada
  componente para 2K; al terminar, devuelve datos estructurados (no solo
  texto) para poder generar la oferta o el correo sin otra ronda de
  preguntas.
- Dos endpoints nuevos: `/api/v1/adhesive/oferta` (1K, con PDF y precio) y
  `/api/v1/adhesive/seguimiento` (2K, solo correo de confirmación).
- Frontend: nuevo botón "Generar oferta / Enviar seguimiento" al terminar
  la conversación de adhesivo.

**Fallo real encontrado y corregido al probar el PDF**: el texto largo en
las celdas de las tablas (fabricante, descripción...) se solapaba
visualmente en vez de ajustarse — afectaba a las 4 tablas de oferta del
PDF (cliente, elemento suelto, repuesto, y esta nueva de adhesivo).
Corregido usando párrafos con ajuste de línea en vez de texto plano en
todas ellas.

## FIX 1.9.3 (agosto 2026): dosificación de adhesivo — bidón, aplicación, repuestos

Jon pidió que el módulo de adhesivo (`app/agents/adhesive.py`) pregunte,
además de lo específico de 1K/2K, tres cosas más — comunes a ambas ramas:

1. **Formato de suministro** del material (típicamente bidón de 20 o 200
   litros), avisando de que en el pedido hará falta el **diámetro exacto**
   del bidón para dimensionar bien el conjunto.
2. **Aplicación manual o automática** — para saber si hace falta pistola
   manual o válvula/aplicador automático.
3. **Si es automática**: si necesita fotocélula y electroválvula —
   avisando de que estos elementos se pueden coger del catálogo de
   repuestos de EPi (ejemplo dado por Jon: la electroválvula MZ200 de
   Zator).

También se añadió el nuevo tipo de tecnología `PISTON_NEUMATICO` (bomba de
pistón de aire, ej. ARO 4-ball/AFX) al motor de razonamiento — mecánicamente
distinta de la neumática de doble membrana aunque también funcione con
aire comprimido, con buen comportamiento en fluidos viscosos (relevante
para adhesivos). **Nota**: se comprobó que las 297 referencias ARO de
pistón detectadas anoche NO estaban realmente en el catálogo operativo de
EPi (les faltaba el caudal, igual que a otras ~550 referencias ARO), así
que no había ninguna oferta real mal clasificada que corregir — el tipo
nuevo queda preparado en el sistema para cuando se localicen sus caudales.

**Fallo real encontrado y corregido al probarlo** (con simulación completa
del flujo, no solo revisión de código): el frontend duplica el último
mensaje del usuario en `history` antes de llamar al backend — sin tenerlo
en cuenta, las preguntas se desajustaban una posición. Además, la primera
comprobación de "aplicación automática" fallaba por la tilde de
"automática" (comparaba con la palabra sin tildes). Ambos corregidos y
verificados con una simulación completa de conversación en los tres casos
(1K+automática, 1K+manual, 2K+automática).

## Sesión nocturna (agosto 2026): más material ARO + perfil barato = neumática

### 1. Perfil "barata" prioriza neumática

Antes, dentro de las tecnologías físicamente aptas para el proceso, EPi las
probaba en orden de EFICIENCIA (lo que usa `PumpTechnologyAdvisor` para
puntuar) — así que en el perfil BARATA podía acabar recomendando una
centrífuga o de engranajes antes que una neumática, aunque la neumática sea
casi siempre la de menor coste de compra. Corregido en `select_from_db`
(`app/main.py`): en el perfil BARATA, si la neumática de doble membrana es
físicamente apta, se prueba SIEMPRE la primera — por delante de tecnologías
con mejor puntuación de eficiencia. Nunca se fuerza si no es apta (sólidos,
abrasivos, etc. pueden seguir descartándola).

### 2. Más material ARO decodificado (para compatibilidad química)

Investigación en fichas oficiales ARO/Ingersoll Rand y distribuidores
(PumpCatalog, TFPumps, Applied, KAD, manual oficial ARO 66610X-X-C):

- Ampliado el decodificador de la serie nueva PD/PE (antes solo cubría
  "PD", ahora también "PE" con su 4º segmento opcional).
- Añadido el decodificador oficial del código legado "666xxx" (tabla de
  asiento/bola/diafragma del manual ARO, y letras de cuerpo confirmadas
  como AF/AJ/AP/A3/B3=Polipropileno, A4=PVDF).
- Resultado: material de cuerpo 458→589, elastómero 359→635 (sobre 2.059
  referencias totales). En el catálogo operativo (1.480 bombas): cuerpo
  411→537, elastómero 357→615.

**Sigue habiendo ~1.470 referencias sin material de cuerpo** (sobre todo
ARO de series antiguas sin manual localizado, y toda la parte de
repuestos). No se ha inventado ningún dato — donde no hay confirmación, se
queda vacío (amarillo en el Excel) en vez de asumir compatibilidad.

### 3. AVISO IMPORTANTE — revisar con Matías antes de tocar

Las 297 referencias ARO "AF04xx..." (ej. `AF0402M11FF48`) **no son bombas
neumáticas de doble membrana** — son bombas de **pistón** (ARO 4-ball
Piston Pump / tecnología AFX), mecánicamente distintas. Actualmente están
clasificadas en el catálogo operativo como "Neumática de Doble Membrana"
(mismo criterio que el resto de ARO), lo cual es **incorrecto**. No se ha
corregido esta noche porque cambiar la tecnología de 297 filas sin más
verificación es arriesgado sin que alguien lo revise antes. Recomendado:
confirmar y, si procede, crear una categoría de tecnología nueva ("Pistón
neumático" o similar) antes de seguir ofertándolas como si fueran AODD —
tienen un comportamiento de caudal/presión diferente.

## FIX 1.8.5 (agosto 2026): quitadas las bombas sin motor (eje libre) del catálogo

Jon detectó que EPi estaba ofertando una bomba "SIN MOTOR" — un modelo a
eje libre, pensado para acoplarse a un motor que el cliente ya tiene
instalado (típico en reposición de repuestos), no para venderse como
equipo completo nuevo. Se identificaron y quitaron **29 referencias** de
`app/db/pumps_catalog.csv` que contenían "SIN MOTOR", "EJE LIBRE", "BARE
SHAFT" o variantes en su descripción/modelo — de Cucchi, Sydex y CDR. El
catálogo pasa de 1.509 a **1.480 bombas operativas**. Como el arranque ya
compara el número de filas del CSV contra lo que hay en la base de datos
(fix 1.7.2), este cambio se aplica solo en el próximo redeploy, sin pasos
manuales adicionales.

## FIX 1.8.4 (agosto 2026): copia interna del Informe Técnico por email

Jon pidió recibir también el segundo PDF (el Informe Interno — de dónde ha
sacado EPi cada componente, razonamiento de tecnología, compatibilidad
química) que antes solo se podía descargar manualmente con acceso de
personal interno. Ahora, cada vez que se genera un presupuesto completo
(`/api/v1/solution/oneshot`), se envía automáticamente una copia de ese
informe a `epi@eficienciayprecisionindustrial.com` — independientemente de
si el cliente dejó su email o no (esto es seguimiento interno, no depende
del cliente). Configurable con `EPI_INTERNAL_REPORT_EMAIL` si en el futuro
se quiere cambiar la dirección de destino.

## FIX 1.8.2/1.8.3 (agosto 2026): entrevista — unidades y medidas seguidas

Detectado por Jon en producción, dos fallos en `_extract_fields`
(`app/agents/interview.py`, modo sin LLM):
- No reconocía litros/minuto salvo escrito exactamente "l/min" o "lpm" —
  ampliado a "litros por minuto", "lts/min", "litros/minuto", etc. (y lo
  mismo para litros/hora).
- La frase "3 metros de altura 8 metros de tubería" (dos medidas seguidas)
  le asignaba a la altura el número de la tubería. Corregido invirtiendo
  el orden de prioridad de búsqueda: se prueba primero "NÚMERO metros de
  PALABRA_CLAVE" (el orden más natural cuando hay varias frases seguidas),
  y solo si no encuentra nada así se prueba el orden inverso.

## FIX 1.8.1 (agosto 2026): la base de datos no persistía + URL de Postgres de Render

Detectado tras revisar los logs de producción: los mensajes de arranque
mostraban "0 bombas antiguas sustituidas por 1509 nuevas" en CADA reinicio,
en vez de "ya está actualizado" a partir del segundo arranque. Eso
confirmaba que la base de datos era efímera (sin `DATABASE_URL` apuntando
a un Postgres real, se usa un SQLite local que vive solo dentro del
contenedor) — no solo el catálogo de bombas se reconstruía cada vez, TODO
se perdía en cada reinicio: usuarios internos y, más importante, los leads
(consultas/presupuestos) de clientes reales.

**Solución**: crear una base de datos PostgreSQL en Render (gratuita para
empezar) y apuntar `DATABASE_URL` a ella. De paso, arreglado un problema
que habría impedido que funcionara: Render entrega la URL con el prefijo
`postgres://`, que SQLAlchemy 2.x ya no reconoce como dialecto válido
(hace falta `postgresql://`) — `app/db/database.py` ahora reescribe el
prefijo automáticamente si hace falta, así que la URL de Render se puede
pegar tal cual.

**Aviso para Jon**: el plan gratuito de PostgreSQL en Render caduca a los
90 días — para no perder el histórico de clientes en ese plazo, pasar a un
plan de pago antes de esa fecha (o hacer copias de seguridad periódicas).

## FIX 1.8.0 (agosto 2026): la entrevista repreguntaba datos ya dados

Detectado por Jon en producción: si el cliente daba todos los datos juntos
en el primer mensaje, EPi seguía preguntando uno a uno igualmente, y al
final siempre calculaba con los mismos valores de ejemplo (15 m3/h, 8 m,
25 m, 50 mm, agua) — ofertando siempre la misma bomba sin importar lo que
el cliente hubiera escrito.

**Causa raíz**: sin una `OPENAI_API_KEY` configurada en Render, EPi usa un
modo de reserva ("sin LLM") pensado solo para que la app nunca se rompa —
pero ese modo original se limitaba a contar turnos y hacer las mismas 6
preguntas en orden fijo, sin leer el contenido de lo que el cliente
escribía, y terminaba siempre con los mismos valores de ejemplo
hardcodeados.

**Arreglado** (`app/agents/interview.py`, método `_rule_based`): ahora, en
cada turno, se analizan TODOS los mensajes del cliente hasta el momento
buscando por palabras clave los 5 datos hidráulicos (caudal, altura,
longitud, diámetro, fluido) en cualquier orden ("altura de 8 m" o "8 m de
altura" valen igual), y solo se pregunta por lo que de verdad falte. Si el
cliente lo da todo junto, se pasa directo a la última pregunta (proceso/
tecnología). También entiende negaciones simples ("no lleva sólidos").

**Esto sigue sin ser tan bueno como el modo con LLM real** (que sí entiende
lenguaje natural sin depender de patrones de texto) — si en algún momento
Jon quiere contratar una clave de OpenAI y ponerla como variable de entorno
`OPENAI_API_KEY` en Render, EPi cambiará automáticamente al modo inteligente
sin tocar nada más del código.

## FIX 1.7.3/1.7.4 (agosto 2026): el email fallaba en silencio + logs invisibles

Jon reportó que el correo con la oferta no llegaba. Dos fallos combinados:

1. `app/services/email_service.py` atrapaba cualquier error de envío
   (usuario/contraseña incorrectos, servidor no disponible...) con un
   `except Exception: return False` que no dejaba ningún rastro — ni éxito
   ni fallo quedaban registrados en ningún sitio. Arreglado: ahora se
   imprime siempre el resultado (`Email de oferta enviado correctamente a
   ...` o `ERROR enviando email de oferta a ...: <motivo exacto>`).
2. Aunque se arregló el `print()`, seguía sin verse en los logs de Render.
   Causa: Python, dentro de Docker, retiene (`buffer`) la salida estándar
   por defecto — los `print()` sueltos pueden quedarse esperando en el
   buffer indefinidamente en vez de mostrarse al momento. Arreglado con
   `ENV PYTHONUNBUFFERED=1` en el `Dockerfile`.

## FIX CRÍTICO 2 (1.7.2, agosto 2026): las bombas se preparaban pero nunca se guardaban

Encontrado en los logs reales de Render tras el fix 1.7.1: el catálogo de
1.509 bombas SÍ se cargaba en cada arranque, pero un fallo posterior en la
creación de usuarios internos (incompatibilidad de versión entre
`passlib` y `bcrypt`: `password cannot be longer than 72 bytes`) ocurría
ANTES del único `db.commit()` de toda la función `seed()` — así que ese
fallo deshacía también el guardado de las bombas, aunque el mensaje de
consola dijera "1509 nuevas". Nunca llegaban a la base de datos real.

**Dos fixes:**
1. `requirements.txt`: se fija `bcrypt==4.0.1` (la última versión
   compatible con `passlib==1.7.4`) — causa raíz del error de hashing.
2. `app/db/seed.py`: el guardado del catálogo de bombas y el de los
   usuarios internos ahora son dos pasos independientes, cada uno con su
   propio `commit()`. Un fallo en el paso de usuarios (por bcrypt o
   cualquier otra cosa en el futuro) ya no puede deshacer el catálogo de
   bombas, que se guarda primero y de forma aislada.

---

## FIX CRÍTICO 1 (1.7.1, agosto 2026): el catálogo real nunca se cargaba solo

Detectado en producción: la base de datos seguía con las 6 bombas de
ejemplo de la V6 después de desplegar hasta la V11. Causa raíz, dos fallos
combinados:

1. **Nada llamaba a `seed()` automáticamente.** Ni el `Dockerfile`, ni
   `main.py`, ni Render — había que ejecutar `python -m app.db.seed` a
   mano por Shell. El plan gratuito de Render no tiene Shell, así que
   nunca se pudo ejecutar.
2. Aunque se hubiera podido ejecutar, `seed()` solo insertaba el catálogo
   **si la tabla estaba completamente vacía** (`if not
   db.query(PumpModel).first()`). Como ya tenía las 6 bombas de ejemplo
   antiguas, esa condición era falsa y nunca las habría sustituido.

**Solución aplicada:**
- `app/main.py` ahora llama a `seed()` automáticamente en cada arranque
  (justo después de crear las tablas). Envuelto en `try/except` para que un
  fallo de seed nunca impida arrancar la aplicación.
- `app/db/seed.py` ya no comprueba "¿está vacía la tabla?" sino "¿el número
  de bombas coincide con el CSV actual?". Si no coincide (catálogo antiguo,
  vacío, o el CSV se ha actualizado con más/menos bombas en una futura
  versión), sustituye la tabla entera por el contenido del CSV. Si coincide,
  no hace nada — arranque rápido, sin tocar la base de datos en cada
  reinicio normal.

Con esto, cualquier despliegue futuro (subir código nuevo a GitHub →
redeploy en Render) actualiza el catálogo de bombas solo, sin depender de
Shell ni de que alguien se acuerde de ejecutar nada a mano.

---

## De la V11: identidad visual EXACTA (a partir del HTML real de la web)

Corrección sobre la V10: aquella versión se basó en fotos/capturas de la
marca (colores aproximados por análisis de imagen). En esta, Jon subió el
**HTML real de la web** (`index.html`), así que los valores ya no son una
aproximación — son los mismos que usa la web en producción.

**Colores exactos (de las variables CSS reales de la web):**
```
--navy-deep: #071527   (fondo del header/hero)
--navy:      #0e2b4d   (azul principal)
--paper:     #f5f2e9   (fondo del contenido — ¡no es oscuro!, es un
                         tono crema/papel, algo que no se apreciaba
                         solo mirando el logo)
--brass:     #c69a45   (acento — antes tenía #C9A227, aproximado)
--brass-bright: #e0b25f
--ink:       #1a2433   (texto principal)
--ink-soft:  #4a5568
```

**Tipografías exactas:** Cormorant (titulares, serif elegante), IBM Plex
Sans (cuerpo), IBM Plex Mono (etiquetas/navegación en mayúsculas,
letter-spacing amplio — el detalle "técnico" de la marca). En la web
(`app/frontend/index.html`) se cargan de Google Fonts, igual que hace la
web real — funcionará en producción porque el navegador del cliente sí
tiene acceso a internet. En los PDFs, IBM Plex Mono se ha registrado con
el archivo de fuente real (`app/assets/fonts/IBMPlexMono-*.ttf`) para las
etiquetas pequeñas; Cormorant no tenía sustituto exacto disponible sin
conexión a internet, así que los titulares siguen en Times (serif clásica,
la aproximación más cercana que se pudo hacer offline).

**Icono de cabecera real**: se extrajo el icono pequeño (mira/cruceta) que
la propia web usa en su barra de navegación, directamente del HTML (estaba
embebido en base64), en vez de usar el logotipo grande completo — así la
cabecera de EPi replica exactamente la estructura de la web (icono +
nombre en dos líneas), no una interpretación propia.

**Fondo "papel" en el contenido**: el mayor cambio de fondo (nunca mejor
dicho) respecto a la V10 es que el contenido de la app ya NO usa un gris
neutro — usa el mismo tono crema/papel (`#f5f2e9`) que la web real,
coherente con la estética de "plano técnico sobre papel" del resto de la
marca.

Todo esto se comprobó renderizando la página de verdad (con Playwright) y
generando PDFs de verdad, no solo revisando el código.

---

## De la V10: identidad visual (primera aproximación, basada en imágenes)

Añadido sobre la V9 (curva de bomba): tanto la interfaz de EPi como los PDFs
que genera usan ya el logo y el estilo visual nuevos de la web.

**Colores extraídos directamente de los archivos que subió Jon**
(`Logo_nuevo.jpg`, `Fondo_Web.jpg`, `Logo_EPI_sin_fondo.png`):
- Fondo de marca: `#0F1822` (azul marino muy oscuro)
- Rejilla decorativa: gris azulado apagado
- Acento: `#C9A227` (dorado, ya se usaba antes y encaja bien con el navy)
- Tipografía: serif elegante para titulares (Georgia/Times, ya que no se
  proporcionó el archivo de la fuente exacta de la web — si Jon la tiene,
  se puede sustituir por la real más adelante)

**En la interfaz (`app/frontend/`):**
- Cabecera con el logo real (`assets/logo_transparent.png`) sobre un fondo
  con la textura de rejilla de la web (`assets/fondo_web.jpg`), franja
  dorada inferior igual que en el logo original.
- Titulares de las tarjetas en tipografía serif con subrayado dorado,
  replicando el estilo del logo.
- Colores de la app actualizados de `#0B1D36` al nuevo `#0F1822`.

**En los PDFs (`app/services/pdf_generator.py`):**
- Nueva cabecera de marca: banner azul marino de ancho completo con el
  logo centrado (mismo archivo que en la web), igual en las 4 plantillas
  (Oferta Cliente, Informe Interno, Oferta de Elemento Individual, Informe
  Interno de Elemento). Función única `_company_header()`, así que
  cualquier cambio de marca futuro se aplica en un solo sitio.
- Titulares en Times-Bold/Times-Italic para que combinen con la serif del
  logo.
- Corregido de paso un fallo de renderizado: "m³/h" no se veía bien con la
  fuente por defecto de reportlab — ahora se escribe "m3/h" en todo el PDF.

Los tres archivos originales que subió Jon están guardados en
`app/assets/` (para los PDFs) y `app/frontend/assets/` (para la web) —
duplicados porque son dos sitios servidos de forma distinta, no porque
haga falta mantenerlos por separado a mano.

**Pendiente si Jon quiere afinar más**: la fuente serif exacta de la web
(si la tienen como archivo .ttf/.otf, se puede incrustar para que sea
idéntica en vez de la aproximación con Georgia/Times), y si hay más
páginas de la web aparte de la que ya se ha usado de referencia.

---

## De la V9: curva de la bomba en la oferta

Añadido sobre la V8 (compatibilidad química): la Oferta Cliente en PDF
incluye ahora la curva caudal/altura de la bomba seleccionada, con el
**punto de trabajo solicitado marcado encima** (`app/services/pump_curve.py`).

**Importante — es una curva ORIENTATIVA, no la real del fabricante**, salvo
para la (todavía muy pequeña) parte del catálogo que tenga informado
`curve_reference_url`. Se genera a partir de los dos datos que sí tenemos
siempre (caudal y altura/presión máximos), con la forma típica de cada
tecnología:
- **Bombas volumétricas** (neumática, peristáltica, tornillo helicoidal,
  engranajes): caudal casi constante frente a la presión (curva casi
  vertical), con una ligera caída por deslizamiento interno al acercarse a
  la presión máxima — así se comportan de verdad este tipo de bombas.
- **Bombas centrífugas**: curva descendente clásica (altura máxima a caudal
  cero, caudal máximo a altura reducida).

Cuando `pump.curve_reference_url` esté informado (curva real localizada,
igual que se hizo con el caudal/potencia/presión bomba a bomba), el PDF
muestra el enlace a la ficha oficial del fabricante junto a la curva. De
momento el catálogo no tiene ninguna URL de curva real cargada — es la
siguiente tarea de investigación pendiente, igual que se hizo con
caudal/potencia/presión.

**Nuevo campo** en `PumpModel`/`SelectedPump`/`pumps_catalog.csv`:
`curve_reference_url` (vacío en todo el catálogo actual).

## Pendiente: logo e identidad visual de la web

Jon va a subir el logo nuevo y los colores/tipografía de la web para
aplicarlos tanto a la interfaz (`app/frontend/index.html`) como a la
cabecera de los PDFs (`app/services/pdf_generator.py`, función
`_company_header`). Sin el archivo del logo y la guía de estilo no se puede
avanzar en esto todavía.

---

## De la V8: compatibilidad química fluido/material

Añadido sobre la V7 (razonamiento de tecnología de bomba): ahora EPi también
comprueba que el fluido a bombear no ataque químicamente el material de la
bomba que va a tocarlo (cuerpo mojado y elastómero/junta).

### Motor de compatibilidad química (`app/engine/chemical_compatibility.py`)

`ChemicalCompatibilityAdvisor` es deliberadamente conservador: si no conoce
el material de la bomba o el fluido no está en su base de conocimiento,
devuelve `compatible=None` ("no se puede confirmar ni descartar, verificar
a mano") en vez de asumir que todo va bien. Cubre los fluidos industriales
más habituales: agua, agua de mar, sosa cáustica, ácido clorhídrico, ácido
sulfúrico, hipoclorito sódico/lejía, disolventes/cetonas/aromáticos, y
aceites minerales/hidrocarburos — con los materiales de cuerpo y elastómero
que cada uno ataca y por qué.

**Dos puntos de uso:**
1. **Antes de elegir bomba** (`bad_materials_for()`): si hay varias bombas
   candidatas dentro de la misma tecnología/caudal/altura/perfil, se
   descartan primero las que tengan un material conocido como incompatible
   con el fluido descrito — salvo que TODAS lo sean, en cuyo caso se sigue
   eligiendo la de mejor puntuación (mejor una bomba con aviso que ninguna).
2. **Después de elegir bomba** (`check()`): genera un
   `ChemicalCompatibilityResult` con el veredicto y los motivos, que llega
   hasta el Informe Interno en PDF, para que el ingeniero lo revise.

### Material de las bombas en el catálogo (`app/db/pumps_catalog.csv`)

Dos columnas nuevas: `wetted_body_material` y `wetted_elastomer_material`.
Cobertura actual: **416/1.509 con material de cuerpo, 357/1.509 con
elastómero** (~27%) — se extrajo por palabras clave de la descripción del
fabricante (SS316, ALUMINIUM, POLYPROPYLENE, EPDM, VITON, SANTOPRENE...) y,
para la serie PD de ARO específicamente, decodificando el propio código de
modelo (patrón confirmado con varias fichas técnicas oficiales de ARO). El
resto de referencias no tiene material identificado — quedan con
`compatible=None` en vez de un falso "compatible".

**IMPORTANTE — revisar antes de producción:** el material de ARO inferido
por código es una deducción de ingeniería razonable para la serie PD, pero
sin confirmación oficial por cada referencia exacta. Antes de prometer
compatibilidad química a un cliente real, verificar con la ficha del
fabricante. Para Verderflex, los materiales de tubo oficiales son NR, NBR,
NBR alimentario, EPDM, CSM/Hypalon y Verderprene (Santoprene) — fuente:
catálogo oficial Verderflex.

### Variable nueva en la entrevista

No hizo falta añadir una pregunta nueva: el fluido (`fluid_name`) ya se
recogía en la V6. La comprobación química se activa automáticamente sobre
ese mismo dato.

### Aviso de pedido oficial en los documentos de cliente

Tanto la Oferta Cliente (`generate_client_offer_pdf`) como la Oferta de
Elemento Individual (`generate_single_item_offer_pdf`) incluyen ahora, al
final del documento: *"En caso de aceptación del presupuesto, envíe el
pedido oficial a pedidos@eficienciayprecisionindustrial.com. Si no recibe
confirmación de la recepción de su pedido, es posible que este no se haya
tramitado."* El mismo aviso se añadió también al cuerpo del email
automático (`app/services/email_service.py`), por coherencia.

---

## De la V7: razonamiento de tecnología de bomba + catálogo real

Hasta la V6, EPi elegía la bomba SOLO por caudal + altura + perfil de
inversión (BARATA/CALIDAD_PRECIO/PREMIUM), sin tener en cuenta el proceso.
Esto podía recomendar, por ejemplo, una bomba de engranajes para un fluido
con sólidos en suspensión — algo que en la práctica destrozaría la bomba.

### 1. Motor de razonamiento de tecnología (`app/engine/pump_technology.py`)

`PumpTechnologyAdvisor` encapsula el criterio de mecánica de fluidos para
decidir qué tecnología(s) de bomba son físicamente aptas ANTES de mirar
precio:

- **Neumática de doble membrana (AODD)**: la más barata, pero la de peor
  eficiencia (aire comprimido). Puede bombear sólidos. Da mucha pulsación —
  no apta si se necesita caudal continuo.
- **Peristáltica**: apta para lodos/abrasivos y fluidos delicados (no daña
  el producto). Pulsación moderada-alta.
- **Tornillo helicoidal**: también apta para lodos/abrasivos, pero con
  MUCHOS MENOS PULSOS que la peristáltica o la neumática — mejor opción si
  además de sólidos se necesita precisión de dosificación.
- **Centrífuga (mecánica o magnética)**: muy buena eficiencia y caudal
  continuo, pero NO apta con sólidos/abrasivos significativos. La versión
  magnética añade estanqueidad total (fugas cero) para fluidos
  tóxicos/corrosivos o ATEX.
- **Engranajes**: muy buena eficiencia y el caudal MÁS CONTINUO de todas —
  ideal para dosificación de precisión de fluidos limpios y viscosos
  (aceites, adhesivos). NO admite sólidos ni fluidos abrasivos.

El motor puntúa las 6 tecnologías y explica, con motivos y avisos en texto,
por qué cada una encaja o no — esa explicación llega hasta el Informe
Interno en PDF (`report.technology_reasoning`), para que el ingeniero de
proyecto pueda revisar y, si hace falta, corregir la elección automática.

**Variables de proceso nuevas** en `HydraulicCalculationRequest`: `has_solids`,
`max_particle_size_mm`, `is_abrasive`, `is_shear_sensitive`,
`requires_continuous_flow`. Ninguna es obligatoria — si el cliente no las
conoce, se asume el caso conservador (sin sólidos, no abrasivo). El agente de
entrevista (`app/agents/interview.py`) las pregunta en un único bloque
conversacional, tanto en modo LLM como en el modo de reglas sin API key.

### 2. Selección de bomba: tecnología primero, precio después

`select_from_db()` en `app/main.py` ya no filtra solo por perfil/caudal/altura:
primero calcula las tecnologías aptas (`PumpTechnologyAdvisor`) y prueba el
catálogo tecnología por tecnología, en orden de puntuación. Si la tecnología
más adecuada no tiene bomba en el perfil de inversión pedido, se relaja el
perfil (nunca la tecnología — esa es una restricción física, no de precio).

### 3. Catálogo real de bombas (`app/db/pumps_catalog.csv`)

Se sustituyen las 6 bombas de ejemplo del seed original por el **catálogo
real de EPi**: 1.509 bombas de 5 fabricantes (ARO, Pompe Cucchi, Sydex,
Verderflex, CDR Pompe), construido a partir de las tarifas 2026 de cada
proveedor y de las fichas técnicas públicas de cada fabricante (ver el
histórico de la conversación de origen para la metodología completa de cada
dato — caudal, potencia, presión, eficiencia). Solo se incluyen las bombas
con caudal verificado; ~550 bombas adicionales de las tarifas originales se
quedaron sin caudal fiable y NO están en este catálogo operativo.

Notas sobre la conversión a `PumpModel` (asunciones a revisar):
- `technology`: asignada por fabricante/familia (ARO → neumática, Cucchi →
  engranajes, Sydex → tornillo helicoidal, Verder → peristáltica, CDR →
  centrífuga mecánica o magnética según familia de modelo).
- `min_flow_m3h`: estimado como un % del caudal máximo (varía por
  tecnología: 5% en neumáticas, 25% en centrífugas), no un dato de catálogo.
- `max_head_m`: convertido desde la presión en bar (bar × 10,19), o un valor
  típico de la tecnología si no había presión.
- `profile` (BARATA/CALIDAD_PRECIO/PREMIUM): asignado por percentil de
  precio DENTRO de cada tecnología (tercios), no es un dato del fabricante.
- `match_score`: la eficiencia real calculada cuando existía, o un valor
  típico de la tecnología en caso contrario.
- Las bombas neumáticas (ARO) tienen `recommended_motor_kw=0.0` — no llevan
  motor eléctrico, se alimentan de aire comprimido.

**Recomendación**: antes de usar esto en producción con clientes reales,
que Matías revise una muestra del CSV — varias de estas asunciones
(perfil por percentil, min_flow por regla general) son razonables pero no
vienen del fabricante.

## Qué venía de la V6 (identificación por foto) — sigue igual

Módulo independiente del stub `/api/v1/photo/redesign` (que rediseña una
instalación completa y sigue sin desarrollar):

1. `POST /api/v1/photo/identify-item` — el cliente sube una foto de UN
   elemento suelto. Llama a Google Cloud Vision API
   (`app/services/vision_service.py`); si `EPI_VISION_API_KEY` no está
   configurada, responde con una identificación de respaldo sin romper el
   flujo.
2. El cliente confirma o corrige el elemento detectado.
3. `POST /api/v1/photo/quote-item` — genera oferta de ese elemento con las
   mismas reglas comerciales (+40% / +38%) que el resto de EPi.

## Qué venía de antes de la V6

1. Sin login obligatorio para el cliente (`/api/v1/interview/chat`,
   `/api/v1/solution/oneshot`, `/api/v1/report/client-pdf` son públicos).
2. Formulario de contacto opcional (`ContactInfo`) — ningún campo obligatorio.
3. Envío automático de la oferta por email si el cliente deja su email.
4. Archivado por empresa/contacto en la tabla `leads`, consultable por el
   personal interno (`GET /api/v1/leads`).
5. El login (JWT) se mantiene solo para el personal interno (admin/engineer).

## Variables de entorno para el envío de email

```
EPI_SMTP_HOST=smtp.tu-proveedor.com
EPI_SMTP_PORT=587
EPI_SMTP_USER=usuario
EPI_SMTP_PASSWORD=contraseña
EPI_SMTP_USE_TLS=true
EPI_MAIL_FROM=epi@eficienciayprecisionindustrial.com
```

Si `EPI_SMTP_HOST` no está configurado, la generación de la oferta sigue
funcionando con normalidad; simplemente no se envía el correo.

**Para que el correo salga como `epi@eficienciayprecisionindustrial.com`**
hace falta darle a EPi una credencial de ENVÍO para esa dirección — pero
esto NO es lo mismo que darle acceso al buzón (leer correo, contactos,
etc.). Opciones, de más sencilla a más recomendable a medio plazo:

1. Crear la cuenta `epi@...` en vuestro proveedor de correo (Google
   Workspace, Microsoft 365...) y generar una "contraseña de aplicación"
   específica para SMTP (no la contraseña normal de acceso al correo).
2. O configurar esa dirección como alias "Enviar como" desde otra cuenta ya
   existente, sin crear un buzón nuevo.
3. O, más robusto para producción, usar un servicio de envío transaccional
   (SendGrid, Mailgun, Amazon SES...): se verifica el dominio una vez
   (registros SPF/DKIM) y se envía "como" `epi@...` sin exponer ninguna
   contraseña de un buzón real, con mejor entregabilidad y sin depender de
   límites de envío de una cuenta de correo normal.

En cualquiera de los tres casos, `EPI_SMTP_USER`/`EPI_SMTP_PASSWORD` son la
credencial de envío, no la de inicio de sesión en el buzón — Matías es
quien debería crearla, dependiendo del proveedor de correo que uséis.

## Puesta en marcha

```bash
pip install -r requirements.txt --break-system-packages
python -m app.db.seed        # carga el catalogo real de 1.509 bombas + usuario admin interno
uvicorn app.main:app --reload
```

La interfaz web queda en `http://localhost:8000/ui/`.

## Nota sobre el margen de contingencia (38%)

El motor comercial (`app/engine/commercial.py`) sigue aplicando el +40%
sobre componentes web y el +38% de contingencia tal como especifica el
dossier. El documento cliente sigue mostrando un precio final único, no un
desglose de "costes reales + recargo oculto" (comentario de transparencia
comercial ya trasladado en la revisión anterior; no es una decisión técnica).
