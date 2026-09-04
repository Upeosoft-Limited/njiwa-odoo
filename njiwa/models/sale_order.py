"""Two moments on a sales order: it was confirmed, and it was cancelled.

Neither is a write(). An order is written to when somebody corrects a delivery
address, adds a line, or changes the salesperson, and a customer messaged for
any of those would learn nothing and think the shop was broken.
"""

from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        """A quotation becoming an order is the first moment it is real.

        It is also when the shop hears about it. Not when the quotation is
        written, which happens while somebody is still deciding, and not when
        the record is created, which on a web order happens the moment a
        visitor reaches the payment page and usually means nothing.

        The state is checked afterwards rather than assumed, because
        action_confirm can be given several orders at once and Odoo may lock
        the ones it confirms.
        """
        confirmed = super().action_confirm()

        queue = self.env["njiwa.pending.send"]
        for order in self:
            if order.state not in ("sale", "done"):
                continue
            queue._queue_for_customer(order, "order_placed", order.partner_id)
            queue._queue_for_shop(order, "new_order")

        return confirmed

    def _action_cancel(self):
        """Where a cancellation actually happens.

        action_cancel is the button, and on an order whose confirmation has
        already been emailed it opens a wizard and cancels nothing; the wizard
        then calls this. Everything that cancels an order ends up here, which
        is why the message is arranged here.
        """
        cancelled = super()._action_cancel()
        self._njiwa_cancelled()
        return cancelled

    def action_cancel(self):
        """The button itself, for the path that does not open the wizard.

        Odoo 16 and 17 both route it through _action_cancel, so on those this
        adds nothing; it is here so that a version which cancels in the button
        still tells the customer. The marker on the queue is what stops the two
        of them sending twice.
        """
        cancelled = super().action_cancel()
        self._njiwa_cancelled()
        return cancelled

    def _njiwa_cancelled(self):
        queue = self.env["njiwa.pending.send"]
        for order in self:
            if order.state != "cancel":
                # A wizard was opened and nothing has been cancelled yet.
                continue
            queue._queue_for_customer(order, "order_cancelled", order.partner_id)
