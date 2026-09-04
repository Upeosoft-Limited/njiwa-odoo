"""What a number field can hold, and what may be sent to.

The last test in the first class is the one that matters most. A value ending
@g.us is a WhatsApp group, and Njiwa posts to one without looking at the rest
of it: a partner record holding a group would turn one confirmed order into a
message to hundreds of people from the shop's own number.
"""

from odoo.tests import TransactionCase, tagged

from odoo.addons.njiwa.models import njiwa_numbers


@tagged("post_install", "-at_install")
class TestNumberParser(TransactionCase):
    def test_a_number_written_in_full_is_left_alone(self):
        self.assertEqual(njiwa_numbers.to_msisdn("254712345678"), "254712345678")

    def test_punctuation_comes_off_rather_than_the_number_being_refused(self):
        self.assertEqual(njiwa_numbers.to_msisdn("+254 712 345 678"), "254712345678")
        self.assertEqual(njiwa_numbers.to_msisdn("(254) 712-345-678"), "254712345678")
        self.assertEqual(njiwa_numbers.to_msisdn("254.712.345.678"), "254712345678")

    def test_dialling_out_with_00_is_the_same_number(self):
        self.assertEqual(njiwa_numbers.to_msisdn("00254712345678"), "254712345678")

    def test_a_leading_zero_is_passed_through_for_njiwa_to_read(self):
        # Njiwa reads a local number against the sending number's own country,
        # which is the same answer somebody who knows would give.
        self.assertEqual(njiwa_numbers.to_msisdn("0712345678"), "0712345678")

    def test_nothing_usable_is_nothing_sent(self):
        self.assertEqual(njiwa_numbers.to_msisdn(""), "")
        self.assertEqual(njiwa_numbers.to_msisdn(None), "")
        self.assertEqual(njiwa_numbers.to_msisdn("ask at the desk"), "")
        self.assertEqual(njiwa_numbers.to_msisdn("12345"), "")
        self.assertEqual(njiwa_numbers.to_msisdn("2547123456789012345"), "")

    def test_a_whatsapp_group_is_never_a_recipient(self):
        self.assertEqual(njiwa_numbers.to_msisdn("120363028712345678@g.us"), "")
        self.assertEqual(njiwa_numbers.to_msisdn("254712345678@s.whatsapp.net"), "")
        self.assertEqual(njiwa_numbers.parse_list("120363028712345678@g.us"), [])

    def test_two_numbers_in_one_box_use_the_first(self):
        self.assertEqual(njiwa_numbers.first_msisdn("254712345678 / 254733000111"), "254712345678")
        self.assertEqual(njiwa_numbers.first_msisdn("no phone, 254733000111"), "254733000111")

    def test_a_list_keeps_its_order_and_drops_the_rest(self):
        self.assertEqual(
            njiwa_numbers.parse_list("254712345678, 254733000111; nothing\n254712345678"),
            ["254712345678", "254733000111"],
        )


@tagged("post_install", "-at_install")
class TestPartnerNumber(TransactionCase):
    def test_mobile_first_then_phone(self):
        partner = self.env["res.partner"].create(
            {"name": "Amina Wanjiru", "phone": "254700000000", "mobile": "0712 345 678"}
        )
        self.assertEqual(njiwa_numbers.for_partner(partner), "0712345678")

        partner.mobile = False
        self.assertEqual(njiwa_numbers.for_partner(partner), "254700000000")

    def test_a_delivery_address_falls_back_to_the_customer(self):
        company = self.env["res.partner"].create(
            {"name": "Mama Shop Ltd", "is_company": True, "mobile": "254712345678"}
        )
        warehouse = self.env["res.partner"].create(
            {"name": "Mama Shop, back gate", "parent_id": company.id, "type": "delivery"}
        )
        self.assertEqual(njiwa_numbers.for_partner(warehouse), "254712345678")

    def test_no_number_is_normal_and_raises_nothing(self):
        partner = self.env["res.partner"].create({"name": "Walk-in customer"})
        self.assertEqual(njiwa_numbers.for_partner(partner), "")
        self.assertEqual(njiwa_numbers.for_partner(self.env["res.partner"]), "")
