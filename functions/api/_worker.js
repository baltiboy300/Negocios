export default {
  async fetch(request) {
    // Handle CORS preflight OPTIONS requests
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "*",
        },
      });
    }

    const url = new URL(request.url);

    // Accept queries either via /api/imd?stationId=42111 or via ?url=...
    let targetUrl;
    if (url.pathname === "/api/imd") {
      const stationId = url.searchParams.get("stationId") || "42111";
      targetUrl = `https://api.imd.gov.in/api/v1/cityforecast?id=${stationId}`;
    } else if (url.searchParams.has("url")) {
      targetUrl = url.searchParams.get("url");
    } else {
      return new Response(
        JSON.stringify({ status: "IMD Proxy Worker is Online", usage: "/api/imd?stationId=42111" }),
        {
          status: 200,
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
        }
      );
    }

    try {
      const response = await fetch(targetUrl, {
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
          "Accept": "application/json",
        },
      });

      const data = await response.text();

      return new Response(data, {
        status: response.status,
        headers: {
          "Content-Type": "application/json",
          "Access-Control-Allow-Origin": "*", // <--- THIS PERMANENTLY FIXES CORS
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Cache-Control": "public, max-age=300",
        },
      });
    } catch (err) {
      return new Response(JSON.stringify({ error: err.message }), {
        status: 500,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
      });
    }
  },
};
