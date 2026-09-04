"""Talking to Njiwa over HTTP. Transport only.

Nothing in here decides when to message anybody. It reads the settings, makes
the call, and turns a refusal into an exception the rest of the module, and an
administrator standing on the settings page, can read.

This is the only file in the module that talks HTTP.
"""

import logging

import requests

from odoo import _
from odoo.exceptions import UserError

from . import njiwa_config

_logger = logging.getLogger(__name__)

# Matches the version in __manifest__.py, and goes out on every request so a
# problem on Njiwa's side can be traced back to a release.
VERSION = "1.0.0"

# Long enough for a slow line, short enough that a stuck request cannot hold
# the scheduled action, and the queue behind it, for ever.
TIMEOUT_SECONDS = 20


class NjiwaError(UserError):
    """Anything Njiwa refused, or could not be asked.

    `code` is the stable, machine readable reason and is the thing to branch
    on: the delivery loop treats connection_failed as a message that was never
    accepted and can safely go again, and everything else as a refusal. The
    wording of the message can change; the code does not. `docs` is a page
    explaining that exact code.
    """

    def __init__(self, message, code="unknown", status=0, docs=None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.docs = docs


def send_text(env, to, text, idempotency_key=None):
    """Send one text message. Returns Njiwa's answer, including the id.

    `idempotency_key` is what stops a customer being messaged twice. Njiwa
    honours it for 24 hours: the same key again replays the first answer
    instead of sending a second message.
    """
    body = {"to": to, "text": text}

    # Only when the shop named a number. Left out, Njiwa uses the account's
    # default, which is the right answer for the shops that have one number and
    # never think about this again.
    sender = njiwa_config.from_number(env)
    if sender:
        body["from"] = sender

    return request(env, "POST", "/v1/messages", body=body, idempotency_key=idempotency_key)


def instances(env):
    """The WhatsApp numbers on this account, linked or not."""
    answer = request(env, "GET", "/v1/instances") or {}
    return answer.get("data") or []


def request(env, method, path, body=None, idempotency_key=None):
    """One call to Njiwa. Raises NjiwaError, and never anything else."""
    if not njiwa_config.enabled(env):
        # The master switch, failing loudly rather than quietly. A send that
        # happens while Njiwa is switched off is a mistake somebody should be
        # able to find afterwards, not a silent nothing.
        raise NjiwaError(
            _("Njiwa is switched off in the Njiwa settings, so nothing was sent."),
            code="switched_off",
        )

    key = njiwa_config.api_key(env)
    if not key:
        raise NjiwaError(
            _("There is no Njiwa API key saved, so nothing can be sent."),
            code="not_configured",
        )

    address = njiwa_config.base_url(env)
    headers = {
        "Authorization": "Bearer %s" % key,
        "Accept": "application/json",
        "User-Agent": "njiwa-odoo/%s" % VERSION,
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    try:
        response = requests.request(
            method,
            "%s%s" % (address, path),
            headers=headers,
            json=body,
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exception:
        # A network failure is not a send failure. The message was never
        # accepted, so it is safe to offer it again, and the code says so.
        raise NjiwaError(
            _("Could not reach Njiwa at %(address)s. %(reason)s")
            % {"address": address, "reason": exception},
            code="connection_failed",
        ) from exception

    if response.status_code == 204:
        return {}

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    if response.status_code >= 400:
        error = payload.get("error") or {}
        raise NjiwaError(
            error.get("message") or _("Njiwa answered with HTTP %s.") % response.status_code,
            code=error.get("code") or "unknown",
            status=response.status_code,
            docs=error.get("docs"),
        )

    return payload
