/** @odoo-module **/

// Motor de reconocimiento facial compartido: face-api.js corre 100% en el
// navegador (TensorFlow.js + modelos pre-entrenados incluidos en este
// módulo, servidos como archivos estáticos comunes) — sin tokens, sin cuentas
// ni llamadas a ningún servicio de IA de terceros.

const MODEL_URL = "/construtec_face_attendance_19/static/src/js/weights";
let modelsLoadedPromise = null;

async function ensureFaceApiLoaded() {
    if (window.faceapi) {
        return;
    }
    await new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "/construtec_face_attendance_19/static/src/js/face-api.min.js";
        script.onload = () => resolve();
        script.onerror = (err) => reject(err);
        document.head.appendChild(script);
    });
}

export async function ensureModelsLoaded() {
    if (!modelsLoadedPromise) {
        await ensureFaceApiLoaded();
        modelsLoadedPromise = Promise.all([
            window.faceapi.nets.ssdMobilenetv1.loadFromUri(MODEL_URL),
            window.faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
            window.faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
            window.faceapi.nets.faceRecognitionNet.loadFromUri(MODEL_URL),
        ]).catch((err) => {
            modelsLoadedPromise = null;
            throw err;
        });
    }
    return modelsLoadedPromise;
}

/**
 * Devuelve la huella facial (128 números) detectada en una imagen/video, o
 * null si no se detectó ningún rostro (o si falló la GPU al procesarlo -
 * ver nota abajo, se trata igual que "no detectado" para que el que llama
 * simplemente reintente en vez de explotar con una excepción sin atrapar).
 *
 * `preferLight`: usar primero TinyFaceDetector (mucho más liviano en GPU)
 * en vez de SsdMobilenetv1 (más preciso pero pesado). Para video en vivo
 * frame-a-frame esto es obligatorio - correr el detector pesado en cada
 * frame sin límite es lo que agota la GPU en teléfonos más modestos y
 * termina en "Failed to compile fragment shader" (WebGL sin contexto). Para
 * una sola foto fija (enrolamiento) sí conviene el detector pesado, ya que
 * ahí la precisión importa más que la velocidad y solo se corre una vez.
 */
export async function getFaceDescriptor(mediaElement, { preferLight = false } = {}) {
    await ensureModelsLoaded();

    const primaryDetector = () => (
        preferLight
            ? window.faceapi.detectSingleFace(mediaElement, new window.faceapi.TinyFaceDetectorOptions())
            : window.faceapi.detectSingleFace(mediaElement)
    );
    const fallbackDetector = () => (
        preferLight
            ? window.faceapi.detectSingleFace(mediaElement)
            : window.faceapi.detectSingleFace(mediaElement, new window.faceapi.TinyFaceDetectorOptions())
    );

    try {
        let detection = await primaryDetector().withFaceLandmarks().withFaceDescriptor();
        if (!detection) {
            detection = await fallbackDetector().withFaceLandmarks().withFaceDescriptor();
        }
        return detection ? Array.from(detection.descriptor) : null;
    } catch (error) {
        // Errores de GPU/WebGL (shader que no compiló, contexto perdido,
        // etc.) no deberían tirar abajo todo el flujo de verificación - se
        // registran y se trata como "no se detectó nada en este frame",
        // dejando que el que llama reintente en el próximo.
        console.error("face-api: fallo al procesar el frame (¿problema de GPU/WebGL?):", error);
        return null;
    }
}
