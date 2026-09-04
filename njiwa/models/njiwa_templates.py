"""The message itself.

A template is plain text with placeholders in braces. The list of placeholders
is the same one every Njiwa plugin uses, so a shop owner who has set one of
these up on another platform already knows what to type. What each one is
filled in with here is an Odoo field, and PLACEHOLDERS below is both the
substitution table and the documentation the settings page prints, so the two
cannot drift apart.

Three kinds of record reach this file: a sale.order, an account.move and a
stock.picking. They share almost no field names, which is why every value is
worked out per model and a placeholder with no answer on this record comes out
as nothing rather than as the literal brace.
"""

import logging
import re
from datetime import datetime

from odoo import _, fields
from odoo.tools.misc import formatLang, format_date

_logger = logging.getLogger(__name__)

# WhatsApp takes 4096 characters. Stopping short leaves room for a footer.
MAX_LENGTH = 4000

# How many lines {items} prints before it starts counting instead. An Odoo
# order can carry two hundred lines, and a WhatsApp message that long is not
# read by anybody.
MAX_ITEMS = 10


def placeholders():
    """Placeholder, and what it is replaced with, in the shop's own words."""
    return {
        "{first_name}": _("The first word of the customer's name, or 'there' if there is none."),
        "{last_name}": _("The rest of the customer's name."),
        "{customer_name}": _("The customer's name as Odoo holds it."),
        "{order_number}": _("The reference of the document that caused the message, such as S00042."),
        "{order_total}": _("The total, with your currency symbol."),
        "{order_date}": _("The order date, the invoice date, or the day the delivery went out."),
        "{order_status}": _("The state the document has just reached."),
        "{payment_method}": _(
            "How they paid, when the document knows. An order paid online names the provider; "
            "an order invoiced and paid later has nothing to name, and this comes out empty."
        ),
        "{items}": _("One line per line of the order, as '2 x Blue shirt'."),
        "{item_count}": _("How many items in total."),
        "{shop_name}": _("The company the document belongs to."),
        "{order_url}": _(
            "A link the customer can open to see their own order or invoice. It carries its own "
            "access token, so it works without a login. A delivery has no such page and this "
            "comes out empty on one."
        ),
        "{admin_url}": _(
            "A link that opens the document in Odoo. Only put this in the message to yourself: "
            "a customer cannot open it."
        ),
    }


def default_for(event):
    """What each message says before anybody edits it.

    These live in Python rather than only in the settings, because the settings
    page is not what sends a message: a scheduled action is, and it must have
    something sensible to say on a database whose settings page has been opened
    exactly once.

    They are deliberately short. A WhatsApp message that reads like an email
    gets read like an email, which is to say not at all.
    """
    return DEFAULTS.get(event, "")


DEFAULTS = {
    "order_placed": (
        "Hi {first_name}, we have your order {order_number} for {order_total}. "
        "We will let you know as it moves along.\n\n{items}\n\n{shop_name}"
    ),
    "payment_received": (
        "Hi {first_name}, thank you. Your payment for {order_number} has come through, "
        "in full, and there is nothing more to pay on it.\n\n{shop_name}"
    ),
    "shipped": (
        "Hi {first_name}, your order is on its way. Our delivery reference is "
        "{order_number}.\n\n{items}\n\n{shop_name}"
    ),
    "order_cancelled": (
        "Hi {first_name}, order {order_number} has been cancelled. If that is not what you "
        "expected, reply to this message and we will look into it.\n\n{shop_name}"
    ),
    "refunded": (
        "Hi {first_name}, we have credited {order_total} back to you on {order_number}. "
        "Where the money is going back to a bank account, it takes a few days to "
        "show.\n\n{shop_name}"
    ),
    "new_order": (
        "New order {order_number} on {shop_name}.\n\n{customer_name}\n"
        "{item_count} item(s), {order_total}\n\n{admin_url}"
    ),
}


def render(template, record):
    """Fill a template in from a document. Returns '' for an empty template.

    An empty template is how a shop turns one message off without turning the
    event off, so it is a legitimate answer and not a fault.
    """
    template = (template or "").strip()
    if not template:
        return ""

    values = values_for(record)

    # Anything in braces that is not a placeholder is a typo, usually
    # {order_no} for {order_number}. It is found in the template rather than in
    # the finished message, because a message can quite legitimately contain
    # braces once a product name has been substituted in, and a shop should not
    # have a product renamed out from under it.
    unknown = sorted(set(re.findall(r"\{[a-z_]+\}", template)) - set(values))
    if unknown:
        _logger.warning(
            "Unknown placeholder %s in a Njiwa message template. It was removed before sending.",
            ", ".join(unknown),
        )
        for token in unknown:
            template = template.replace(token, "")

    # One pass, so a value that happens to contain braces is left alone rather
    # than substituted again.
    message = re.sub(r"\{[a-z_]+\}", lambda found: values.get(found.group(0), ""), template)

    message = re.sub(r"\n{3,}", "\n\n", message).strip()

    if len(message) > MAX_LENGTH:
        message = message[: MAX_LENGTH - 1] + "…"

    return message


def values_for(record):
    """Every placeholder, filled in from the document."""
    partner = record.partner_id

    # In the customer's own language where they have one. It is their message:
    # the wording is the shop's, but the state of the order, the date and the
    # currency should read the way everything else they get from you reads.
    if partner.lang:
        record = record.with_context(lang=partner.lang)
        partner = partner.with_context(lang=partner.lang)

    name = partner.name or ""
    first, _separator, last = name.partition(" ")
    amount, currency = money(record)

    return {
        # Odoo keeps one name where WooCommerce keeps two, so this is the first
        # word of it. For a company that is the first word of the company name,
        # which reads better than nothing and better than "Dear Sir".
        "{first_name}": first or _("there"),
        "{last_name}": last,
        "{customer_name}": name,
        "{order_number}": record.name or "",
        "{order_total}": formatLang(record.env, amount, currency_obj=currency) if currency else "",
        "{order_date}": document_date(record),
        "{order_status}": state_label(record),
        "{payment_method}": payment_method(record),
        "{items}": items(record),
        "{item_count}": item_count(record),
        "{shop_name}": record.company_id.name or "",
        "{order_url}": portal_url(record),
        "{admin_url}": backend_url(record),
    }


def money(record):
    """The number the customer would recognise, and the currency it is in.

    A delivery has no total of its own. Where it came from a sales order, that
    order's total is the figure the customer is holding; where it did not, this
    comes back empty rather than as a nought.
    """
    if "amount_total" in record._fields:
        return record.amount_total, record.currency_id

    order = source_order(record)
    if order:
        return order.amount_total, order.currency_id

    return 0.0, None


def source_order(record):
    """The sales order a delivery came from, when Odoo can say.

    stock.picking.sale_id belongs to sale_stock, the module that bridges the
    two. It is installed on any database that sells and ships, but this module
    does not depend on it, so the field is asked for rather than assumed.
    """
    if "sale_id" in record._fields:
        return record.sale_id
    return None


def document_date(record):
    """The date the customer would put on this, in their own format."""
    for field in ("date_order", "invoice_date", "date_done", "scheduled_date", "date"):
        if field in record._fields and record[field]:
            value = record[field]
            if isinstance(value, datetime):
                # Stored in UTC. Shown in the reader's own day, which is what
                # stops an evening order being reported as tomorrow.
                value = fields.Datetime.context_timestamp(record, value).date()
            return format_date(record.env, value)
    return ""


def state_label(record):
    """The state, spelled the way the screen spells it rather than 'sale'."""
    if "state" not in record._fields or not record.state:
        return ""
    selection = record.fields_get(["state"])["state"].get("selection") or []
    return dict(selection).get(record.state, record.state)


def payment_method(record):
    """How they paid, where the document actually knows.

    Odoo does not carry "how they paid" on an order the way a web shop does:
    the money arrives later, on a document of its own. Where the order was paid
    online there is a payment transaction naming the provider, and that is the
    honest answer. Everywhere else this is empty, and the settings page says so
    rather than leaving somebody to find out from a customer.
    """
    if "transaction_ids" not in record._fields:
        return ""

    names = []
    for transaction in record.transaction_ids:
        if transaction.state not in ("authorized", "done"):
            continue
        provider = transaction.provider_id if "provider_id" in transaction._fields else None
        label = provider.name if provider else ""
        if label and label not in names:
            names.append(label)
    return ", ".join(names)


def lines(record):
    """The lines worth reading out, whichever kind of document this is.

    Sections and notes are dropped: they are headings the shop wrote for
    itself, and a customer reading "2 x " for one would wonder what it was.
    """
    if "order_line" in record._fields:
        return [
            (line.product_id.name or line.name, line.product_uom_qty)
            for line in record.order_line
            if not line.display_type
        ]

    if "invoice_line_ids" in record._fields:
        return [
            (line.product_id.name or line.name, line.quantity)
            for line in record.invoice_line_ids
            if line.display_type in (False, "product")
        ]

    if "move_ids" in record._fields:
        # What went out, not what was asked for: a delivery that shipped two of
        # three should say two. Odoo 17 renamed stock.move.quantity_done to
        # quantity, so the field is asked for by name rather than assumed.
        done = "quantity_done" if "quantity_done" in record.move_ids._fields else "quantity"
        return [(move.product_id.name, move[done]) for move in record.move_ids]

    return []


def items(record):
    """One line per line of the order, as "2 x Blue shirt"."""
    printed = []
    more = 0

    for label, quantity_of in lines(record):
        if len(printed) >= MAX_ITEMS:
            more += 1
            continue
        printed.append("%s x %s" % (quantity(quantity_of), label or ""))

    if more:
        printed.append(_("and %s more") % more)

    return "\n".join(printed)


def item_count(record):
    """How many things are on the document, counting quantities."""
    return quantity(sum(quantity_of for _label, quantity_of in lines(record)))


def quantity(value):
    """A quantity as a person would write it.

    Odoo keeps quantities as floats, so two shirts are 2.0 shirts. Nobody
    writes that, and a customer reading it wonders what the .0 means. A
    fractional quantity, which is real for anything sold by weight or length,
    keeps its decimals and loses the trailing zeros.
    """
    number = float(value or 0.0)
    if number == int(number):
        return str(int(number))
    return ("%.3f" % number).rstrip("0").rstrip(".")


def portal_url(record):
    """Where the customer can see this, without a login.

    get_portal_url() belongs to portal.mixin and puts an access token in the
    link, which is what makes it open for somebody who has no Odoo account. A
    stock.picking is not a portal document and has no such page, so a delivery
    message that uses {order_url} gets nothing rather than a link to a login
    screen.
    """
    if not hasattr(record, "get_portal_url"):
        return ""
    return record.get_base_url() + record.get_portal_url()


def backend_url(record):
    """A link that opens the document in Odoo, for the message to the shop."""
    return "%s/web#id=%s&model=%s&view_type=form" % (
        record.get_base_url(),
        record.id,
        record._name,
    )
