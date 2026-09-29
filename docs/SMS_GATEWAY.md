# Merchant-phone SMS bridge

## What is implemented

The signed server endpoint and a Python relay with a persistent retry queue are implemented. A physical Android device was not available for end-to-end testing. No personal SMS inbox has been read. The local demo uses synthetic messages only.

The relay expects the [official Termux:API SMS inbox representation](https://github.com/termux/termux-api/blob/master/app/src/main/java/com/termux/api/apis/SmsInboxAPI.java): inbox `type`, sender `address` (or legacy `number`), `received`, `body` and `_id`. Its unit test checks exact sender filtering and duplicate suppression. Phone permissions, background execution and sender formatting must be validated on the chosen device.

## Phone setup

1. Use a dedicated merchant Android phone that receives the business's bank notifications. Obtain Termux and Termux:API from compatible official installation sources; follow [Termux:API installation instructions](https://github.com/termux/termux-api).
2. Grant SMS access on that phone only with the merchant's authorization. Install Python and the Termux API command package in Termux. Copy `scripts/phone_bridge.py` to the phone.
3. Configure the same `SMS_SECRET` on phone and server, and set the server's `BANK_SENDER` to the exact sender address the phone reports. Do not commit keys or include them in a demo video.
4. Configure an HTTPS endpoint on your own server. The provided local application is not automatically exposed to the internet.
5. Run the relay using the chosen URL and sender:

```bash
python phone_bridge.py --url https://YOUR-OWN-HOST --sender YOUR-BANK-SENDER --watch
```

The secret is read from the process environment. Configure the phone's own process supervision/wake behavior according to its Android version, then verify recovery after reboot and network loss. The script polls the most recent 1,000 inbox messages every 20 seconds and uses an on-disk queue. This bounded poll can miss messages after a long outage or heavy inbox traffic; use an Android SMS receiver plus a proper durable cursor/service for production.

## Reliability behavior

- Only exact allowlisted inbox senders are queued. Personal messages are ignored.
- Events are committed locally before delivery. Failed requests remain pending.
- Stable event identity makes lost responses safe: the server recognises redelivery.
- Request signatures use a fresh transport timestamp for every retry.
- HTTP is permitted only to localhost; use HTTPS for device-to-server transport.
- Rejected requests remain queued and print a generic warning; inspect configuration and parser issues instead of discarding evidence. A production outbox needs retry backoff, dead-letter handling and alerting.

## Trust boundaries

Gateway authentication is not bank authentication. SMS sender spoofing, device compromise, delivery loss, reversals and inadequate order attribution remain possible. Bank statement reconciliation and device management are required before real automatic fulfilment. A masked SMS account is deliberately not expanded to the full account, and a missing transaction date is not invented from the phone receipt time.

The browser's **Simulate bank SMS** button exists only in demo mode and is visibly labelled. Never enable that simulator on a real payment workspace.
