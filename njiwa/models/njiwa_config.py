"""Where the settings are kept, and the two traps in reading them back.

Everything on the settings page is stored in ir.config_parameter. That is the
storage Odoo keeps for the Settings administrator: reading a parameter goes
through check_access_rights('read') on a model no ordinary group is granted,
which is why the whole of Odoo reaches it with sudo(). A portal user cannot
read the API key, and neither can a salesperson.

The first trap is get_param(), which ends in `or default`. A parameter that has
been saved empty comes back as the default rather than as empty, which would
turn "I cleared this message box so nothing is sent" into "the wording we
shipped is sent". Every read below looks at the record instead, so "never
configured" and "deliberately blank" stay two different answers.

The second is that ir_config_parameter.value is required, and set_param()
deletes the row rather than storing an empty one. A cleared message box is
therefore stored as a single space: it satisfies the column, it strips to
nothing here, and it shows the shop the empty box it left behind.
"""

from . import njiwa_templates

# Where Njiwa lives, unless somebody has been given their own address.
DEFAULT_BASE_URL = "https://njiwa.upeo.ai"

# The parameter names. Everything this module stores starts with "njiwa.", and
# uninstalling deletes exactly that prefix.
P_ENABLED = "njiwa.enabled"
P_API_KEY = "njiwa.api_key"
P_BASE_URL = "njiwa.base_url"
P_FROM_NUMBER = "njiwa.from_number"
P_ALERT_NUMBERS = "njiwa.alert_numbers"
P_TEST_SENDS = "njiwa.test_sends"
P_EVENT = "njiwa.event_%s"
P_MESSAGE = "njiwa.message_%s"

# What the shop stores as a cleared message box. See the second trap above.
BLANK = " "

# Every moment this module can message a customer about, in the order they
# happen to an order, and the name each one has on the settings page.
#
# One entry per moment, and each is mapped in its own model file to the method
# Odoo calls when that moment is genuinely true. There is deliberately no
# entry for "the order was written to", which fires when somebody corrects a
# delivery address and would message a customer for it.
CUSTOMER_EVENTS = [
    ("order_placed", "Order confirmed"),
    ("payment_received", "Payment received"),
    ("shipped", "Shipped"),
    ("order_cancelled", "Order cancelled"),
    ("refunded", "Refunded"),
]

# The one message that goes to the shop rather than to the customer.
OWNER_EVENT = "new_order"

ALL_EVENTS = CUSTOMER_EVENTS + [(OWNER_EVENT, "New order, to you")]

EVENT_KEYS = [event for event, _label in ALL_EVENTS]


def raw(env, key):
    """The stored value, '' if it was stored blank, None if it was never set.

    The three answers are different and the whole file depends on keeping them
    apart, which is why this reads the record rather than calling get_param().
    """
    parameter = env["ir.config_parameter"].sudo().search([("key", "=", key)], limit=1)
    if not parameter:
        return None
    return parameter.value or ""


def _flag(value):
    """A tick box stored as text.

    bool("False") is True, and that is the bug this exists to prevent: a shop
    that turned an event off and had it stored as the string "False" would
    carry on sending.
    """
    return str(value or "").strip().lower() in ("1", "true", "yes", "t", "on")


def enabled(env):
    """The master switch, off until somebody turns it on.

    Installing a module must never cause a message to be sent, so an absent
    parameter reads as off rather than as on.
    """
    return _flag(raw(env, P_ENABLED))


def api_key(env):
    return (raw(env, P_API_KEY) or "").strip()


def is_test_key(env):
    return api_key(env).startswith("sk_test_")


def base_url(env):
    return (raw(env, P_BASE_URL) or "").strip().rstrip("/") or DEFAULT_BASE_URL


def from_number(env):
    """Which of the shop's linked numbers sends. Empty means the account default."""
    return "".join(character for character in (raw(env, P_FROM_NUMBER) or "") if character.isdigit())


def alert_numbers(env):
    return raw(env, P_ALERT_NUMBERS) or ""


def event_on(env, event):
    return _flag(raw(env, P_EVENT % event))


def message(env, event):
    """The wording for one event.

    An absent parameter is a shop that has never opened the settings page, and
    it gets the wording this module ships, because an event you tick should
    have something to say without a writing exercise first. A blank parameter
    is a shop that cleared the box on purpose, and it gets nothing, because
    clearing the box is how one message is turned off without turning the
    event off.
    """
    stored = raw(env, P_MESSAGE % event)
    if stored is None:
        return njiwa_templates.default_for(event)
    return stored.strip()
