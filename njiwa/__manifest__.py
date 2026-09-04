{
    "name": "Njiwa: WhatsApp for your customers",
    "summary": "WhatsApp a customer when their order is confirmed, paid, sent, "
               "cancelled or refunded, and get a message yourself when an order comes in.",
    "description": """
Njiwa sends the WhatsApp messages. Odoo tells it when.

Six moments, each off until somebody turns it on, each with wording that works
before anybody edits it:

* a sales order is confirmed, and the customer is told it is in;
* a customer invoice is paid, and the customer is thanked;
* a delivery is validated, and the customer is told it is on its way;
* a sales order is cancelled, and the customer hears it from you;
* a credit note is posted, and the customer is told the money is coming back;
* and one message to you, once, when an order becomes real.

Nothing is sent from the request that confirmed the order. Messages are written
to a small queue in this module and sent a minute later by a scheduled action,
so Njiwa being slow can never delay or break a sale, and so the module needs
nothing installed beside it.

Settings live under Sales, Configuration, Njiwa.
""",
    "author": "UPEO.AI",
    "website": "https://njiwa.upeo.ai",
    "license": "LGPL-3",
    "category": "Sales/Sales",
    # No series in front of it, on purpose. Odoo puts its own there when it
    # reads this file, so one module installs on 16.0 and on 17.0 and calls
    # itself 16.0.1.0.0 or 17.0.1.0.0 accordingly.
    "version": "1.0.0",
    "depends": [
        "base",
        # Every model this module listens to is a mail thread, and every note
        # it writes about a message it sent is a note on that thread.
        "mail",
        "sale",
        "account",
        "stock",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/njiwa_cron.xml",
        "views/njiwa_pending_send_views.xml",
        "views/res_config_settings_views.xml",
    ],
    # Removing the module removes the API key. See hooks.py.
    "uninstall_hook": "uninstall_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
