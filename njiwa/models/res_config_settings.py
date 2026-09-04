"""The settings page.

Every field carries its own description, because a setting whose meaning has to
be looked up somewhere else is a setting people get wrong.

Everything is stored in ir.config_parameter, which Odoo keeps for the Settings
administrator, and the API key is additionally marked base.group_system so that
it is not in the form at all for anybody else. This whole model is already
administrator-only; the marking is there for the day somebody grants a wider
group access to settings and does not think about what is on the page.

The page is its own form under Sales, Configuration, rather than a block inside
the Settings app. That is not a preference. Odoo 16 builds that page out of
<div class="app_settings_block"> inside <div class="settings">, and Odoo 17
builds it out of <app>, <block> and <setting> tags placed directly in the form;
a single module cannot inherit both, and a module that inherits the wrong one
does not install at all.

Being its own form has one consequence worth knowing before reading further. A
res.config.settings record is applied by execute(), which the Settings app's
own Save button calls and the save control on a plain form does not, so this
model applies itself in create() when the record comes from this page. Without
that, the save Odoo has trained everybody to press would throw away the key
they had just pasted.
"""

import time

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from . import njiwa_client, njiwa_config, njiwa_numbers, njiwa_templates

# What a shop may press "Send test message" for. Far more than a person
# checking their setup needs, far less than a mistake left running could use.
TEST_SENDS_AN_HOUR = 10


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    njiwa_enabled = fields.Boolean(
        string="Send WhatsApp messages",
        config_parameter=njiwa_config.P_ENABLED,
        help="The master switch. Until this is on, nothing is sent, whatever else is "
        "ticked below. Turning it off later keeps your key, your numbers and your "
        "wording, and orders carry on exactly as before.",
    )
    njiwa_api_key = fields.Char(
        string="API key",
        config_parameter=njiwa_config.P_API_KEY,
        groups="base.group_system",
        help="Create one in the Njiwa console under API keys, then paste it here. A key "
        "beginning sk_test_ checks and stores every message and delivers nothing, which "
        "is what you want while you set this up. A key beginning sk_live_ sends to real "
        "phones and costs money. The console shows a key once and keeps only its "
        "fingerprint, so a lost key is replaced rather than recovered.",
    )
    njiwa_base_url = fields.Char(
        string="Njiwa address",
        config_parameter=njiwa_config.P_BASE_URL,
        default=njiwa_config.DEFAULT_BASE_URL,
        help="Leave this exactly as it is. It exists for shops that have been given their "
        "own Njiwa address, and changing it otherwise stops messages reaching anybody.",
    )
    njiwa_from_number = fields.Char(
        string="Send from",
        config_parameter=njiwa_config.P_FROM_NUMBER,
        help="Which of your linked WhatsApp numbers these messages come from. Digits only, "
        "in full international form, such as 254712345678. Leave it empty to use the "
        "number marked default in the console, which is the right answer if you have one "
        "number.",
    )
    njiwa_alert_numbers = fields.Char(
        string="Your WhatsApp numbers",
        config_parameter=njiwa_config.P_ALERT_NUMBERS,
        help="Where the new-order message to you goes. Full international form, separated "
        "by commas if there are several. Everybody listed gets their own copy.",
    )

    njiwa_event_order_placed = fields.Boolean(
        string="Order confirmed",
        config_parameter=njiwa_config.P_EVENT % "order_placed",
        help="Sent when a quotation is confirmed and becomes a sales order. Not when the "
        "quotation is written, which happens while you are still talking about it.",
    )
    njiwa_message_order_placed = fields.Text(
        string="Wording, order confirmed",
        config_parameter=njiwa_config.P_MESSAGE % "order_placed",
    )

    njiwa_event_payment_received = fields.Boolean(
        string="Payment received",
        config_parameter=njiwa_config.P_EVENT % "payment_received",
        help="Sent when a customer invoice is fully paid, at the moment the payment is "
        "matched against it. A part payment sends nothing: the customer still owes you, "
        "and being thanked for paying is confusing when they have not finished.",
    )
    njiwa_message_payment_received = fields.Text(
        string="Wording, payment received",
        config_parameter=njiwa_config.P_MESSAGE % "payment_received",
    )

    njiwa_event_shipped = fields.Boolean(
        string="Shipped",
        config_parameter=njiwa_config.P_EVENT % "shipped",
        help="Sent when a delivery order is validated. Only deliveries going out: a receipt "
        "from a supplier and an internal transfer message nobody.",
    )
    njiwa_message_shipped = fields.Text(
        string="Wording, shipped",
        config_parameter=njiwa_config.P_MESSAGE % "shipped",
    )

    njiwa_event_order_cancelled = fields.Boolean(
        string="Order cancelled",
        config_parameter=njiwa_config.P_EVENT % "order_cancelled",
        help="Worth sending. A cancellation nobody explained is what turns into a phone call.",
    )
    njiwa_message_order_cancelled = fields.Text(
        string="Wording, order cancelled",
        config_parameter=njiwa_config.P_MESSAGE % "order_cancelled",
    )

    njiwa_event_refunded = fields.Boolean(
        string="Refunded",
        config_parameter=njiwa_config.P_EVENT % "refunded",
        help="Sent when you post a credit note for a customer. Saying so stops the "
        "\"where is my refund\" message before it is sent.",
    )
    njiwa_message_refunded = fields.Text(
        string="Wording, refunded",
        config_parameter=njiwa_config.P_MESSAGE % "refunded",
    )

    njiwa_event_new_order = fields.Boolean(
        string="Tell me about new orders",
        config_parameter=njiwa_config.P_EVENT % njiwa_config.OWNER_EVENT,
        help="One message to you when an order becomes real, which is when it is confirmed. "
        "Not when a quotation is written, so an enquiry that goes nowhere never wakes you up.",
    )
    njiwa_message_new_order = fields.Text(
        string="Wording, the message to you",
        config_parameter=njiwa_config.P_MESSAGE % "new_order",
    )

    njiwa_test_number = fields.Char(
        string="Send a test message to",
        help="Your own WhatsApp number. Digits, written how you like: 254712345678, "
        "+254 712 345 678 and 0712345678 are all read correctly. Nothing is stored here.",
    )
    njiwa_placeholders = fields.Text(
        string="Placeholders", readonly=True, compute="_compute_njiwa_placeholders"
    )

    # ------------------------------------------------------- reading it back

    @api.depends_context("lang")
    def _compute_njiwa_placeholders(self):
        """The list on the page is built from the code that does the replacing.

        Written out here rather than typed into the view, so the page cannot
        promise a placeholder the renderer does not have.
        """
        listing = "\n".join(
            "%s  %s" % (token.ljust(18), meaning)
            for token, meaning in njiwa_templates.placeholders().items()
        )
        for settings in self:
            settings.njiwa_placeholders = listing

    def get_values(self):
        """Show exactly what would be sent.

        The wording and the address are read through the same functions the
        sending code uses, rather than through get_param, because get_param
        cannot tell a box somebody cleared on purpose from one nobody has ever
        touched, and the difference between those two is whether a message goes
        out at all.
        """
        values = super().get_values()
        values["njiwa_base_url"] = njiwa_config.base_url(self.env)
        for event, _label in njiwa_config.ALL_EVENTS:
            values["njiwa_message_%s" % event] = njiwa_config.message(self.env, event)
        return values

    def set_values(self):
        """Save, including the boxes somebody deliberately emptied.

        Odoo stores an emptied setting by deleting the parameter, and a deleted
        parameter reads back as "never configured", which would put the wording
        this module ships back in front of a shop that had just taken it out.
        The wording is therefore written here, blank included, as the single
        space ir_config_parameter can hold.
        """
        super().set_values()
        self._njiwa_save_wording()

    def _njiwa_save_wording(self):
        parameters = self.env["ir.config_parameter"].sudo()
        for event, _label in njiwa_config.ALL_EVENTS:
            wording = self["njiwa_message_%s" % event] or ""
            parameters.set_param(
                njiwa_config.P_MESSAGE % event, wording.strip() or njiwa_config.BLANK
            )

    # ---------------------------------------------------------- writing it

    @api.model_create_multi
    def create(self, vals_list):
        """Odoo's own save on this page writes the Njiwa parameters too.

        A res.config.settings record is only applied when execute() is called,
        which is what the Save button of the Settings app does. This page is a
        form of its own, so the save control the web client puts on it writes
        the transient record and nothing else, and Odoo has trained everybody
        to press that control: somebody who pasted their key, ticked the switch
        and pressed it would have thrown the key away, and then be told by Test
        connection that there is no key saved. Odoo also saves a form before it
        runs a button on it, so this is what makes the two check buttons look
        at the settings that are on the screen.

        Only records created from this page are applied, which the context of
        the menu action says. The Settings app builds its own res.config.settings
        records, they never show these fields, and they are left alone.
        """
        settings = super().create(vals_list)
        if self.env.context.get("module") == "njiwa":
            for record in settings:
                record._njiwa_apply()
        return settings

    def _njiwa_apply(self):
        """Write the Njiwa settings, and only the Njiwa settings.

        This page is a page of its own, so it writes its own parameters rather
        than calling the general Save, which would write back every setting of
        every other app from a form that never showed them.
        """
        self.ensure_one()
        self._njiwa_only_admin()

        parameters = self.env["ir.config_parameter"].sudo()

        sender = "".join(character for character in (self.njiwa_from_number or "") if character.isdigit())
        if self.njiwa_from_number and not sender:
            raise UserError(
                _("Send from is not a phone number. Write it as digits, like 254712345678, "
                  "or leave it empty to use the number marked default in the console.")
            )
        if sender.startswith("0"):
            # A leading zero is fine on a recipient, which Njiwa reads against
            # the sending number's own country. It is not fine here, where
            # there is no other number to read it against.
            raise UserError(
                _("Send from must be the number in full international form, without the "
                  "leading zero: 254712345678 rather than 0712345678.")
            )

        alerts = self.njiwa_alert_numbers or ""
        if alerts.strip() and not njiwa_numbers.parse_list(alerts):
            raise UserError(
                _("None of the numbers in \"Your WhatsApp numbers\" is a phone number. Write "
                  "them in full international form, separated by commas.")
            )

        parameters.set_param(njiwa_config.P_ENABLED, "True" if self.njiwa_enabled else False)
        parameters.set_param(njiwa_config.P_API_KEY, (self.njiwa_api_key or "").strip() or False)
        parameters.set_param(
            njiwa_config.P_BASE_URL,
            (self.njiwa_base_url or "").strip().rstrip("/") or False,
        )
        parameters.set_param(njiwa_config.P_FROM_NUMBER, sender or False)
        parameters.set_param(njiwa_config.P_ALERT_NUMBERS, alerts.strip() or False)

        for event, _label in njiwa_config.ALL_EVENTS:
            parameters.set_param(
                njiwa_config.P_EVENT % event,
                "True" if self["njiwa_event_%s" % event] else False,
            )
        self._njiwa_save_wording()

    # --------------------------------------------------------- the buttons

    def action_njiwa_save(self):
        """The button, which saves and then says so.

        Odoo has already saved the form by the time this runs, so the writing
        is done twice with the same values. What the button adds is the plain
        answer that it worked, which a settings page nobody has used before
        needs more than it needs one fewer write.
        """
        self.ensure_one()
        self._njiwa_apply()

        return self._njiwa_says(
            _("Saved."),
            _("These settings are what the scheduled action will use from now on."),
        )

    def action_njiwa_test_connection(self):
        """Who this key belongs to, and what it can send from. Sends nothing."""
        self.ensure_one()
        self._njiwa_only_admin()

        found = njiwa_client.instances(self.env)

        lines = []
        if njiwa_config.is_test_key(self.env):
            lines.append(
                _("This is a test key. Every message is checked and stored, and nothing "
                  "reaches WhatsApp. Swap it for a key beginning sk_live_ when you are ready.")
            )

        if not found:
            lines.append(
                _("The key works, but this account has no numbers yet. Add one in the Njiwa "
                  "console under Numbers and link it.")
            )
        else:
            lines.append(_("Connected. This key can send from:"))
            for number in found:
                lines.append(
                    "%s  %s  %s%s"
                    % (
                        number.get("label") or number.get("id") or "",
                        "+%s" % number["msisdn"] if number.get("msisdn") else _("not linked yet"),
                        number.get("status") or "",
                        _("  (default)") if number.get("is_default") else "",
                    )
                )

        sender = njiwa_config.from_number(self.env)
        if sender and sender not in [number.get("msisdn") for number in found]:
            lines.append(
                _("Send from is set to %s and no number on this account matches it, so every "
                  "message will be refused. Correct it, or clear it to use the default "
                  "number above.") % sender
            )

        return self._njiwa_says(_("Njiwa answered"), "\n".join(lines))

    def action_njiwa_send_test_message(self):
        """One fixed message to one number you name.

        Test connection proves the key. This proves the rest of the path, all
        the way to a phone in somebody's hand. The wording is written here and
        the operator supplies the recipient and nothing else, so the button
        cannot be talked into saying something it should not.
        """
        self.ensure_one()
        self._njiwa_only_admin()
        self._njiwa_rate_limit()

        # A leading zero is accepted here on purpose. It is refused for the
        # sending number, where the country really is ambiguous, but a
        # recipient is read against the sending number's own country, so
        # 0712345678 is a number this button should send to rather than argue
        # about. What is refused is anything that is not a phone number at all,
        # a JID ending @g.us above everything: Njiwa reads one of those as a
        # WhatsApp group, and one press would post to hundreds of people from
        # the shop's own number.
        number = njiwa_numbers.to_msisdn(self.njiwa_test_number)
        if not number:
            raise UserError(
                _("%(typed)s is not a phone number. Write it as digits, %(least)s to "
                  "%(most)s of them, like 254712345678 or 0712345678.")
                % {
                    "typed": self.njiwa_test_number or "",
                    "least": njiwa_numbers.MIN_MSISDN_DIGITS,
                    "most": njiwa_numbers.MAX_MSISDN_DIGITS,
                }
            )

        answer = njiwa_client.send_text(
            self.env,
            number,
            _("Test message from %s. If you can read this, Odoo can reach your customers "
              "on WhatsApp.") % self.env.company.name,
        )

        told = _("Sent to +%(number)s (%(message_id)s).") % {
            "number": number,
            "message_id": answer.get("id") or "?",
        }
        if njiwa_config.is_test_key(self.env):
            told += "\n" + _("This is a test key, so nothing actually reached the phone.")

        return self._njiwa_says(_("Njiwa answered"), told)

    # --------------------------------------------------------------- guards

    def _njiwa_only_admin(self):
        """These buttons read the API key and one of them spends money."""
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only a Settings administrator can change or test Njiwa."))

    def _njiwa_rate_limit(self):
        """A ceiling on the button that actually sends.

        Ten an hour is far more than somebody checking their setup needs. The
        times are kept in a parameter rather than in memory because Odoo runs
        in several processes, and a limit one worker knows about is not a
        limit.
        """
        parameters = self.env["ir.config_parameter"].sudo()
        now = int(time.time())
        recent = [
            int(stamp)
            for stamp in (njiwa_config.raw(self.env, njiwa_config.P_TEST_SENDS) or "").split()
            if stamp.isdigit() and now - int(stamp) < 3600
        ]
        if len(recent) >= TEST_SENDS_AN_HOUR:
            raise UserError(
                _("That is %s test messages in an hour, which is enough to be a mistake. "
                  "Wait a while, or place a real order to test the events themselves.")
                % TEST_SENDS_AN_HOUR
            )
        parameters.set_param(
            njiwa_config.P_TEST_SENDS, " ".join(str(stamp) for stamp in recent + [now])
        )

    @api.model
    def _njiwa_says(self, title, message):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "sticky": True,
                "type": "info",
            },
        }
