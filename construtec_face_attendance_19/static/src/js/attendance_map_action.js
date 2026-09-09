/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { deserializeDateTime } from "@web/core/l10n/dates";

/** El servidor manda `datetime` en UTC crudo (mismo criterio que el resto de
 * este módulo, ver `formatMarkDatetime` en attendance_menu_patch.js) - hay que
 * convertirlo a la zona horaria del usuario antes de mostrarlo, si no el popup
 * del mapa muestra la hora UTC en vez de la hora local real del marcaje. */
function formatPointDatetime(value) {
    try {
        return deserializeDateTime(value).toFormat("dd/MM/yyyy HH:mm");
    } catch {
        return value;
    }
}

const LEAFLET_CSS = "/construtec_face_attendance_19/static/src/lib/leaflet/leaflet.css";
const LEAFLET_JS = "/construtec_face_attendance_19/static/src/lib/leaflet/leaflet.js";

let leafletLoadPromise = null;

function ensureLeafletLoaded() {
    if (window.L) {
        return Promise.resolve();
    }
    if (!leafletLoadPromise) {
        leafletLoadPromise = new Promise((resolve, reject) => {
            const link = document.createElement("link");
            link.rel = "stylesheet";
            link.href = LEAFLET_CSS;
            document.head.appendChild(link);

            const script = document.createElement("script");
            script.src = LEAFLET_JS;
            script.onload = () => resolve();
            script.onerror = (err) => reject(err);
            document.head.appendChild(script);
        });
    }
    return leafletLoadPromise;
}

// Un color fijo por colaborador (se repite si hay más colaboradores que colores).
const COLORS = ["#e53935", "#1e88e5", "#43a047", "#fb8c00", "#8e24aa", "#00897b", "#d81b60", "#3949ab"];

export class ConstrutecAttendanceMapAction extends Component {
    static template = "construtec_face_attendance_19.AttendanceMapAction";
    static props = ["*"];

    setup() {
        this.mapContainer = useRef("mapContainer");
        this.state = useState({ loading: true, error: null, pointCount: 0, employees: [] });
        this.map = null;

        onWillStart(() => ensureLeafletLoaded());
        onMounted(() => this.renderMap());
        onWillUnmount(() => {
            if (this.map) {
                this.map.remove();
                this.map = null;
            }
        });
    }

    async renderMap() {
        const params = (this.props.action && this.props.action.params) || {};
        let result;
        try {
            result = await rpc("/construtec_face_attendance/map_data", {
                date_from: params.date_from,
                date_to: params.date_to,
                employee_ids: params.employee_ids || [],
            });
        } catch (error) {
            console.error("No se pudo cargar el mapa de marcajes:", error);
            this.state.error = "No se pudieron cargar los marcajes.";
            this.state.loading = false;
            return;
        }

        if (result.error) {
            this.state.error = result.error;
            this.state.loading = false;
            return;
        }

        const points = result.points || [];
        this.state.loading = false;
        this.state.pointCount = points.length;

        const map = window.L.map(this.mapContainer.el).setView([0, 0], 2);
        this.map = map;
        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>',
            maxZoom: 19,
        }).addTo(map);

        if (!points.length) {
            return;
        }

        const employeeColors = {};
        const employeeNames = {};
        let colorIndex = 0;
        const bounds = [];

        for (const point of points) {
            if (!(point.employee_id in employeeColors)) {
                employeeColors[point.employee_id] = COLORS[colorIndex % COLORS.length];
                employeeNames[point.employee_id] = point.employee_name;
                colorIndex++;
            }
            const color = employeeColors[point.employee_id];
            const marker = window.L.circleMarker([point.latitude, point.longitude], {
                radius: 8,
                color,
                fillColor: color,
                fillOpacity: 0.85,
                weight: 2,
            }).addTo(map);
            marker.bindPopup(
                `<strong>${point.employee_name}</strong><br/>${point.label}<br/>${formatPointDatetime(point.datetime)}`
            );
            bounds.push([point.latitude, point.longitude]);
        }

        this.state.employees = Object.keys(employeeColors).map((id) => ({
            id,
            name: employeeNames[id],
            color: employeeColors[id],
        }));

        map.fitBounds(bounds, { padding: [30, 30] });
    }
}

registry.category("actions").add("construtec_attendance_map", ConstrutecAttendanceMapAction);
