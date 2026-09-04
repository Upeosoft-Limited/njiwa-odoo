"""What a cleared message box does to the queue, which is nothing at all.

Clearing the box is the documented way to stop one message while the event
stays on. The failure that made this file necessary was a row queued anyway,
which came back a minute later as a red failure note on every order, invoice
and delivery the shop had.
"""

from odoo.tests import TransactionCase, tagged

from odoo.addons.njiwa.models import njiwa_config


@tagged("post_install", "-at_install")
class TestEmptyWordingQueuesNothing(TransactionCase):
    def setUp(self):
        super().setUp()
        parameters = self.env["ir.config_parameter"].sudo()
        parameters.set_param(njiwa_config.P_ENABLED, "True")
        parameters.set_param(njiwa_config.P_EVENT % "order_placed", "True")
        self.queue = self.env["njiwa.pending.send"]
        self.customer = self.env["res.partner"].create(
            {"name": "A customer", "mobile": "254712345678"}
        )

    def _rows(self):
        return self.queue.sudo().search(
            [("res_model", "=", "res.partner"), ("res_id", "=", self.customer.id)]
        )

    def test_a_cleared_box_queues_nothing_and_says_nothing(self):
        self.env["ir.config_parameter"].sudo().set_param(
            njiwa_config.P_MESSAGE % "order_placed", njiwa_config.BLANK
        )
        notes_before = len(self.customer.message_ids)

        self.queue._queue_for_customer(self.customer, "order_placed", self.customer)

        self.assertFalse(self._rows())
        self.assertEqual(len(self.customer.message_ids), notes_before)

    def test_the_wording_we_ship_still_queues(self):
        self.queue._queue_for_customer(self.customer, "order_placed", self.customer)
        self.assertEqual(len(self._rows()), 1)
