# Njiwa for Odoo

WhatsApp your customers when their order is confirmed, paid, sent, cancelled or
refunded, and get a message yourself when an order comes in.

The addon is the `njiwa` folder beside this file. Its technical name is
**njiwa**, and it is written for **Odoo 16.0 and 17.0**: every hook, field and
view tag in it was checked against both, and the places where the two versions
differ are named in the code where the difference is handled.

## Install

1. Copy the `njiwa` folder into a directory on your Odoo `addons_path`.
2. Restart Odoo.
3. Turn on developer mode, go to **Apps**, press **Update Apps List**, search
   for **Njiwa** and install it.

It needs Sales, Invoicing and Inventory, and installs them if they are not
there. It needs nothing else: no queue addon, no worker, no third-party
library.

## Set it up

The settings are at **Sales → Configuration → Njiwa (WhatsApp)**.

They are a page of their own rather than a section inside the Settings app, and
that is not a preference: Odoo 16 and Odoo 17 build the Settings page out of
different markup, and one addon cannot install into both. Everything else about
the page is ordinary Odoo.

1. Paste your API key from [console.upeo.ai](https://console.upeo.ai) → API
   keys.
2. Tick **Send WhatsApp messages**. Nothing is sent until you do.
3. Press **Test connection**. Odoo saves the page before it runs, so what you
   have just typed is what is checked. It lists the WhatsApp numbers your Njiwa
   account really has, so you find out now rather than at the moment a customer
   should have been messaged.
4. Put your own number in **Send a test message to** and press **Send test
   message**. That proves the whole path, all the way to a phone in your hand.
5. Tick the events you want and edit the wording.

**Start with a test key.** A key beginning `sk_test_` checks and stores every
message and delivers nothing. Turn on the events you want, confirm a test
order, read the note on it, and only then paste the `sk_live_` key in its
place. From that moment the messages are real and they cost money.

| Setting | What it is for |
| --- | --- |
| Send WhatsApp messages | The master switch. Off keeps every setting and sends nothing. |
| API key | `sk_test_` delivers nothing, `sk_live_` sends for real. |
| Njiwa address | Leave it alone unless you were given your own. |
| Send from | Which of your numbers sends. Empty means the account default. |
| Each event | On, off, and the exact wording. Empty wording sends nothing. |
| Your WhatsApp numbers | Where the new-order message to you goes. Several, comma separated. |

**Save these settings** writes the page, and so does Odoo's own save on it.
Both check buttons save the page before they run, so they always use the
settings you can see.

## What gets sent, and when

| When this happens in Odoo | Who hears about it |
| --- | --- |
| A quotation is confirmed | The customer: we have your order |
| A customer invoice is fully paid | The customer: thank you, nothing more to pay |
| A delivery order going out is validated | The customer: it is on its way |
| A sales order is cancelled | The customer: cancelled, and here is who to ask |
| A credit note is posted | The customer: the money is coming back |
| A quotation is confirmed | You: a new order came in, once |

Each one is off until you turn it on, and each ships wording that works before
anybody edits it.

Three of those are worth spelling out.

**Payment received** is sent when the payment is matched against the invoice
and the invoice is settled in full. A part payment sends nothing: the customer
still owes you, and being thanked for paying is confusing when they have not
finished. An invoice settled by a credit note sends nothing either, because
nobody paid.

**Shipped** is deliveries going out only. A receipt from a supplier and an
internal transfer between your own locations message nobody.

**The message to you** is sent once per order, when the order is confirmed —
not when a quotation is written, so an enquiry that goes nowhere never wakes
you up.

## The wording

Plain text with placeholders in braces. The settings page lists them all with
what each one means; they are `{first_name}`, `{last_name}`,
`{customer_name}`, `{order_number}`, `{order_total}`, `{order_date}`,
`{order_status}`, `{payment_method}`, `{items}`, `{item_count}`,
`{shop_name}`, `{order_url}` and `{admin_url}`.

A placeholder that does not exist, `{order_no}` say, is taken out before
sending rather than shown to a customer, and a line goes in the Odoo log
saying where to look.

**Clearing a box is how you stop one message without turning the event off.**
An empty box sends nothing and writes nothing on the order, whatever the tick
box beside it says: it is a decision rather than a failure, so it is not
reported as one.

Messages go out in the customer's own language where the contact has one, so
the date, the total and the state of the order read the way everything else you
send them reads.

## Things worth knowing

**Confirming an order never waits for WhatsApp.** Confirming writes one small
row to a queue in this addon and returns. A scheduled action, **Njiwa: send
queued WhatsApp messages**, comes along a minute later and does the sending. A
slow network, or Njiwa being down, cannot delay or break a sale. It also means
that if scheduled actions are switched off on your database, nothing goes out;
you would see the queue filling up and nothing leaving it.

This is deliberately not the OCA `queue_job` addon. That is an excellent thing
to have and most databases do not have it, and an addon that needs it would
look installed and quietly send nothing on every database that does not.

**Every send is written on the document.** Open the order, the invoice or the
delivery and the notes say what went where, with Njiwa's message id, or why it
did not. "No WhatsApp message, because this customer has no phone number" shows
up there too, which is the answer to the first question anybody asks.

**The whole queue is at Sales → Configuration → Njiwa messages.** Waiting,
sent, and failed with the reason Njiwa gave.

**Nothing is sent twice.** Each message carries an idempotency key made from
the database, the document, the event and the recipient. If the scheduled
action runs twice, Njiwa replays the first answer instead of messaging the
customer again, and the queue row outlives that: a document that somehow
reaches the same moment twice, months apart, still sends once.

**A message Njiwa never accepted is offered again.** A network failure is not a
send failure, so it is retried for a few minutes and then written off with the
reason on the row. A message Njiwa refused is not retried: it has read it and
said no.

**A message that has waited more than a day is not sent.** A customer told on
Thursday that their Monday order is confirmed learns nothing and wonders what
else is wrong.

**Phone numbers are read as people write them.** `0712345678`,
`+254 712 345 678` and `254712345678` are all understood. The customer's
Mobile is used first, then their Phone, then the same two on the company the
contact belongs to, which is what makes a delivery address with no number of
its own still reach somebody. A customer with no number at all is normal:
nothing is sent, nothing is raised, and the document says so.

Anything that is not a phone number is refused, and one refusal matters more
than the rest: a value ending `@g.us` is a WhatsApp **group**. Njiwa would post
to it, and one confirmed order could message hundreds of people from your own
number.

**Send from is the one place a leading zero is wrong.** A recipient is read
against your sending number's own country, so `0712345678` is fine there. Your
sending number has no other number to be read against, so write it in full:
`254712345678`.

**Who can see the key.** It is stored in Odoo's system parameters, which only a
Settings administrator can read, and the field is marked for that group as
well. A portal user, a customer with a login, and an ordinary salesperson
cannot read it. Everybody in your company can see the message queue, because
knowing whether a customer was told is part of their job; the key is not on it.

**Uninstalling removes the key** and the rest of the Njiwa settings with it. A
live key left behind in a database nobody is looking after is a key nobody is
looking after. The notes on your orders stay, because they are a record of what
was sent and they belong to the order.

## What it does not do

**It does not receive replies.** Inbound WhatsApp arrives as a webhook, and
verifying one needs that number's signing secret, which the console does not
yet show. Until it does, a receiving feature could not check that a request
really came from Njiwa, so there is not one.

**It does not run campaigns.** Bulk sending to past customers is what the Njiwa
console is for, on Business plans and above.

**It does not keep its own copy of your messages.** Njiwa already stores every
message, its status and its failure reason. A second copy is a second thing to
keep in step.

## Running the tests

```bash
odoo -d yourdatabase -i njiwa --test-enable --stop-after-init
```

They cover the number parser, the template renderer, the way the settings are
read back, and the cleared message box that must queue nothing. None of them
sends anything.

---

Docs: https://docs.njiwa.upeo.ai · Console: https://console.upeo.ai
UPEO.AI · hello@upeo.ai · 0116888777 on WhatsApp
