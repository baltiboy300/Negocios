export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Route for the IMD API Proxy
    if (url.pathname === "/api/imd") {
      const stationId = url.searchParams.get("stationId") || "42111";
      const targetUrl = `https://api.imd.gov.in/api/v1/cityforecast?id=${stationId}`;

      try {
        const response = await fetch(targetUrl, {
          headers: {
            "User-Agent": "Sentinel-HL-EWS/1.0",
            "Accept": "application/json"
          }
        });

        if (!response.ok) {
          return new Response(
            JSON.stringify({ error: `IMD responded with HTTP ${response.status}` }),
            { 
              status: response.status, 
              headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" } 
            }
          );
        }

        const data = await response.json();
        return new Response(JSON.stringify(data), {
          status: 200,
          headers: {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Cache-Control": "public, max-age=300"
          }
        });
      } catch (err) {
        return new Response(
          JSON.stringify({ error: err.message || "Failed to reach IMD upstream" }),
          { 
            status: 500, 
            headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" } 
          }
        );
      }
    }

    // Pass through all other requests (static HTML/CSS/JS)
    if (env.ASSETS) {
      return env.ASSETS.fetch(request);
    }

    return new Response("Not Found", { status: 404 });
  }
};
