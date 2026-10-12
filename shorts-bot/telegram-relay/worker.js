// Shorts Bot ka Telegram relay (Cloudflare Worker).
// Bot ki requests ko api.telegram.org tak pahunchata hai, jab internet company
// computer se Telegram rok de. Sirf Telegram bot API ke raaste (/bot...) chalte hain.
export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/bot")) {
      return new Response("Shorts Bot relay chal raha hai.", { status: 200 });
    }
    url.protocol = "https:";
    url.hostname = "api.telegram.org";
    url.port = "";
    return fetch(new Request(url.toString(), request));
  },
};
