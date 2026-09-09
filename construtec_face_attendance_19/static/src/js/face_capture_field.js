/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, useRef, onWillUnmount } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { imageUrl } from "@web/core/utils/urls";
import { isBinarySize } from "@web/core/utils/binary";
import { fileTypeMagicWordMap } from "@web/views/fields/image/image_field";
import { ensureModelsLoaded, getFaceDescriptor } from "@construtec_face_attendance_19/js/face_api_loader";

class FaceCaptureDialog extends Component {
    static template = "construtec_face_attendance_19.FaceCaptureDialog";
    static components = { Dialog };
    static props = ["close", "onCaptured", "poseLabel"];

    setup() {
        this.video = useRef("video");
        this.fileInput = useRef("fileInput");
        this.state = useState({ loading: true, error: null, processingFile: false });
        this.stream = null;
        onWillUnmount(() => this.stopStream());
        this.start();
    }

    async start() {
        try {
            await ensureModelsLoaded();
            this.stream = await navigator.mediaDevices.getUserMedia({ video: true });
            const video = this.video.el;
            video.srcObject = this.stream;
            await new Promise((resolve) => {
                video.onloadedmetadata = () => video.play().then(resolve);
            });
            this.state.loading = false;
        } catch (error) {
            console.error("No se pudo iniciar la cámara:", error);
            this.state.error = _t("No se pudo acceder a la cámara.");
            this.state.loading = false;
        }
    }

    stopStream() {
        if (this.stream) {
            this.stream.getTracks().forEach((track) => track.stop());
            this.stream = null;
        }
    }

    async capture() {
        const video = this.video.el;
        if (!video || !video.videoWidth) {
            this.state.error = _t("La cámara todavía no está lista, esperá un segundo.");
            return;
        }
        const descriptor = await getFaceDescriptor(video);
        if (!descriptor) {
            this.state.error = _t("No se detectó un rostro. Encuadrá tu cara y probá de nuevo.");
            return;
        }
        const canvas = document.createElement("canvas");
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        canvas.getContext("2d").drawImage(video, 0, 0);
        const base64 = canvas.toDataURL("image/jpeg", 0.9).split(",")[1];

        this.props.onCaptured(base64, descriptor);
        this.stopStream();
        this.props.close();
    }

    triggerFileUpload() {
        this.state.error = null;
        this.fileInput.el.click();
    }

    async onFileSelected(ev) {
        const file = ev.target.files && ev.target.files[0];
        ev.target.value = "";
        if (!file) {
            return;
        }
        this.state.processingFile = true;
        this.state.error = null;
        try {
            const dataUrl = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result);
                reader.onerror = () => reject(reader.error);
                reader.readAsDataURL(file);
            });
            const img = new Image();
            await new Promise((resolve, reject) => {
                img.onload = () => resolve();
                img.onerror = () => reject(new Error("invalid image"));
                img.src = dataUrl;
            });
            const descriptor = await getFaceDescriptor(img);
            if (!descriptor) {
                this.state.error = _t("No se detectó un rostro en esa foto. Probá con otra.");
                return;
            }
            const base64 = dataUrl.split(",")[1];
            this.props.onCaptured(base64, descriptor);
            this.stopStream();
            this.props.close();
        } catch (error) {
            console.error("No se pudo procesar la imagen subida:", error);
            this.state.error = _t("No se pudo leer esa imagen. Probá con otro archivo.");
        } finally {
            this.state.processingFile = false;
        }
    }
}

export class FaceCaptureField extends Component {
    static template = "construtec_face_attendance_19.FaceCaptureField";
    static props = {
        ...standardFieldProps,
        pose: { type: String, optional: true },
        descriptorField: { type: String, optional: true },
    };

    setup() {
        this.dialogService = useService("dialog");
    }

    /** Fuente real para el <img>: hay que resolverla igual que el widget
     * stock de imagen (ImageField) - un record ya guardado NO trae el
     * base64 en record.data (el ORM devuelve un tamaño tipo "5.2 Kb" en su
     * lugar, por rendimiento), hay que pedirlo por la URL /web/image/... En
     * cambio, apenas capturada (antes de guardar) sí es base64 real, y ahí
     * hay que detectar el tipo real de imagen (siempre JPEG acá) en vez de
     * asumir PNG - si no, el navegador puede no mostrar la miniatura. */
    get imageSrc() {
        const value = this.props.record.data[this.props.name];
        if (!value) {
            return null;
        }
        if (isBinarySize(value)) {
            const record = this.props.record;
            return imageUrl(record.resModel, record.resId, this.props.name, {
                unique: record.data.write_date,
            });
        }
        const magic = fileTypeMagicWordMap[value[0]] || "jpg";
        return `data:image/${magic};base64,${value}`;
    }

    get isCaptured() {
        return !!this.props.record.data[this.props.descriptorField];
    }

    openCapture() {
        this.dialogService.add(FaceCaptureDialog, {
            poseLabel: this.props.pose,
            onCaptured: (base64, descriptor) => {
                this.props.record.update({
                    [this.props.name]: base64,
                    [this.props.descriptorField]: descriptor,
                });
            },
        });
    }
}

export const faceCaptureField = {
    component: FaceCaptureField,
    supportedTypes: ["binary"],
    extractProps: ({ options }) => ({
        pose: options.pose || "",
        descriptorField: options.descriptor_field,
    }),
};

registry.category("fields").add("construtec_face_capture", faceCaptureField);
