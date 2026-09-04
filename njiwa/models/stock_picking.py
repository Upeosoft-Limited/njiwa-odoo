"""One moment in the warehouse: it has gone out.

button_validate is the moment stock actually moves, and it is not always the
moment it is pressed: an immediate transfer or a backorder puts a wizard in
between and validates nothing until that wizard is answered. The state is
therefore read afterwards rather than assumed.
"""

from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        validated = super().button_validate()

        queue = self.env["njiwa.pending.send"]
        for picking in self:
            if picking.state != "done":
                # A wizard was returned and nothing has moved yet. It comes
                # back through here when the wizard is answered.
                continue
            if picking.picking_type_code != "outgoing":
                # A receipt from a supplier and an internal transfer are
                # nobody's business but the shop's.
                continue
            queue._queue_for_customer(picking, "shipped", picking.partner_id)

        return validated
