/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ActivityMenu } from "@hr_attendance/components/attendance_menu/attendance_menu";
import { useState, onWillStart, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { ensureModelsLoaded, getFaceDescriptor } from "@construtec_face_attendance_19/js/face_api_loader";

// Cuántos frames sin match/detección se aceptan antes de abandonar el intento.
const MAX_ATTEMPTS = 90;

// Debe coincidir con COOLDOWN_MINUTES del controlador (controllers/main.py) -
// esto es solo un adelanto de UX (evita abrir la cámara para nada); el
// servidor es quien realmente lo hace cumplir.
const COOLDOWN_MINUTES = 15;

// Cada cuánto se manda un ping de ubicación automático mientras el empleado
// está fichado. Límite real e insalvable: solo funciona con la pestaña/app
// en primer plano (visible) - apenas se bloquea el teléfono o se cambia de
// app, el navegador deja de entregar ubicación, no hay forma de saltear eso
// desde una PWA (haría falta una app nativa con permiso de ubicación en
// segundo plano, que es un proyecto aparte).
const LOCATION_PING_INTERVAL_MS = 15 * 60 * 1000;

const MARK_BUTTONS = [
    { markType: "inicio_labores", label: _t("Inicio de Labores / Hora Extra"), icon: "fa-sign-in", cls: "success" },
    { markType: "inicio_alimentacion", label: _t("Inicio de Alimentación"), icon: "fa-cutlery", cls: "info" },
    { markType: "fin_alimentacion", label: _t("Fin de Alimentación"), icon: "fa-cutlery", cls: "info" },
    { markType: "fin_labores", label: _t("Fin de Labores / Hora Extra"), icon: "fa-sign-out", cls: "warning" },
];

patch(ActivityMenu.prototype, {
    setup() {
        super.setup(...arguments);
        this.faceNotification = useService("notification");
        this.faceCheckActive = false;
        this.faceStream = null;
        this.faceAttempts = 0;
        this.faceLastMarkAt = {}; // markType -> epoch ms, del propio navegador (adelanto de UX)
        this.markButtons = MARK_BUTTONS;
        this.faceRecentMarks = useState({ items: [], loading: false });
        this.faceOptions = useState({ analyticAccounts: [] });

        onWillStart(async () => {
            await Promise.all([
                this.loadRecentMarks(),
                this.loadAnalyticAccounts(),
            ]);
        });

        // Ping de ubicación automático - revisa cada LOCATION_PING_INTERVAL_MS
        // si corresponde mandar uno (solo si está fichado y la pestaña está
        // visible en ese momento). El systray vive durante toda la sesión,
        // así que un solo intervalo arrancado acá alcanza, no hace falta
        // reiniciarlo en cada check-in/check-out.
        this.locationPingTimer = setInterval(() => this.maybeSendLocationPing(), LOCATION_PING_INTERVAL_MS);
        onWillUnmount(() => clearInterval(this.locationPingTimer));
    },

    /** Ver LOCATION_PING_INTERVAL_MS: no hay forma de que esto funcione con
     * la app en segundo plano o el teléfono bloqueado - limitación real del
     * navegador, no algo que se pueda evitar desde acá. */
    maybeSendLocationPing() {
        if (!this.state.checkedIn) {
            return;
        }
        if (document.visibilityState !== "visible") {
            return;
        }
        if (!navigator.geolocation || !navigator.onLine) {
            return;
        }
        navigator.geolocation.getCurrentPosition(
            ({ coords: { latitude, longitude } }) => {
                rpc("/construtec_face_attendance/location_ping", { latitude, longitude }).catch((error) => {
                    console.error("No se pudo mandar el ping de ubicación:", error);
                });
            },
            (error) => {
                console.error("No se pudo obtener ubicación para el ping automático:", error);
            },
            { enableHighAccuracy: false, timeout: 10000 }
        );
    },

    async loadRecentMarks() {
        this.faceRecentMarks.loading = true;
        try {
            const marks = await rpc("/construtec_face_attendance/recent_marks");
            this.faceRecentMarks.items = marks;
        } catch (error) {
            console.error("No se pudieron cargar los marcajes recientes:", error);
        } finally {
            this.faceRecentMarks.loading = false;
        }
    },

    async loadAnalyticAccounts() {
        try {
            this.faceOptions.analyticAccounts = await rpc("/construtec_face_attendance/analytic_accounts");
        } catch (error) {
            console.error("No se pudieron cargar las cuentas analíticas:", error);
        }
    },

    /** @override
     * Es el beforeOpen del Dropdown (ver hr_attendance.attendance_menu):
     * se dispara cada vez que se abre el panel. Además de lo que ya hacía
     * (refrescar horas/estado), recargamos cuentas/marcajes acá para que no
     * haga falta recargar toda la página para ver un marcaje reciente nuevo.
     */
    async searchReadEmployee() {
        await super.searchReadEmployee();
        await Promise.all([
            this.loadAnalyticAccounts(),
            this.loadRecentMarks(),
        ]);
    },

    formatMarkDatetime(value) {
        try {
            return deserializeDateTime(value).toFormat("dd/MM HH:mm");
        } catch {
            return value;
        }
    },

    /** Minutos que faltan para poder repetir este marcaje, o 0 si ya se puede. */
    cooldownRemaining(markType) {
        const last = this.faceLastMarkAt[markType];
        if (!last) {
            return 0;
        }
        const elapsedMin = (Date.now() - last) / 60000;
        return Math.max(0, Math.ceil(COOLDOWN_MINUTES - elapsedMin));
    },

    /** @override de signInOut original: ya no se usa, cada botón llama a onMarkClick. */
    async onMarkClick(markType) {
        if (this._attendanceInProgress) {
            return;
        }
        const remaining = this.cooldownRemaining(markType);
        if (remaining > 0) {
            const button = this.markButtons.find((b) => b.markType === markType);
            this.faceNotification.add(
                _t("Ya marcaste \"%(label)s\" hace poco. Esperá %(min)s minuto(s) más.", {
                    label: button ? button.label : markType,
                    min: remaining,
                }),
                { title: _t("Asistencia"), type: "warning" }
            );
            return;
        }
        // Los campos (cuenta analítica/observaciones) viven en el dropdown
        // que estamos por cerrar, así que hay que leerlos ANTES - una vez
        // cerrado, ese contenido se desmonta y ya no se puede leer.
        const analyticSelect = document.getElementById("ConstrutecAnalyticSelect");
        const observacionesEl = document.getElementById("ConstrutecObservaciones");
        this.faceCurrentAnalyticId = analyticSelect && analyticSelect.value ? parseInt(analyticSelect.value, 10) : false;
        this.faceCurrentObservaciones = observacionesEl ? observacionesEl.value.trim() : "";

        this.dropdown.close();
        this._attendanceInProgress = true;
        try {
            await this.openFaceVerificationModal(markType);
        } catch (error) {
            console.error("Face verification flow error:", error);
            this._attendanceInProgress = false;
        }
    },

    getFaceModal() {
        return document.getElementById("ConstrutecFaceModal");
    },

    setFaceStatus(modal, text) {
        const status = modal.querySelector("#ConstrutecFaceStatus");
        if (status) {
            status.textContent = text;
        }
    },

    setFaceLive(modal, isLive) {
        const dot = modal.querySelector("#ConstrutecFaceLiveDot");
        if (dot) {
            dot.style.display = isLive ? "flex" : "none";
        }
    },

    async openFaceVerificationModal(markType) {
        const modal = this.getFaceModal();
        if (!modal) {
            this._attendanceInProgress = false;
            this.faceNotification.add(
                _t("No se encontró el panel de verificación facial."),
                { type: "danger" }
            );
            return;
        }

        this.faceCurrentMarkType = markType;
        const button = this.markButtons.find((b) => b.markType === markType);
        modal.querySelector("#ConstrutecFaceModalTitle").textContent = button ? button.label : "";

        modal.style.display = "block";
        this.faceAttempts = 0;
        this.setFaceLive(modal, false);
        this.setFaceStatus(modal, _t("Iniciando…"));

        try {
            await this.startFaceCheck(modal);
        } catch (error) {
            console.error("No se pudo iniciar la verificación facial:", error);
            this.faceNotification.add(
                _t("No se pudo iniciar la verificación facial."),
                { type: "danger" }
            );
            this.closeFaceModal(modal);
        }
    },

    async startFaceCheck(modal) {
        const video = modal.querySelector("#construtec_face_video");
        this.setFaceStatus(modal, _t("Cargando sistema de reconocimiento…"));
        try {
            await ensureModelsLoaded();
        } catch (error) {
            this.faceNotification.add(
                _t("No se pudo cargar el sistema de reconocimiento facial. Recargá la página."),
                { type: "danger" }
            );
            this.closeFaceModal(modal);
            return;
        }
        if (!window.isSecureContext) {
            this.faceNotification.add(
                _t("La cámara requiere una conexión segura (HTTPS)."),
                { type: "danger" }
            );
            this.closeFaceModal(modal);
            return;
        }

        this.setFaceStatus(modal, _t("Solicitando acceso a la cámara…"));
        this.faceCheckActive = true;
        let stream;
        try {
            stream = await navigator.mediaDevices.getUserMedia({ video: true });
        } catch (error) {
            this.faceNotification.add(
                _t("No se pudo acceder a la cámara. Revisá los permisos del navegador."),
                { type: "danger" }
            );
            this.closeFaceModal(modal);
            return;
        }
        if (!this.faceCheckActive) {
            stream.getTracks().forEach((track) => track.stop());
            return;
        }
        this.faceStream = stream;
        video.srcObject = stream;
        await new Promise((resolve) => {
            video.onloadedmetadata = () => video.play().then(resolve);
        });
        this.setFaceLive(modal, true);
        this.setFaceStatus(modal, _t("Buscando tu rostro…"));
        this.processFaceFrame(modal, video);
    },

    /** Espera antes del próximo intento de detección - correr el detector en
     * cada frame de video (~60/seg) sin límite es lo que satura la GPU en
     * teléfonos más modestos y termina en errores de WebGL ("Failed to
     * compile fragment shader") o el celular trabándose. Unas pocas
     * detecciones por segundo alcanzan de sobra para esto. */
    scheduleNextFaceFrame(modal, video) {
        this.faceFrameTimer = setTimeout(() => this.processFaceFrame(modal, video), 300);
    },

    async processFaceFrame(modal, video) {
        if (!this.faceCheckActive) {
            return;
        }
        if (!video.videoWidth) {
            requestAnimationFrame(() => this.processFaceFrame(modal, video));
            return;
        }

        // preferLight: en el loop en vivo se prioriza el detector más
        // liviano (TinyFaceDetector) por sobre el más preciso pero pesado
        // (SsdMobilenetv1) - ver face_api_loader.js.
        const descriptor = await getFaceDescriptor(video, { preferLight: true });
        if (!this.faceCheckActive) {
            return;
        }

        if (!descriptor) {
            this.setFaceStatus(modal, _t("No se detecta tu rostro. Encuadrá tu cara con la cámara…"));
            if (!this.bumpFaceAttempts(modal, _t("No se detectó tu rostro. Encuadrá tu cara con la cámara."))) {
                this.scheduleNextFaceFrame(modal, video);
            }
            return;
        }

        this.setFaceStatus(modal, _t("Verificando…"));
        let result;
        try {
            result = await rpc("/construtec_face_attendance/verify", { descriptor });
        } catch (error) {
            console.error("Verify RPC failed:", error);
            this.faceNotification.add(_t("Error al verificar el rostro."), { type: "danger" });
            this.closeFaceModal(modal);
            return;
        }

        if (result && result.allow) {
            this.faceCheckActive = false;
            this.setFaceLive(modal, false);
            this.setFaceStatus(modal, _t("¡Rostro verificado! Registrando…"));
            await this.confirmMark(modal);
            return;
        }

        this.setFaceStatus(modal, _t("Rostro no reconocido, seguimos intentando…"));
        const message = (result && result.error) || _t("No se pudo reconocer tu rostro.");
        if (!this.bumpFaceAttempts(modal, message)) {
            this.scheduleNextFaceFrame(modal, video);
        }
    },

    /** Devuelve true si se alcanzó el límite de intentos y se cerró el modal. */
    bumpFaceAttempts(modal, message) {
        this.faceAttempts++;
        if (this.faceAttempts >= MAX_ATTEMPTS) {
            this.faceNotification.add(message, { title: _t("Verificación facial"), type: "danger" });
            this.closeFaceModal(modal);
            return true;
        }
        return false;
    },

    async confirmMark(modal) {
        const markType = this.faceCurrentMarkType;
        const button = this.markButtons.find((b) => b.markType === markType);
        const analyticAccountId = this.faceCurrentAnalyticId;
        const observaciones = this.faceCurrentObservaciones;
        // No reseteamos _attendanceInProgress acá: lo hace el finally de
        // doMark más abajo, para no dejar una ventana en la que un doble
        // click abra un segundo modal mientras el marcaje todavía viaja.
        this.closeFaceModal(modal, { resetProgress: false });

        const trackingEnabled = this.employee && this.employee.device_tracking_enabled;
        const doMark = async (latitude = false, longitude = false) => {
            try {
                const result = await rpc("/construtec_face_attendance/mark", {
                    mark_type: markType,
                    latitude,
                    longitude,
                    analytic_account_id: analyticAccountId,
                    observaciones,
                });
                if (!result || !result.ok) {
                    this.faceNotification.add(
                        (result && result.error) || _t("No se pudo registrar el marcaje."),
                        { title: _t("Asistencia"), type: "danger" }
                    );
                    return;
                }
                this.employee = result;
                this._searchReadEmployeeFill();
                this.faceLastMarkAt[markType] = Date.now();
                this.faceNotification.add(
                    _t("%(label)s registrado correctamente.", { label: button ? button.label : markType }),
                    { title: _t("Asistencia"), type: "success" }
                );
                await this.loadRecentMarks();
            } catch (error) {
                console.error("Mark failed:", error);
                this.faceNotification.add(
                    (error && error.message) || _t("No se pudo registrar el marcaje."),
                    { title: _t("Asistencia"), type: "danger" }
                );
            } finally {
                this._attendanceInProgress = false;
            }
        };

        if (trackingEnabled && navigator.geolocation && navigator.onLine) {
            navigator.geolocation.getCurrentPosition(
                ({ coords: { latitude, longitude } }) => doMark(latitude, longitude),
                () => doMark(),
                { enableHighAccuracy: true, timeout: 10000 }
            );
        } else {
            await doMark();
        }
    },

    closeFaceModal(modal, { resetProgress = true } = {}) {
        this.faceCheckActive = false;
        if (this.faceFrameTimer) {
            clearTimeout(this.faceFrameTimer);
            this.faceFrameTimer = null;
        }
        if (this.faceStream) {
            this.faceStream.getTracks().forEach((track) => track.stop());
            this.faceStream = null;
        }
        const video = modal.querySelector("#construtec_face_video");
        if (video) {
            video.srcObject = null;
        }
        modal.style.display = "none";
        if (resetProgress) {
            this._attendanceInProgress = false;
        }
    },

    onCancelFaceCheck() {
        const modal = this.getFaceModal();
        if (modal) {
            this.closeFaceModal(modal);
        }
    },
});
