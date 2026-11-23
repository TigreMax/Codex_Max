---
name: transcribir
description: Úsala cuando el jefe pida pasar un audio o un video a texto (transcribir, transcripción, "pásalo a texto", un curso, una reunión, una llamada). Usa Whisper local con la tarjeta de video; nada sale de la computadora.
---
# transcribir

Herramienta: `D:\Codex_Max\codexmax\herramientas\transcribir.py`. Todo se hace en la computadora del jefe: el audio no se manda a ninguna IA ni a internet.

## Antes de empezar
- Confirma la ruta exacta del archivo (audio o video). Compruébala: lista la carpeta y mira que exista; no la supongas.
- Si es material de una empresa, el `.txt` queda **junto al original**. Si el jefe lo pide en otra carpeta, se hace como él dice.

## Pasos
1. Corre (con la ruta entre comillas):
   `D:\Cortex_externas\whisper_env\Scripts\python.exe D:\Codex_Max\codexmax\herramientas\transcribir.py "<ruta del audio o video>"`
   Opciones: `--modelo large-v3|medium|tiny` (por defecto `large-v3`; los tres ya están descargados), `--idioma es` (por defecto detecta solo), `--cpu` (fuerza el procesador).
2. Va mostrando el avance y guarda `<mismo nombre>.txt` junto al archivo, con la hora `[hh:mm:ss]` de cada frase.
3. Si dice **"NO SE PUDO USAR LA TARJETA DE VIDEO"**, sigue con el procesador (mucho más lento). Avísale al jefe con el motivo.
4. Al terminar, abre el `.txt` y comprueba que existe, que se lee bien y que dice con qué hizo el trabajo ("tarjeta de video" o "procesador").
5. Dile al jefe dónde quedó el `.txt` y cuánto tardó. Aclara que los nombres propios y las cifras pueden traer errores: lo importante se compara contra el audio antes de usarlo como dato.

## Si algo falla
- **No existe el entorno `whisper_env`:** no lo instales tú; díselo al jefe.
- **`cublas64_12.dll is not found`:** faltan las librerías de NVIDIA del entorno; reporta el mensaje exacto al jefe.
- **Un audio largo** puede tardar bastante con el procesador. Avisa antes de dejarlo corriendo.

## Cómo saber que quedó bien
- El `.txt` está junto al original, legible, con horas, y sin cortarse a la mitad.

## Qué nunca se hace
- Mandar el audio o su texto a un servicio de internet para transcribirlo.
- Instalar programas o librerías sin permiso del jefe.
- Dar por correcto un nombre o una cifra sin compararlo contra el audio.
