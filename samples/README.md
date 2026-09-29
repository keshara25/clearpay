# Synthetic samples

`upload-demo.png` and its `.sms.txt` companion were generated for the live development demonstration. They do not describe a real bank payment. Their order code belongs to that demo workspace, so do not expect them to approve against a newly created order.

For a repeatable fresh demonstration, create an order and regenerate the sample using its code:

```bash
python scripts/make_sample.py --code PAY-YOURACTUALORDERCODE --reference TXFRESH001
```

The generator updates both the image and matching SMS with the current time. Upload the image first, observe the pending state, then send the matching SMS through the demo simulator.
