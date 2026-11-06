/** @odoo-module **/
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onMounted, onWillStart, onWillUnmount, useEffect, useRef } from "@odoo/owl";

const LEAFLET_CSS = "/construtec_analytic_geo_19/static/src/lib/leaflet/leaflet.css";
const LEAFLET_JS = "/construtec_analytic_geo_19/static/src/lib/leaflet/leaflet.js";
let leafletPromise = null;

function ensureLeaflet() {
    if (window.L) {
        return Promise.resolve();
    }
    if (!leafletPromise) {
        leafletPromise = new Promise((resolve, reject) => {
            const link = document.createElement("link");
            link.rel = "stylesheet";
            link.href = LEAFLET_CSS;
            document.head.appendChild(link);
            const script = document.createElement("script");
            script.src = LEAFLET_JS;
            script.onload = () => resolve();
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    return leafletPromise;
}

// Centro por defecto: Guatemala.
const DEFAULT_CENTER = [15.4, -90.4];

export class GeoMapField extends Component {
    static template = "construtec_analytic_geo_19.GeoMapField";
    static props = { ...standardFieldProps };

    setup() {
        this.mapRef = useRef("map");
        this.map = null;
        this.marker = null;
        onWillStart(() => ensureLeaflet());
        onMounted(() => this.initMap());
        onWillUnmount(() => {
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });
        useEffect(
            () => this.syncMarker(),
            () => [this.lat, this.lng]
        );
    }

    get lat() {
        return this.props.record.data.geo_latitude || 0;
    }
    get lng() {
        return this.props.record.data.geo_longitude || 0;
    }
    get hasPoint() {
        return Boolean(this.lat || this.lng);
    }

    initMap() {
        const L = window.L;
        this.map = L.map(this.mapRef.el).setView(
            this.hasPoint ? [this.lat, this.lng] : DEFAULT_CENTER,
            this.hasPoint ? 15 : 7
        );
        // Sin API key: calles (OpenStreetMap) y satélite (Esri World Imagery), con selector.
        const calles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: "&copy; OpenStreetMap",
        });
        const satelite = L.tileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            { maxZoom: 19, attribution: "Imágenes &copy; Esri, Maxar, Earthstar Geographics" }
        );
        calles.addTo(this.map);
        L.control.layers({ Calles: calles, Satélite: satelite }).addTo(this.map);
        if (!this.props.readonly) {
            this.map.on("click", (ev) => this.setPoint(ev.latlng.lat, ev.latlng.lng));
        }
        this.syncMarker();
        // El contenedor puede montarse oculto: recalcular el tamaño.
        setTimeout(() => this.map && this.map.invalidateSize(), 200);
    }

    syncMarker() {
        if (!this.map) {
            return;
        }
        const L = window.L;
        if (!this.hasPoint) {
            if (this.marker) {
                this.marker.remove();
                this.marker = null;
            }
            return;
        }
        const pos = [this.lat, this.lng];
        if (!this.marker) {
            this.marker = L.marker(pos, { draggable: !this.props.readonly }).addTo(this.map);
            this.marker.on("dragend", () => {
                const p = this.marker.getLatLng();
                this.setPoint(p.lat, p.lng);
            });
            this.map.setView(pos, Math.max(this.map.getZoom(), 15));
        } else {
            this.marker.setLatLng(pos);
        }
    }

    setPoint(lat, lng) {
        this.props.record.update({
            geo_latitude: Number(lat.toFixed(7)),
            geo_longitude: Number(lng.toFixed(7)),
        });
    }

    openStreetView() {
        // URL oficial de Google Maps (no requiere key): abre Street View en esa coordenada.
        window.open(
            `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${this.lat},${this.lng}`,
            "_blank",
            "noopener"
        );
    }

    useMyLocation() {
        if (!navigator.geolocation) {
            return;
        }
        navigator.geolocation.getCurrentPosition((pos) => {
            this.setPoint(pos.coords.latitude, pos.coords.longitude);
            if (this.map) {
                this.map.setView([pos.coords.latitude, pos.coords.longitude], 16);
            }
        });
    }
}

registry.category("fields").add("construtec_geo_map", {
    component: GeoMapField,
    supportedTypes: ["char"],
});
