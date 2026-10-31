"""UPIResolve AI - core logic. Plain Python, no LLM, no extra dependencies.

respond(text) -> str   is the only function the Agentverse chat handler needs.
"""
import re
from datetime import date, timedelta

SOURCE = "RBI circular DPSS.CO.PD No.629/02.01.014/2019-20 (20 Sep 2019), UPI rows 4a/4b"
SOURCE_URL = "https://www.rbi.org.in/Scripts/NotificationUser.aspx?Id=11693"
LAST_CHECKED = "31 Oct 2026"

SAFETY = ("Never share your UPI PIN, OTP or banking password with anyone, including me. "
          "Banks, UPI apps and NPCI do not need them to process a refund or complaint.")

# Verified against the RBI circular above. T = calendar date of the transaction.
RULES = {
    "p2p": {
        "title": "Money debited but not credited (transfer to a person)",
        "tat": 1,
        "outcome": "the beneficiary was not credited",
    },
    "merchant": {
        "title": "Money debited but merchant got no confirmation (merchant payment)",
        "tat": 5,
        "outcome": "the merchant did not receive confirmation",
    },
    # Customer error is not a 'failed transaction' under the circular (my reading).
    # Recovery steps are from secondary sources - verify on NPCI's page.
    "wrong": {
        "title": "Money sent to the wrong UPI ID (customer error)",
        "tat": None,
        "outcome": "the money went to a wrong recipient",
    },
}

ESCALATION = [
    "Raise a complaint on that transaction inside your UPI app (Help / Dispute).",
    "Contact your bank's customer care or grievance cell and quote the complaint reference.",
    "If unresolved, file on NPCI's UPI Dispute Redressal Mechanism page "
    "(npci.org.in > What we do > UPI > Dispute Redressal Mechanism).",
    "If still unresolved, complain under the RBI Integrated Ombudsman Scheme.",
]

EVIDENCE = [
    "UTR / UPI transaction ID",
    "Screenshot of the failed or pending payment screen",
    "Debit SMS or the bank statement line",
    "Date, time and amount",
    "Receiver's UPI ID, phone number or merchant name",
]


def unsafe(text: str) -> bool:
    """True if the user seems to be pasting a PIN / OTP / password."""
    t = text.lower()
    return bool(re.search(r"\b(pin|otp|password|cvv)\b", t) and re.search(r"\b\d{4,8}\b", t))


def classify(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("wrong", "mistake", "incorrect upi", "wrong number")):
        return "wrong"
    if any(w in t for w in ("merchant", "shop", "store", "order", "bill", "recharge",
                            "restaurant", "swiggy", "zomato", "amazon", "flipkart")):
        return "merchant"
    return "p2p"


def parse_date(text: str, today: date):
    t = text.lower()
    if "today" in t:
        return today
    if "yesterday" in t:
        return today - timedelta(days=1)
    m = re.search(r"(\d+)\s*days?\s*ago", t)
    if m:
        return today - timedelta(days=int(m.group(1)))
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", t)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else today.year
        y += 2000 if y < 100 else 0
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return None


def parse_amount(text: str):
    m = re.search(r"(?:₹|rs\.?|inr)\s*([\d,]+)", text.lower()) or \
        re.search(r"([\d,]{3,})\s*(?:rupees|rs\b)", text.lower())
    return int(m.group(1).replace(",", "")) if m else None


def timeline(kind: str, txn: date, today: date):
    """Return (deadline, days_late, owed_rupees). Wrong-recipient has no TAT."""
    tat = RULES[kind]["tat"]
    if tat is None:
        return None, 0, 0
    deadline = txn + timedelta(days=tat)
    late = max(0, (today - deadline).days)
    return deadline, late, 100 * late


def respond(text: str, today: date = None) -> str:
    today = today or date.today()

    if unsafe(text):
        return ("STOP - it looks like you shared a PIN, OTP or password. Do not send those to "
                "anyone. Please ignore that message, and if it was real, change it in your bank app.\n\n"
                + SAFETY)

    kind = classify(text)
    txn = parse_date(text, today)
    if txn is None:
        return ("When did the payment happen? Reply like 'yesterday', '3 days ago' or '28/10'. "
                "Add the amount too (e.g. Rs 5000).\n\n" + SAFETY)

    r = RULES[kind]
    amt = parse_amount(text)
    amt_s = f"Rs {amt:,}" if amt else "Rs <amount>"
    deadline, late, owed = timeline(kind, txn, today)

    out = [f"SITUATION: {r['title']}"]

    if deadline:
        out.append(f"RBI limit: reversal by T+{r['tat']} = {deadline:%d %b %Y}.")
        if late == 0:
            out.append("Status: still inside the limit. Check the status in your UPI app; "
                       "if it is not reversed by the date above, escalate (steps below).")
        else:
            out.append(f"Status: OVERDUE by {late} day(s). Compensation owed so far: Rs {owed} "
                       f"(Rs 100/day). RBI says it must be credited automatically, "
                       f"without you asking. If it is not, say so in your complaint.")
    else:
        out.append("There is no automatic reversal or compensation for a wrong-recipient "
                   "payment, and recovery is not guaranteed. Raise it with your bank and "
                   "UPI app as soon as possible.")

    out.append("\nDO THIS, IN ORDER:")
    out += [f"{i}. {s}" for i, s in enumerate(ESCALATION, 1)]

    out.append("\nKEEP READY:")
    out += [f"- {e}" for e in EVIDENCE]

    out.append("\nCOMPLAINT DRAFT:")
    out.append(
        f"Subject: UPI transaction issue - request for reversal (UTR: <your UTR>)\n"
        f"On {txn:%d %b %Y} I made a UPI payment of {amt_s}. The amount was debited but "
        f"{r['outcome']}."
        + (f" As per RBI circular DPSS.CO.PD No.629/02.01.014/2019-20, reversal is due by "
           f"T+{r['tat']} and Rs 100 per day is payable for any delay beyond it. Please reverse "
           f"the amount and pay the applicable compensation." if deadline else
           " Please help me request a return of the amount through the dispute mechanism.")
        + "\nRegards, <your name>"
    )

    out.append(f"\nSource: {SOURCE} ({SOURCE_URL}). Rules last checked {LAST_CHECKED}. "
               "General guidance, not legal advice.")
    out.append(SAFETY)
    return "\n".join(out)


# ---------------- Agentverse chat handler ----------------
from datetime import datetime as _dt, timezone as _tz
from uuid import uuid4
from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

agent = Agent()
chat_proto = Protocol(spec=chat_protocol_spec)

WELCOME = (
    "Hi, I'm UPIResolve AI. Tell me what happened with your UPI payment and I'll give you "
    "the RBI deadline, any compensation owed, what evidence to keep, and where to complain.\n\n"
    "Example: 'My Rs 5000 UPI transfer failed 3 days ago, money debited but the receiver did not get it.'\n\n"
    + SAFETY
)


def make_reply(text: str) -> ChatMessage:
    return ChatMessage(
        timestamp=_dt.now(_tz.utc),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=text)],
    )


@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=_dt.now(_tz.utc), acknowledged_msg_id=msg.msg_id),
    )
    user_text = ""
    for item in msg.content:
        if isinstance(item, StartSessionContent):
            await ctx.send(sender, make_reply(WELCOME))
        elif isinstance(item, TextContent):
            user_text += item.text + " "
    if user_text.strip():
        await ctx.send(sender, make_reply(respond(user_text)))


@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    pass


agent.include(chat_proto, publish_manifest=True)
