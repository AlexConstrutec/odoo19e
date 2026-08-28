# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
"""Thin client for Meta's WhatsApp Business Cloud API - **template messages only**, never free
text. Any business-initiated message outside a 24h customer-service window (exactly what a
notification triggered by "Enviar" on an Orden de Pago is) requires a pre-approved Meta template
- there is no free-text path here on purpose, to avoid building something that looks like it
works in testing (replying to your own message within 24h) and then silently violates policy /
gets rejected in real use.

Deliberately generic (explicit scalar args, not an ORM object) - same pattern as
`construtec_account_payment_order_19/tools/enterprise_sync_api.py` in the sibling module this
one depends on - so it's easy to unit test without a live Meta account, and easy for another
module to call without importing anything company-specific.
"""
import logging
import re

import requests

_logger = logging.getLogger(__name__)

GRAPH_API_MESSAGES_URL = 'https://graph.facebook.com/{version}/{phone_number_id}/messages'
GRAPH_API_PHONE_URL = 'https://graph.facebook.com/{version}/{phone_number_id}'
REQUEST_TIMEOUT = 10
DEFAULT_API_VERSION = 'v21.0'


class WhatsAppApiError(Exception):
    """Any failure talking to the Meta WhatsApp Cloud API (config/network/auth/API)."""


def normalize_number(number):
    """Keep digits only, as required by the WhatsApp Cloud API `to` field."""
    return re.sub(r'\D', '', number or '')


def send_whatsapp_template(phone_number_id, access_token, api_version, to_number,
                            template_name, template_language, params=None, button_param=None):
    """Send ONE pre-approved template message to ONE number. Raises WhatsAppApiError on any
    failure (missing config, network error, or Meta rejecting the request - e.g. unknown
    template name/language, unsubscribed number, rate limit) - never returns a silent False,
    unlike the sibling helpdesk integration, so the caller can log/surface the real reason.

    `params` (list of strings, optional) fill the template's numbered placeholders ({{1}},
    {{2}}, ...) in order, as the single "body" component.

    `button_param` (str, optional) fills the DYNAMIC SUFFIX of a "Website" button configured
    in the template as a Dynamic URL - Meta only allows the button's URL to be dynamic at the
    very END of a fixed prefix already baked into the approved template (anti-phishing
    restriction), never the whole URL - so this is just that trailing part (e.g.
    `id=123&model=account.payment.order&view_type=form`), never a full `https://...` string."""
    to_number = normalize_number(to_number)
    if not (phone_number_id and access_token):
        raise WhatsAppApiError(
            'La cuenta de WhatsApp de esta compañía no está configurada '
            '(falta Phone Number ID o Access Token).')
    if not to_number:
        raise WhatsAppApiError('El destinatario no tiene un número de teléfono válido.')
    if not template_name:
        raise WhatsAppApiError('No se definió qué plantilla de WhatsApp usar.')

    components = []
    if params:
        components.append({
            'type': 'body',
            'parameters': [{'type': 'text', 'text': str(p)} for p in params],
        })
    if button_param:
        components.append({
            'type': 'button',
            'sub_type': 'url',
            'index': '0',
            'parameters': [{'type': 'text', 'text': str(button_param)}],
        })

    url = GRAPH_API_MESSAGES_URL.format(
        version=api_version or DEFAULT_API_VERSION, phone_number_id=phone_number_id)
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }
    payload = {
        'messaging_product': 'whatsapp',
        'to': to_number,
        'type': 'template',
        'template': {
            'name': template_name,
            'language': {'code': template_language or 'es'},
            'components': components,
        },
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise WhatsAppApiError(f'No se pudo conectar con la API de WhatsApp: {exc}') from exc

    try:
        data = response.json()
    except ValueError:
        raise WhatsAppApiError('Respuesta inválida de la API de WhatsApp.')

    if response.status_code >= 400:
        message = (data.get('error') or {}).get('message') or str(data)
        raise WhatsAppApiError(message)
    return data


def check_phone_number(phone_number_id, access_token, api_version):
    """Validate credentials by fetching the phone number's own info - sends no message, safe to
    use as a connectivity test. Returns (True, {verified_name, display_phone_number,
    quality_rating}) on success, or (False, error_message) on failure."""
    if not phone_number_id or not access_token:
        return False, 'Falta el Phone Number ID o el Access Token.'

    url = GRAPH_API_PHONE_URL.format(
        version=api_version or DEFAULT_API_VERSION, phone_number_id=phone_number_id)
    headers = {'Authorization': f'Bearer {access_token}'}
    params = {'fields': 'verified_name,display_phone_number,quality_rating'}
    try:
        response = requests.get(url, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        return False, str(exc)

    if response.status_code == 200:
        return True, response.json()

    try:
        error_message = response.json().get('error', {}).get('message', response.text)
    except ValueError:
        error_message = response.text
    return False, error_message
