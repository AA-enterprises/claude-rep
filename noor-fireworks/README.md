# Noor Fireworks website

A static website for Noor Fireworks: an online fireworks shop with a working cart, plus pages for wedding fireworks, displays, delivery, showrooms, safety and contact. Orders and enquiries are sent to the shop on WhatsApp, so there is no server, database or payment gateway to run.

## Files

| Path | What it is |
|---|---|
| `index.html` | The page |
| `css/styles.css` | All styling |
| `js/config.js` | **Business details and the product catalogue. Edit this one.** |
| `js/fireworks.js` | The fireworks animation engine |
| `js/app.js` | Shop, cart, WhatsApp checkout and page behaviour |
| `assets/` | Hero video, poster image and favicon |

## Before going live

Open `js/config.js` and replace the placeholders:

- `phone` and `whatsapp`: your real number. `whatsapp` must be digits only in international format, for example `923001234567`.
- `email`, `hours` and the three `showrooms`.
- Prices, stock (`st`: `ok`, `few`, `pre` or `out`) and products as needed.

The phone number and email also appear in `index.html` (in the structured data block in `<head>`); update them there too so search engines show the right details.

## How ordering works

1. A customer adds products to the cart. The cart remembers them on that phone or computer.
2. Buy one, get one free is applied automatically to products marked `bogo: 1` (the 16 and 25-shot cakes): every second offer cake, cheapest first, is free.
3. Code `MELA15` takes 15% off. A free sparkler pack is added at PKR 25,000 and above.
4. The customer fills in name, phone, city and address, confirms they are 18+, and presses **Send order on WhatsApp**. WhatsApp opens with the full order written out, ready to send to you.
5. You reply with the delivery charge and payment details, as before.

The contact form works the same way: it opens WhatsApp with the enquiry written out.

## Run it locally

Open `index.html` in a browser, or serve the folder:

```bash
cd noor-fireworks
python3 -m http.server 8000
# then open http://localhost:8000
```

## Put it online

Any static host works. Two free options:

- **Netlify**: drag the `noor-fireworks` folder onto app.netlify.com/drop.
- **GitHub Pages**: in the repository settings, enable Pages for the `main` branch, then open `/noor-fireworks/`.
