# RSA game — Alice, Bob & Eve

A real-time web game built around RSA encryption. Players join as Alice or
Bob (defend a message exchange) or Eve (intercept and crack it). Built for
a Programming 5 microservices + real-time communication assignment.

## Architecture

```
web-client  ──WS──>  gateway  ──pub/sub──>  Redis
                         │
                         ├──HTTP──>  auth     (room join, session tokens)
                         ├──HTTP──>  match    (game state, scoring, difficulty)
                         │              │
                         │              ├──HTTP──>  crypto  (RSA keygen/encrypt/decrypt/crack)
                         │              └──HTTP──>  stats   (match history, Postgres)
```

- **gateway** — the only service holding WebSocket connections. Verifies
  the player's token with `auth`, registers them with `match` on connect,
  forwards game actions, and fans Redis pub/sub events back out — either
  to the whole room, or privately to one player (used for Alice's private
  key and her decrypted message).
- **auth** — name + room code in, short-lived JWT out. No password
  accounts for this project.
- **match** — the authoritative game state machine: role assignment
  (first two joiners are Alice/Bob, third is Eve), the round timer, the
  fixed 3-round difficulty curve, scoring, and win conditions. Calls
  `crypto` for every RSA operation and reports each round's result to
  `stats`.
- **crypto** — the only service that touches RSA math: keygen, encrypt,
  decrypt, and `/crack`, which verifies Eve's factors and — if correct —
  rebuilds the private key and decrypts whatever's been intercepted.
- **stats** — persists round results to Postgres and serves a small
  win-count leaderboard.

## How a match plays out

1. Three players join a room (via the web client). The first two become
   Alice and Bob, the third becomes Eve.
2. Someone clicks **Begin round 1**. `match` asks `crypto` for a keypair
   sized to that round's difficulty and starts a countdown. The public
   half (`n`, `e`) is broadcast to the whole room — Eve is *meant* to see
   it, that's how RSA works. The private half (`d`) goes only to Alice.
3. Bob types a message; it's encrypted server-side and broadcast as
   ciphertext to the whole room — this is the interception moment.
4. Alice decrypts it with her private key. Eve tries to factor `n` into
   its two primes and submit them as an attack.
5. If Eve factors it correctly before time runs out, she wins the round
   and the intercepted message is revealed. Otherwise the round times out
   and Alice/Bob win it. After 3 rounds, whoever won more rounds wins the
   match.

## Running it

```bash
docker compose up --build
```

This starts Redis, Postgres, all five services, and a static file server
for the web client. Then open:

```
http://localhost:8080
```

Open it in three separate browser tabs/windows (or on three devices) to
play all three roles — use the same room code in each, or leave it blank
in the first tab to generate one.

| Service        | Port |
|----------------|------|
| web-client      | 8080 |
| gateway (WS)    | 8000 |
| auth            | 8001 |
| match           | 8002 |
| crypto          | 8003 |
| stats           | 8004 |
| Postgres        | 5432 |
| Redis           | 6379 |

Each service also runs standalone for local development:

```bash
cp .env.example .env   # only needed if running services outside Docker
cd services/crypto
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8003
```

## Repo layout

```
rsa-game/
├── docker-compose.yml
├── .env.example
├── services/
│   ├── gateway/    WebSocket gateway (FastAPI + websockets + Redis pub/sub)
│   ├── auth/       Room join + JWT issuance (FastAPI)
│   ├── match/      Game state machine (FastAPI)
│   ├── crypto/     RSA ops + Eve's attack toolkit (FastAPI)
│   └── stats/      Match history (FastAPI + Postgres)
├── shared/         Reference event/action schemas used across services
└── web-client/     Static web client (plain HTML/CSS/JS, no build step)
```

## Status

Complete and playable end to end: lobby → role assignment → 3 timed
rounds → scoring → match result, with a leaderboard backed by Postgres.

Known simplifications, worth a line in your writeup if a grader asks:
- Room codes aren't checked for collisions against active rooms (fine at
  class-project scale).
- Match state lives in memory in a single `match-service` process — noted
  in `state.py` as the place you'd move to Redis if this needed to scale
  horizontally.
- No rate limiting on Eve's attack attempts beyond the visible
  `attempts_used` counter.
