# web-client

Static, dependency-free HTML/CSS/JS. No build step.

- `index.html` / `style.css` — layout and the dark "case file" visual theme
- `app.js` — join flow (HTTP to auth-service), the WebSocket connection to
  gateway-service, and all rendering, driven entirely by the events listed
  in `shared/events.py`

Served by `docker compose up` at http://localhost:8080, or open
`index.html` directly / serve it with any static file server. The service
URLs it talks to are hardcoded at the top of `app.js` (`AUTH_URL`,
`GATEWAY_WS_URL`, `STATS_URL`) — change them if you deploy the backend
anywhere other than `localhost`.
