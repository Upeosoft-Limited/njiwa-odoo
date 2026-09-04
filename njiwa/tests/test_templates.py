"""What a customer would actually read."""

from odoo.tests import TransactionCase, tagged

from odoo.addons.njiwa.models import njiwa_templates


@tagged("post_install", "-at_install")
class TestTemplateRenderer(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {"name": "Amina Wanjiru", "mobile": "0712345678"}
        )
        cls.shirt = cls.env["product.product"].create({"name": "Blue shirt", "list_price": 500.0})
        cls.order = cls.env["sale.order"].create(
            {
                "partner_id": cls.partner.id,
                "order_line": [(0, 0, {"product_id": cls.shirt.id, "product_uom_qty": 2})],
            }
        )

    def test_a_shipped_template_reads_like_a_message(self):
        message = njiwa_templates.render(
            "Hi {first_name}, your order {order_number} is on its way.\n\n{items}", self.order
        )
        self.assertIn("Hi Amina,", message)
        self.assertIn(self.order.name, message)
        self.assertIn("2 x Blue shirt", message)

    def test_the_name_is_split_and_a_missing_one_is_not_dear_sir(self):
        values = njiwa_templates.values_for(self.order)
        self.assertEqual(values["{first_name}"], "Amina")
        self.assertEqual(values["{last_name}"], "Wanjiru")
        self.assertEqual(values["{customer_name}"], "Amina Wanjiru")

        self.partner.name = "Mama Shop"
        self.assertEqual(njiwa_templates.values_for(self.order)["{first_name}"], "Mama")

    def test_a_quantity_is_written_the_way_a_person_writes_it(self):
        # Odoo keeps quantities as floats, and nobody tells a customer they are
        # getting 2.0 shirts.
        self.assertEqual(njiwa_templates.quantity(2.0), "2")
        self.assertEqual(njiwa_templates.quantity(0.5), "0.5")
        self.assertEqual(njiwa_templates.quantity(1.250), "1.25")
        self.assertEqual(njiwa_templates.values_for(self.order)["{item_count}"], "2")

    def test_the_total_carries_the_currency(self):
        total = njiwa_templates.values_for(self.order)["{order_total}"]
        self.assertTrue(total)
        self.assertIn(self.order.currency_id.symbol, total)

    def test_an_unknown_placeholder_is_removed_rather_than_sent(self):
        message = njiwa_templates.render("Order {order_no} for you", self.order)
        self.assertNotIn("{", message)
        self.assertEqual(message, "Order  for you")

    def test_an_empty_template_sends_nothing(self):
        self.assertEqual(njiwa_templates.render("", self.order), "")
        self.assertEqual(njiwa_templates.render("   \n  ", self.order), "")
        self.assertEqual(njiwa_templates.render(None, self.order), "")

    def test_a_very_long_message_is_cut_before_whatsapp_refuses_it(self):
        message = njiwa_templates.render("x" * (njiwa_templates.MAX_LENGTH + 500), self.order)
        self.assertEqual(len(message), njiwa_templates.MAX_LENGTH)
        self.assertTrue(message.endswith("…"))

    def test_every_placeholder_the_page_promises_can_be_filled_in(self):
        # The settings page prints this list. Anything on it that the renderer
        # does not answer would reach a customer as a hole in a sentence.
        values = njiwa_templates.values_for(self.order)
        for token in njiwa_templates.placeholders():
            self.assertIn(token, values)

    def test_the_defaults_shipped_with_the_module_render_on_their_own(self):
        # A shop that ticks an event and never opens the wording box still has
        # something to say, and it must not come out with braces in it.
        for event, wording in njiwa_templates.DEFAULTS.items():
            message = njiwa_templates.render(wording, self.order)
            self.assertTrue(message, event)
            self.assertNotIn("{", message, event)
