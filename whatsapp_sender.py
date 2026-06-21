"""
whatsapp_sender.py
Handles outbound WhatsApp messages via Meta's Cloud API for Nudge by Addicoot.

Env vars required (.env):
    WHATSAPP_TOKEN          - permanent or long-lived access token for the WABA system user
    WHATSAPP_PHONE_NUMBER_ID - the Phone Number ID (NOT the phone number itself) from Meta dev console
    WHATSAPP_BUSINESS_ACCOUNT_ID - the WABA ID, used only for template submission
    WHATSAPP_API_VERSION    - optional, defaults to v23.0
"""

import os
import logging
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WABA_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")
API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v23.0")

GRAPH_BASE = f"https://graph.facebook.com/{API_VERSION}"

# Name of the approved template used for the daily nudge.
# Must exactly match the template name you submit for approval (see submit_daily_nudge_template()).
DAILY_NUDGE_TEMPLATE_NAME = "daily_nudge"
DAILY_NUDGE_TEMPLATE_LANG = "en"


class WhatsAppSendError(Exception):
    pass


def _require_config():
    missing = [
        name for name, val in [
            ("WHATSAPP_TOKEN", WHATSAPP_TOKEN),
            ("WHATSAPP_PHONE_NUMBER_ID", PHONE_NUMBER_ID),
        ] if not val
    ]
    if missing:
        raise WhatsAppSendError(f"Missing required env vars: {', '.join(missing)}")


def whatsapp_send(to_number: str, message: str) -> dict:
    """
    Send the daily nudge to a user via the approved 'daily_nudge' template.

    to_number: WhatsApp number in E.164 format WITHOUT the leading '+', e.g. '919876543210'
    message: the full Gemini-generated nudge text, inserted as the template's single {{1}} variable

    Returns the parsed JSON response from Meta on success.
    Raises WhatsAppSendError on failure (caller should catch this so one bad
    number doesn't kill the rest of the scheduler loop).
    """
    _require_config()

    if not to_number or to_number == "N/A":
        raise WhatsAppSendError(f"No valid WhatsApp number provided")

    clean_number = to_number.strip().replace("+", "").replace(" ", "").replace("-", "")

    url = f"{GRAPH_BASE}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_number,
        "type": "template",
        "template": {
            "name": DAILY_NUDGE_TEMPLATE_NAME,
            "language": {"code": DAILY_NUDGE_TEMPLATE_LANG},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": message}
                    ]
                }
            ]
        }
    }

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=15.0)
    except httpx.RequestError as e:
        raise WhatsAppSendError(f"Network error sending to {clean_number}: {e}") from e

    if response.status_code != 200:
        raise WhatsAppSendError(
            f"Meta API error ({response.status_code}) for {clean_number}: {response.text}"
        )

    data = response.json()
    logger.info(f"WhatsApp message sent to {clean_number}: {data}")
    return data


def whatsapp_send_freeform(to_number: str, message: str) -> dict:
    """
    Send a plain-text message WITHOUT a template.
    Only works inside Meta's 24-hour customer service window (i.e. the user
    messaged you in the last 24h, e.g. a check-in reply or onboarding confirmation).
    Do NOT use this for the daily proactive nudge — it will fail outside the window.
    """
    _require_config()
    clean_number = to_number.strip().replace("+", "").replace(" ", "").replace("-", "")

    url = f"{GRAPH_BASE}/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": clean_number,
        "type": "text",
        "text": {"body": message},
    }

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=15.0)
    except httpx.RequestError as e:
        raise WhatsAppSendError(f"Network error sending to {clean_number}: {e}") from e

    if response.status_code != 200:
        raise WhatsAppSendError(
            f"Meta API error ({response.status_code}) for {clean_number}: {response.text}"
        )

    return response.json()


def submit_daily_nudge_template() -> dict:
    """
    One-time helper: submits the 'daily_nudge' template to Meta for approval.
    Run this manually once (e.g. `python -c "from whatsapp_sender import submit_daily_nudge_template; print(submit_daily_nudge_template())"`).
    Do NOT call this from the scheduler or any request path — template creation is a
    one-off admin action, not a runtime operation.

    Template design: single body variable {{1}} holding the full AI-generated nudge text.
    Category MARKETING is used since these are proactive engagement messages outside
    a live chat window, sent on a recurring schedule — this is what Meta expects for
    this kind of use case and avoids UTILITY-category rejection.
    """
    if not WABA_ID:
        raise WhatsAppSendError("Missing WHATSAPP_BUSINESS_ACCOUNT_ID env var")
    _require_config()

    url = f"{GRAPH_BASE}/{WABA_ID}/message_templates"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "name": DAILY_NUDGE_TEMPLATE_NAME,
        "language": DAILY_NUDGE_TEMPLATE_LANG,
        "category": "MARKETING",
        "components": [
            {
                "type": "BODY",
                "text": "{{1}}",
                "example": {
                    "body_text": [
                        [
                            "Good morning Shruthi! 🌱 Remember your goal to apply to 5 jobs this week. "
                            "You already nailed the BQ26 certification, so you've got the discipline for this too. "
                            "Today's move: send 1 application before lunch. Small steps, real progress 💪"
                        ]
                    ]
                }
            },
            {
                "type": "FOOTER",
                "text": "Reply DONE when you've taken today's action."
            }
        ]
    }

    response = httpx.post(url, json=payload, headers=headers, timeout=15.0)
    if response.status_code != 200:
        raise WhatsAppSendError(f"Template submission failed ({response.status_code}): {response.text}")

    data = response.json()
    logger.info(f"Template submitted: {data}")
    return data


def check_template_status() -> dict:
    """Fetch current approval status of the daily_nudge template."""
    if not WABA_ID:
        raise WhatsAppSendError("Missing WHATSAPP_BUSINESS_ACCOUNT_ID env var")
    _require_config()

    url = f"{GRAPH_BASE}/{WABA_ID}/message_templates"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    params = {"name": DAILY_NUDGE_TEMPLATE_NAME}

    response = httpx.get(url, headers=headers, params=params, timeout=15.0)
    if response.status_code != 200:
        raise WhatsAppSendError(f"Status check failed ({response.status_code}): {response.text}")
    return response.json()