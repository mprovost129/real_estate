import base64
import json
import logging
from urllib import error, parse, request

from django.conf import settings


logger = logging.getLogger(__name__)


class SMSDeliveryError(Exception):
    pass


def send_sms_message(*, to_number, body):
    """
    Send SMS using configured provider.
    Supported providers:
    - console: no external call, logs output and returns success
    - twilio: direct Twilio REST API call via urllib
    """
    provider = getattr(settings, "SMS_PROVIDER", "console")

    if provider == "console":
        logger.info("SMS[console] to=%s body=%s", to_number, body)
        return {"sent": True, "provider": "console", "message_id": ""}

    if provider == "twilio":
        return _send_twilio(to_number=to_number, body=body)

    raise SMSDeliveryError(f"Unsupported SMS_PROVIDER: {provider}")


def _send_twilio(*, to_number, body):
    account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", "")
    auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", "")
    from_number = getattr(settings, "TWILIO_PHONE_NUMBER", "")

    if not account_sid or not auth_token or not from_number:
        raise SMSDeliveryError("Twilio settings are incomplete. Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER.")

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    payload = parse.urlencode(
        {
            "To": to_number,
            "From": from_number,
            "Body": body,
        }
    ).encode("utf-8")

    token = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
    req = request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            data = json.loads(raw or "{}")
            message_sid = data.get("sid", "")
            status = data.get("status", "")
            if status in {"failed", "undelivered"}:
                raise SMSDeliveryError(f"Twilio returned status '{status}'.")
            return {"sent": True, "provider": "twilio", "message_id": message_sid}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise SMSDeliveryError(f"Twilio HTTP error {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise SMSDeliveryError(f"Twilio connection error: {exc}") from exc
