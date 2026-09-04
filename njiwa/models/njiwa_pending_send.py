"""The queue, and the worker that drains it.

Two rules run this file. Nothing is sent from the request that confirmed the
order, and nothing is sent twice.

The first is why this model exists at all. Confirming an order writes one small
row here and returns; a scheduled action picks the row up a minute later and
makes the HTTP call. A shop must not wait on WhatsApp to take an order, and
Njiwa being slow must never be able to lose a sale. It is deliberately not the
OCA queue_job addon: that is an excellent thing to have and most Odoo databases
do not have it, and a module that breaks on a database without it is a module
that looks installed and quietly sends nothing.

The second is why the row carries an idempotency key and is looked up by it
before another is written. Njiwa honours the key for 24 hours, so a job that
runs twice replays the first answer rather than messaging the customer again;
the row outlives that, and is what stops a document that somehow reaches the
same moment twice, months apart, sending a second time.

This model deliberately keeps no copy of the message text. Njiwa already stores
every message, its status and its failure reason, and a second copy is a second
thing to keep in step.
"""

import hashlib
import logging
from datetime import timedelta

from markupsafe import escape

from odoo import _, api, fields, models

from . import njiwa_client, njiwa_config, njiwa_numbers, njiwa_templates

_logger = logging.getLogger(__name__)

# How many times a message Njiwa never accepted is offered again. A network
# that is down for five minutes should not cost anybody a message; a network
# that is down for an hour is somebody's problem to look at, and by then the
# row says so.
MAX_ATTEMPTS = 5

# After this, a message stops being worth sending. A customer who is told on
# Thursday that their Monday order is confirmed learns nothing and wonders what
# else is wrong. It is also the window Njiwa honours an idempotency key for.
STALE_AFTER = timedelta(hours=24)


class NjiwaPendingSend(models.Model):
    _name = "njiwa.pending.send"
    _description = "Njiwa message waiting to go out"
    _order = "id"
    _rec_name = "idempotency_key"

    idempotency_key = fields.Char(
        string="Idempotency key", required=True, readonly=True, index=True
    )
    res_model = fields.Char(string="Document model", required=True, readonly=True)
    res_id = fields.Integer(string="Document", required=True, readonly=True)
    record_name = fields.Char(string="Document reference", readonly=True)
    event = fields.Selection(selection=njiwa_config.ALL_EVENTS, required=True, readonly=True)
    to_number = fields.Char(string="To", required=True, readonly=True)
    state = fields.Selection(
        [("queued", "Waiting"), ("sent", "Sent"), ("failed", "Failed")],
        default="queued",
        required=True,
        readonly=True,
        index=True,
    )
    attempts = fields.Integer(readonly=True, default=0)
    message_id = fields.Char(string="Njiwa message id", readonly=True)
    failure_reason = fields.Text(readonly=True)

    _sql_constraints = [
        (
            "idempotency_key_unique",
            "unique(idempotency_key)",
            "Njiwa has already queued this message for this document.",
        )
    ]

    # ------------------------------------------------------------ queueing

    @api.model
    def _queue_for_customer(self, record, event, partner):
        """One message to the customer, if this event is on and they have a number.

        Everything is inside one try and one savepoint, and that is the point
        of this method. An order must never fail to confirm, and a delivery
        must never fail to validate, because a WhatsApp message could not be
        arranged: that would turn a messaging module into a reason the shop
        cannot ship. The savepoint is there as well as the try because a
        database error cannot be undone by catching it in Python.
        """
        try:
            with self.env.cr.savepoint():
                if not njiwa_config.enabled(self.env):
                    return
                if not njiwa_config.event_on(self.env, event):
                    return

                number = njiwa_numbers.for_partner(partner)
                if not number:
                    # A customer with no number is normal, and it is not an
                    # error. It is written on the document, though, because "I
                    # turned it on and nothing happened" is the first thing
                    # anybody asks, and this is the answer, sitting where they
                    # are already looking.
                    self._note(
                        record,
                        _("Njiwa: no WhatsApp message, because %s has no phone number.")
                        % (partner.display_name or _("this customer")),
                    )
                    return

                self._enqueue(record, event, number)
        except Exception:
            _logger.exception(
                "Njiwa could not queue the %s message for %s %s", event, record._name, record.id
            )

    @api.model
    def _queue_for_shop(self, record, event):
        """One message to the shop's own numbers, once per document.

        Everybody listed gets their own copy, and the recipient is part of the
        idempotency key so those copies do not collapse into one another.
        """
        try:
            with self.env.cr.savepoint():
                if not njiwa_config.enabled(self.env):
                    return
                if not njiwa_config.event_on(self.env, event):
                    return

                for number in njiwa_numbers.parse_list(njiwa_config.alert_numbers(self.env)):
                    self._enqueue(record, event, number)
        except Exception:
            _logger.exception(
                "Njiwa could not queue the %s alert for %s %s", event, record._name, record.id
            )

    @api.model
    def _enqueue(self, record, event, number):
        """Write the row, unless this exact message has been queued before.

        The row is written inside the transaction that is confirming the
        document, so a confirmation that is rolled back further down the line
        takes the queued message with it and the customer hears nothing about
        an order that does not exist.

        It is created with sudo() because the person confirming the order is a
        salesperson, and a salesperson has no business writing to this table by
        hand. The row is still theirs: it names the document they confirmed.
        """
        if not njiwa_config.message(self.env, event):
            # Clearing the message box is how a shop stops one message without
            # turning the event off, so an empty wording is a decision and not
            # a fault. Nothing is queued, which is what keeps that decision
            # quiet: a row written here would come back a minute later as a
            # failure, and every order, invoice and delivery would carry a red
            # line about a message the shop chose not to send.
            return self.browse()

        key = self._idempotency_key(record, event, number)
        if self.sudo().search_count([("idempotency_key", "=", key)]):
            return self.browse()

        return self.sudo().create(
            {
                "idempotency_key": key,
                "res_model": record._name,
                "res_id": record.id,
                "record_name": record.display_name,
                "event": event,
                "to_number": number,
            }
        )

    @api.model
    def _idempotency_key(self, record, event, number):
        """One key per document, per event, per recipient.

        The database is in there too. Several Odoo databases can share one
        Njiwa account, and S00042 exists on all of them.
        """
        database = _short_hash(self.env.cr.dbname)
        recipient = _short_hash(number, length=6)
        return "odoo-%s-%s-%s-%s-%s" % (
            database,
            record._name.replace(".", "_"),
            record.id,
            event,
            recipient,
        )

    # ------------------------------------------------------------- sending

    @api.model
    def _drain(self, limit=100):
        """Send what is waiting. Run once a minute by the scheduled action.

        Each message is committed on its own. A queue where one refusal rolls
        back the four messages that went out before it is a queue that sends
        those four again on the next run.
        """
        if not njiwa_config.enabled(self.env):
            # Switched off is switched off: the rows stay where they are rather
            # than being sent or thrown away, and go out if it is switched back
            # on within the day.
            return

        waiting = self.sudo().search([("state", "=", "queued")], limit=limit)
        for row in waiting:
            try:
                with self.env.cr.savepoint():
                    row._send_one()
            except Exception:
                # _send_one writes down what went wrong itself. This is the net
                # under it: one unreadable row must not stop the queue.
                _logger.exception("Njiwa could not send queued message %s", row.idempotency_key)
            self._commit()

    def _send_one(self):
        """Send one message, and write down what happened either way."""
        self.ensure_one()

        if self.create_date and fields.Datetime.now() - self.create_date > STALE_AFTER:
            self._failed(
                _("This message waited more than a day to go out, so it was not sent.")
            )
            return

        record = self._record()
        if not record:
            self._failed(_("The document was deleted before the message went out."))
            return

        # The wording is read again rather than trusted from queueing time,
        # because a shop can clear the box in the minute this row waits. Empty
        # is a decision, so the row is dropped rather than failed: it is not
        # written on the document, and it does not sit in the queue in red.
        # Nothing was sent, so nothing can be sent twice by dropping it.
        message = njiwa_templates.render(njiwa_config.message(self.env, self.event), record)
        if not message:
            _logger.info(
                "The wording for the Njiwa %s message is empty, so %s %s sent nothing.",
                self.event,
                self.res_model,
                self.res_id,
            )
            self.unlink()
            return

        try:
            answer = njiwa_client.send_text(self.env, self.to_number, message, self.idempotency_key)
        except njiwa_client.NjiwaError as refusal:
            self._refused(refusal, record)
            return

        self.write(
            {
                "state": "sent",
                "message_id": answer.get("id") or "",
                "failure_reason": False,
            }
        )

        note = _("Njiwa: WhatsApp sent to +%(number)s (%(message_id)s).") % {
            "number": self.to_number,
            "message_id": answer.get("id") or "?",
        }
        if njiwa_config.is_test_key(self.env):
            note += " " + _("That was a test key, so nothing reached WhatsApp.")
        self._note(record, note)

    def _refused(self, refusal, record):
        """Njiwa would not take it, or could not be asked.

        A network failure is not a send failure: the message was never
        accepted, so it is offered again rather than written off, and the
        customer is not told about a wobble that lasted a minute. A refusal is
        different. Njiwa has read the message and said no, and saying no again
        in sixty seconds would not change its mind.
        """
        self.write({"attempts": self.attempts + 1, "failure_reason": str(refusal)})

        if refusal.code == "connection_failed" and self.attempts < MAX_ATTEMPTS:
            return

        self._failed(str(refusal) or _("Njiwa gave no reason."), record=record)

    def _failed(self, reason, record=None):
        self.write({"state": "failed", "failure_reason": reason})
        self._note(
            record if record is not None else self._record(),
            _("Njiwa: could not WhatsApp +%(number)s. %(reason)s")
            % {"number": self.to_number, "reason": reason},
        )

    # ------------------------------------------------------------- helpers

    def _record(self):
        """The document this message is about, or an empty answer."""
        self.ensure_one()
        if not self.res_model or self.res_model not in self.env:
            return None
        return self.env[self.res_model].sudo().browse(self.res_id).exists()

    @api.model
    def _note(self, record, text):
        """Write a line on the document, the way an order note reads.

        It goes on as an internal note, not as a message to the customer: the
        customer already has the WhatsApp, and a shop that follows its own
        orders should not get an email every time one goes out.

        Wrapped, because this is the record of what happened and not the thing
        that happened. A note that cannot be written must not turn a message
        that was sent into an error saying it was not.
        """
        if not record or not hasattr(record, "message_post"):
            return
        try:
            record.sudo().message_post(
                body=escape(text),
                message_type="comment",
                subtype_xmlid="mail.mt_note",
            )
        except Exception:
            _logger.warning("Could not write a Njiwa note on %s %s: %s", record._name, record.id, text)

    def _commit(self):
        """Keep what has already gone out, whatever the next message does.

        Committing inside a scheduled action is ordinary Odoo, and this is the
        same thing the outgoing mail queue does for the same reason. It is
        skipped under the test runner, where committing would escape the
        rollback the tests rely on.
        """
        if self.env.registry.in_test_mode():
            return
        self.env.cr.commit()


def _short_hash(value, length=8):
    # Not a security decision: this only has to be short and stable.
    return hashlib.md5(str(value).encode()).hexdigest()[:length]
