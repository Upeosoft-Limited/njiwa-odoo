"""Removing the module removes the key.

A live API key left in ir_config_parameter after somebody uninstalled the
module is a key nobody is looking after any more. The notes on the orders stay,
because they are a record of what was sent and they belong to the order rather
than to us.
"""

from odoo import SUPERUSER_ID, api


def uninstall_hook(cr_or_env, registry=None):
    """Take every Njiwa setting out of ir_config_parameter, the key first.

    Odoo 16 hands an uninstall hook a cursor and the registry; Odoo 17 hands it
    an environment. Both are accepted here, so one module serves both without a
    second copy of this file.
    """
    env = (
        cr_or_env
        if isinstance(cr_or_env, api.Environment)
        else api.Environment(cr_or_env, SUPERUSER_ID, {})
    )
    env["ir.config_parameter"].sudo().search([("key", "=like", "njiwa.%")]).unlink()
