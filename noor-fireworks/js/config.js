/*
  Noor Fireworks: business details and catalogue.
  Edit this file to change phone numbers, prices, stock and products.
  Everything else on the site reads from here.
*/
window.NOOR = {
  business: {
    name: 'Noor Fireworks',
    phone: '+92 300 0000000',        // shown on the site
    whatsapp: '923000000000',        // international format, digits only (used for wa.me links)
    email: 'hello@noorfireworks.pk',
    hours: 'Mon–Sat, 10 am to 7 pm'
  },

  /* Social pages. Paste the full link to your page; leave '' to hide an icon. */
  social: {
    instagram: 'https://www.instagram.com/',
    facebook: 'https://www.facebook.com/'
  },

  promo: {
    code: 'MELA15',
    percent: 15,
    freeGiftAt: 25000,               // free sparkler pack at or above this cart total (PKR)
    freeGift: 'Free sparkler pack'
  },

  /*
    Reviews strip near the bottom of the page. Stays hidden until you fill it in with REAL figures,
    for example: { customers: '2,000+', sources: [{ name: 'Google', rating: 4.8, count: 312, url: 'https://g.page/...' }] }
  */
  reviews: null,

  cities: ['Karachi', 'Lahore', 'Islamabad', 'Rawalpindi', 'Faisalabad', 'Multan', 'Peshawar', 'Hyderabad', 'Other city'],

  showrooms: [
    { city: 'Karachi', area: 'Korangi Industrial Area, Karachi', hours: 'Mon–Sat, 10 am to 8 pm', phone: '+92 300 0000000',
      map: 'https://www.google.com/maps/search/?api=1&query=Korangi+Industrial+Area+Karachi' }
  ],

  /* [name, short description, tile colour, effect, palette, dark text?] */
  categories: [
    ['Cakes & barrages', 'Multi-shot shows in one box', '#ff2e88', 'peony', 'mix'],
    ['Rockets', 'Whistle up, burst high', '#2f5bff', 'rocket', 'blue'],
    ['Roman candles', 'Balls of colour, one by one', '#7a3cff', 'roman', 'green'],
    ['Fountains & mines', 'Showers of sparks from the ground', '#ff6a2b', 'fountain', 'gold', 1],
    ['Wheels', 'Charkhi that spin and sing', '#007d73', 'wheel', 'gold'],
    ['Sparklers', 'Phuljhari for every hand', '#ffb000', 'fountain', 'silver', 1],
    ['Handheld smoke', 'Thick colour for photos', '#12773d', 'smoke', 'flag'],
    ['Gender reveal', 'Pink or blue, the big moment', '#ff8fc0', 'smoke', 'reveal', 1],
    ['Ice fountains', 'Cold sparks, safe indoors', '#4fb6ff', 'fountain', 'silver', 1],
    ['Firing systems', 'Wireless cue controllers', '#1b1240', 'crossette', 'blue'],
    ['Big fireworks', 'Display shells, licensed only', '#c81f2d', 'willow', 'gold'],
    ['Low noise', 'All colour, less boom', '#8bd400', 'fountain', 'green', 1]
  ],

  /*
    id: unique, never change once orders use it
    n: name, k: category, q: size/shots, d: duration, x: keep-back distance
    pv: price (PKR), was: old price, st: ok | few | pre | out
    low: low noise, pro: licensed only (price on request), bogo: part of the cake offer
    fx / c / bg: the animation shown on the card
  */
  items: [
    { id: 'night-garden-49', n: 'Night Garden 49-shot cake', k: 'Cakes & barrages', q: '49 shots', d: '40 s', x: '25 m', pv: 18500, was: 21000, st: 'few', fx: 'peony', c: 'violet', bg: '#2a0f3d', pop: 10 },
    { id: 'chirya-16', n: 'Chirya 16-shot cake', k: 'Cakes & barrages', q: '16 shots', d: '20 s', x: '15 m', pv: 4500, st: 'ok', bogo: 1, fx: 'peony', c: 'pink', bg: '#3a0f2e', pop: 9 },
    { id: 'crossette-25', n: 'Crossette 25-shot cake', k: 'Cakes & barrages', q: '25 shots', d: '25 s', x: '20 m', pv: 8900, st: 'ok', bogo: 1, fx: 'crossette', c: 'blue', bg: '#0f2a6b', pop: 8 },
    { id: 'mela-finale-100', n: 'Mela Finale 100-shot', k: 'Cakes & barrages', q: '100 shots', d: '55 s', x: '25 m', pv: 42000, was: 46000, st: 'pre', fx: 'chrysanthemum', c: 'gold', bg: '#1b1240', pop: 7 },
    { id: 'butterfly-36', n: 'Butterfly low-noise cake', k: 'Cakes & barrages', q: '36 shots', d: '45 s', x: '15 m', pv: 9800, st: 'ok', low: 1, fx: 'ring', c: 'pink', bg: '#401040', pop: 7 },
    { id: 'sky-whistler', n: 'Sky Whistler rockets', k: 'Rockets', q: '12 pcs', d: '3 s each', x: '25 m', pv: 2400, st: 'ok', fx: 'rocket', c: 'pink', bg: '#13235c', pop: 9 },
    { id: 'starball-candles', n: 'Starball roman candles', k: 'Roman candles', q: '8 balls × 4', d: '25 s', x: '15 m', pv: 900, st: 'ok', fx: 'roman', c: 'green', bg: '#2b1460', pop: 6 },
    { id: 'rainbow-fountain', n: 'Rainbow fountain', k: 'Fountains & mines', q: '2 m height', d: '40 s', x: '5 m', pv: 1200, was: 1500, st: 'ok', low: 1, fx: 'fountain', c: 'mix', bg: '#4a1238', pop: 9 },
    { id: 'peacock-mine', n: 'Peacock mine', k: 'Fountains & mines', q: '1 shot', d: '2 s', x: '15 m', pv: 2200, st: 'ok', fx: 'mine', c: 'green', bg: '#063a3a', pop: 4 },
    { id: 'golden-charkhi', n: 'Golden charkhi', k: 'Wheels', q: '10 pcs', d: '25 s', x: '5 m', pv: 750, st: 'ok', low: 1, fx: 'wheel', c: 'gold', bg: '#073b45', pop: 7 },
    { id: 'golden-phuljhari', n: 'Golden phuljhari', k: 'Sparklers', q: '10 pcs', d: '60 s', x: '1 m', pv: 650, st: 'ok', low: 1, fx: 'fountain', c: 'gold', bg: '#3d1d05', pop: 10 },
    { id: 'flag-smoke', n: 'Green & white smoke', k: 'Handheld smoke', q: '2 pcs', d: '90 s', x: '5 m', pv: 1400, st: 'ok', low: 1, fx: 'smoke', c: 'flag', bg: '#0f3b28', pop: 6 },
    { id: 'reveal-smoke', n: 'Gender reveal smoke', k: 'Gender reveal', q: 'Pink or blue', d: '60 s', x: '5 m', pv: 1600, st: 'few', low: 1, fx: 'smoke', c: 'reveal', bg: '#3a1a3f', pop: 5 },
    { id: 'ice-fountain', n: 'Ice fountain, indoor', k: 'Ice fountains', q: '3 m height', d: '30 s', x: '1.5 m', pv: 4800, st: 'ok', low: 1, fx: 'fountain', c: 'silver', bg: '#12285e', pop: 8 },
    { id: 'wireless-12', n: '12-cue wireless firer', k: 'Firing systems', q: '12 cues', d: '200 m range', x: 'Remote', pv: 14000, was: 16500, st: 'few', fx: 'crossette', c: 'mix', bg: '#1b1240', pop: 3 },
    { id: 'willow-6', n: 'Gold willow shell, 6″', k: 'Big fireworks', q: '12 per case', d: '6 s', x: '130 m', pv: 0, st: 'ok', pro: 1, fx: 'willow', c: 'gold', bg: '#1a0c2e', pop: 2 },
    { id: 'peony-4', n: 'Mix peony shell, 4″', k: 'Big fireworks', q: '24 per case', d: '2.5 s', x: '85 m', pv: 0, st: 'ok', pro: 1, fx: 'peony', c: 'red', bg: '#2a0a1c', pop: 1 }
  ]
};
