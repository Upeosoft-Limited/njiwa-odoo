"""Turning what somebody typed into a number WhatsApp can reach.

People write a number the way they say it: 0712 345 678, (071) 234-5678,
+254 712 345 678. WhatsApp needs one form, so the punctuation comes off rather
than the number being refused for having it.

Nothing here guesses a country. A WooCommerce order carries a billing country
and can; an Odoo partner carries one that is often the company's own, and a
delivery address inherits it from the parent. Njiwa already reads a local
number against the sending number's own country, which is the same answer
arrived at by somebody who knows, so a leading zero is passed through as typed
instead.
"""

import re

# How long an msisdn is, taken from Njiwa's own normalisation. The settings
# page repeats these for the test button, so that button refuses a number for
# the same reason the API would.
MIN_MSISDN_DIGITS = 7
MAX_MSISDN_DIGITS = 15

# How a number is written down, and nothing else. A full stop is in here
# because people type 0712.345.678.
PUNCTUATION = re.compile(r"[\s+()\-.]")

# What separates one number from the next when somebody has typed several.
SEPARATORS = re.compile(r"[,;/\n\r]+")


def to_msisdn(raw):
    """One number, digits only, or '' when there is nothing usable.

    Everything that is not a phone number comes back empty, and that includes
    the one value that matters most: a JID ending @g.us is a WhatsApp *group*,
    and Njiwa reads it as one without looking at the rest. A partner's Mobile
    field holding a group would turn one confirmed order into a message to
    hundreds of people from the shop's own number, so nothing but digits is
    ever allowed through.
    """
    number = PUNCTUATION.sub("", str(raw or ""))
    if not number:
        return ""

    # 00 is how much of the world dials out, and what is left is the whole
    # international number.
    if number.startswith("00"):
        number = number[2:]

    if not re.fullmatch(r"[0-9]+", number):
        return ""
    if not MIN_MSISDN_DIGITS <= len(number) <= MAX_MSISDN_DIGITS:
        return ""

    return number


def first_msisdn(raw):
    """The first usable number in a field somebody has put several in.

    A partner's Mobile is one box, and people put two numbers in it:
    "0712345678 / 0722000111", or the same with a comma. Stripping the
    punctuation out of that and sending what is left would dial a number that
    belongs to nobody, so the field is split first and the first number that
    survives is the one used.
    """
    for piece in SEPARATORS.split(str(raw or "")):
        number = to_msisdn(piece)
        if number:
            return number
    return ""


def parse_list(raw):
    """Several numbers typed by the shop owner, in the order they typed them.

    Separated by commas, semicolons, slashes or lines. Anything that is not a
    number is dropped rather than sent to, and a number typed twice is sent to
    once.
    """
    found = []
    for piece in SEPARATORS.split(str(raw or "")):
        number = to_msisdn(piece)
        if number and number not in found:
            found.append(number)
    return found


def for_partner(partner):
    """The number to send to, or '' when this customer has none.

    Mobile first, then Phone, because a mobile is the one that has WhatsApp on
    it and a landline never will. When the contact on the document has neither,
    the company it belongs to is worth asking: a delivery address is often a
    warehouse record with no number of its own, while the customer it hangs
    under has the number the shop would actually ring.

    A partner with no number at all is normal. It is not an error and nothing
    here raises.
    """
    if not partner:
        return ""

    candidates = [partner.mobile, partner.phone]

    company = partner.commercial_partner_id
    if company and company != partner:
        candidates += [company.mobile, company.phone]

    for candidate in candidates:
        number = first_msisdn(candidate)
        if number:
            return number

    return ""
