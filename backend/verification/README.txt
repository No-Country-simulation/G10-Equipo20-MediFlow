Verificación de regresiones MediFlow

Ejecutar:
  docker compose --profile test run --build --rm tests

La suite usa exclusivamente db-test. Cubre extracción por rol y país,
identificaciones multilínea, datos ambiguos, recomendaciones preventivas,
urgencia actual, enrutamiento, contactos y permisos de destinos, y la cola
Slack con transporte simulado (no envía mensajes reales).

Reproducción de un documento almacenado, sin llamadas al modelo:
  docker compose run --rm --no-deps -T \
    -v "$PWD/backend/verification/replay_uploaded_document.py:/tmp/replay_document.py:ro" \
    -e PYTHONPATH=/app api python /tmp/replay_document.py UUID

El comando verifica el SHA-256 y compara el texto con el original en R2.
Con --apply completa una identificación faltante de un documento ya entregado
solo si la repetición del flujo y la evidencia del paciente son válidas.
Conserva el original, el destino, la entrega y todos los resultados previos;
añade una corrección al historial y un nuevo respaldo en R2.

Los diagnósticos operativos se conservan en reportes privados.

Destinos y notificaciones:
- Migraciones 0013 y 0014: webhook por destino y destino de cada aviso en
  la cola Slack. Los emails fueron eliminados de la base, API y formulario.
- /destinations/:code/edit abre el formulario completo.
- GET /destinations/:code requiere DESTINATIONS_MANAGE y no permite caché.
  Las listas y los resultados de documentos no exponen el webhook.
- Al confirmar ENTREGADO / DELIVERED_LOCAL se inserta un aviso DELIVERED en
  la misma transacción. Se cubren procesamiento, recuperación y revisión.
- La restricción documento/nivel evita duplicar registros de entrega al
  repetir la programación. El worker usa el webhook vigente del destino.
- Las alertas urgentes y críticas usan el webhook urgente. Los avisos de
  entrega y revisión usan el webhook específico guardado en cada destino.
  El webhook principal completa únicamente las bandejas sin uno específico.
- La migración 0015 restablece emails por destino y añade una cola SMTP opcional.
  Configuración SMTP, dentro de Variables de Configuración, guarda servidor,
  puerto, seguridad STARTTLS/SSL, usuario, contraseña y remitente. El envío
  permanece desactivado por defecto y requiere activación explícita.
  La contraseña nunca se devuelve en las respuestas de configuración.
  test_email_notifications.py cubre destinatarios, permisos, configuración,
  activación, deduplicación, transporte simulado, errores y reintentos.

Pruebas reales para Colombia (tres archivos):
- fixtures/01_imagenes_escaneado.pdf: PDF sin capa de texto; requiere OCR.
  Informe de resonancia de rodilla -> DIAGNOSTICO_IMAGENES / ENTREGADO.
- fixtures/02_urgencias_ocr.png: imagen; requiere OCR. Orden de laboratorio
  con prioridad explícita urgente -> COLA_URGENCIAS_MEDICAS / ENTREGADO.
- fixtures/03_revision_humana.pdf: texto digital. Fórmula sin frecuencia
  de administración -> REVISION_HUMANA / EN_REVISION_HUMANA.
Los datos personales de estos archivos son sintéticos. No tienen datos reales.

Asociar los webhooks del .env (comando administrativo explícito):
  docker compose run --rm --no-deps -T \
    -v "$PWD/backend/verification:/verification:ro" -e PYTHONPATH=/app \
    api python /verification/configure_slack_inboxes.py
Este comando configura Urgencias con SLACK_WEBHOOK_URL_URGENTE y completa
las bandejas sin webhook con SLACK_WEBHOOK_URL. Conserva los webhooks
específicos guardados por destino y asigna IMAGING_REPORT/ANY a Imágenes.
No se ejecuta al iniciar: las ediciones posteriores desde la interfaz persisten.

Ejecutar las tres pruebas reales (envía mensajes reales a Slack):
  docker compose run --rm --no-deps -T --user "$(id -u):$(id -g)" \
    -v "$PWD/backend/verification:/verification" -e PYTHONPATH=/app \
    api python /verification/run_colombia_acceptance.py \
    /verification/fixtures /verification/results/colombia-live.json
Comprueba país CO, OCR, identificación del paciente, campos, prioridad, destino,
estado, visibilidad en la bandeja, avisos SENT y originales/respaldo en R2.
Los ID se guardan en el reporte y se reutilizan al repetir el comando.
Para nuevas cargas intencionales se debe indicar un archivo de reporte nuevo.

Diseño de los avisos Slack:
- Block Kit con título, archivo original, bandeja, estado, prioridad, país,
  tipo documental, ID, hora UTC y botón para abrir el documento.
- La revisión muestra motivos legibles; la alerta inicial de urgencia indica
  que el procesamiento sigue en curso, sin anticipar la entrega.
- <!channel> es la mención explícita de Slack para todos los miembros del
  canal. Los nombres de archivo se muestran como texto literal para evitar
  menciones o formato involuntarios procedentes del documento.
- results/colombia-slack-blocks.json registra una nueva ejecución de las tres
  cargas con este diseño, sus avisos reales y las verificaciones de R2.
  Se descargan y comparan tanto los originales (SHA-256) como los respaldos
  JSON; no se comprueba únicamente el estado SYNCED en la base de datos.
