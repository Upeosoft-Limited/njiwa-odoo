"""Reading the settings back, which is subtler than it looks.

get_param() ends in `or default`, so a message box somebody cleared on purpose
would come back as the wording this module ships and carry on sending. These
are the tests that hold that shut.
"""

from odoo.tests import TransactionCase, tagged

from odoo.addons.njiwa.models import njiwa_config, njiwa_templates


@tagged("post_install", "-at_install")
class TestSettingsAreReadBack(TransactionCase):
    def test_nothing_is_sent_until_somebody_turns_it_on(self):
        self.assertFalse(njiwa_config.enabled(self.env))
        for event, _label in njiwa_config.ALL_EVENTS:
            self.assertFalse(njiwa_config.event_on(self.env, event), event)

    def test_a_switch_stored_as_the_word_false_is_off(self):
        # bool("False") is True. This is the test that says so.
        self.env["ir.config_parameter"].sudo().set_param(njiwa_config.P_ENABLED, "False")
        self.assertFalse(njiwa_config.enabled(self.env))

        self.env["ir.config_parameter"].sudo().set_param(njiwa_config.P_ENABLED, "True")
        self.assertTrue(njiwa_config.enabled(self.env))

    def test_wording_nobody_has_touched_is_the_wording_we_ship(self):
        self.assertEqual(
            njiwa_config.message(self.env, "order_placed"),
            njiwa_templates.default_for("order_placed"),
        )

    def test_a_box_that_was_cleared_stays_cleared(self):
        self.env["ir.config_parameter"].sudo().set_param(
            njiwa_config.P_MESSAGE % "order_placed", njiwa_config.BLANK
        )
        self.assertEqual(njiwa_config.message(self.env, "order_placed"), "")

    def test_wording_somebody_typed_is_what_comes_back(self):
        self.env["ir.config_parameter"].sudo().set_param(
            njiwa_config.P_MESSAGE % "shipped", "It has gone out, {first_name}."
        )
        self.assertEqual(
            njiwa_config.message(self.env, "shipped"), "It has gone out, {first_name}."
        )

    def test_the_address_defaults_to_njiwa(self):
        self.assertEqual(njiwa_config.base_url(self.env), njiwa_config.DEFAULT_BASE_URL)
        self.env["ir.config_parameter"].sudo().set_param(
            njiwa_config.P_BASE_URL, "https://njiwa.example.com/"
        )
        self.assertEqual(njiwa_config.base_url(self.env), "https://njiwa.example.com")


@tagged("post_install", "-at_install")
class TestSettingsPageWrites(TransactionCase):
    def test_saving_an_empty_box_does_not_bring_the_default_back(self):
        settings = self.env["res.config.settings"].create({})
        settings.njiwa_message_shipped = ""
        settings._njiwa_save_wording()
        self.assertEqual(njiwa_config.message(self.env, "shipped"), "")

    def test_the_page_shows_what_would_be_sent(self):
        values = self.env["res.config.settings"].get_values()
        self.assertEqual(
            values["njiwa_message_refunded"], njiwa_templates.default_for("refunded")
        )
        self.assertEqual(values["njiwa_base_url"], njiwa_config.DEFAULT_BASE_URL)
