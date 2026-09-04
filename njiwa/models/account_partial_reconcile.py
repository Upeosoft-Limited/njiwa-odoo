"""One moment in the accounts: a customer invoice has been paid.

This is the one event that cannot be hooked where you would expect. An invoice
carries payment_state, and payment_state is a stored computed field: the ORM
writes it while flushing, underneath write(), so a write() override does not
see it change and a compute override cannot read the old value without
recomputing the thing it is inside.

What is left is the moment underneath, which is also the moment that is
actually true: money has been matched against the invoice. Every way of paying
an invoice ends in a partial reconciliation, whether it was a payment
registered by hand, a bank statement matched in the reconciliation screen, or a
gateway posting its own entry, so this catches all of them and nothing else.
"""

import logging

from odoo import api, models

from . import njiwa_config

_logger = logging.getLogger(__name__)

# The states an invoice is in once the customer has done their part.
# in_payment is a shop whose journal keeps an outstanding account: the payment
# is recorded and the customer has paid, and the bank statement that turns it
# into paid is the shop's own bookkeeping, days later.
PAID_ENOUGH = ("paid", "in_payment")


class AccountPartialReconcile(models.Model):
    _inherit = "account.partial.reconcile"

    @api.model_create_multi
    def create(self, vals_list):
        partials = super().create(vals_list)
        partials._njiwa_payment_received()
        return partials

    def _njiwa_payment_received(self):
        """Arrange the message, without ever being able to break the payment.

        The switches are read first because reading them is two small parameter
        lookups, and everything after them is not: finding the invoices walks
        both sides of every reconciliation and reads payment_state, a stored
        computed field, so asking for it makes the ORM work out the residual of
        each move again. A database where nobody has turned Njiwa on should pay
        none of that every time somebody registers a payment.

        The rest is inside the same try and savepoint every other hook in this
        module uses. Every way of paying an invoice ends here: a payment
        registered by hand, a bank statement matched in the reconciliation
        screen, a gateway posting its own entry. None of them may fail because
        a WhatsApp message could not be arranged, so nothing below is allowed
        out of this method. The savepoint is there as well as the try because a
        database error cannot be undone by catching it in Python.
        """
        if not njiwa_config.enabled(self.env):
            return
        if not njiwa_config.event_on(self.env, "payment_received"):
            return

        try:
            with self.env.cr.savepoint():
                queue = self.env["njiwa.pending.send"]
                for invoice in self._njiwa_invoices_now_paid():
                    queue._queue_for_customer(invoice, "payment_received", invoice.partner_id)
        except Exception:
            _logger.exception(
                "Njiwa could not queue the payment_received message for reconciliations %s",
                self.ids,
            )

    def _njiwa_invoices_now_paid(self):
        """The customer invoices these reconciliations have just finished off.

        A part payment is not one of them. The customer still owes money, and
        being thanked for paying when they have not finished is the kind of
        message that produces a phone call rather than saving one.

        Neither is an invoice settled by a credit note. Nobody paid anything:
        the refund event has already told that customer what happened, and
        thanking them for a payment they did not make reads as a mistake,
        because it is one.
        """
        invoices = self.env["account.move"]

        for partial in self:
            sides = (
                (partial.debit_move_id.move_id, partial.credit_move_id.move_id),
                (partial.credit_move_id.move_id, partial.debit_move_id.move_id),
            )
            for move, counterpart in sides:
                if move.move_type != "out_invoice" or move.state != "posted":
                    continue
                if counterpart.move_type == "out_refund":
                    continue
                if move.payment_state not in PAID_ENOUGH:
                    continue
                invoices |= move

        return invoices
