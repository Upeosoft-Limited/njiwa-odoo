"""One moment on a journal entry: a credit note was posted.

_post is where an entry becomes real, and every path to that goes through it:
the Confirm button, a payment that posts its own entry, and the scheduled
action that posts an entry somebody dated for today.
"""

from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _post(self, soft=True):
        """A posted credit note is the moment money is going back.

        Not the moment it arrives in their bank: that is days later and Odoo
        never sees it. The wording this module ships says exactly that, because
        a customer who is told "refunded" and sees nothing that afternoon
        writes to ask where it is.
        """
        posted = super()._post(soft=soft)

        queue = self.env["njiwa.pending.send"]
        for move in posted:
            if move.move_type != "out_refund":
                continue
            queue._queue_for_customer(move, "refunded", move.partner_id)

        return posted
