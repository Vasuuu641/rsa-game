# RSA Game — Alice, Bob & Eve

A real-time web game built around RSA encryption. Three players join a room — two defend a message exchange as **Alice** and **Bob**, one attacks it as **Eve**. Built as a microservices + real-time communication project.

---

## How to play

Every match is three players and three rounds. Roles are assigned automatically: the first two people to join a room become **Alice** and **Bob**, the third becomes **Eve**. You don't choose your role — it's fixed by join order, so the game stays balanced round to round rather than letting one player always pick the "easy" side.

Each round works the same way regardless of round number — only the key size and the clock change (see [Difficulty curve](#difficulty-curve) below).

### Playing as Alice

You hold the **private key**. Your job is to read Bob's message before Eve reconstructs your key and reads it herself.

1. When the round starts, you're privately sent your private key `d` — nobody else in the room ever sees this value, not even over the network in a form anyone else can intercept.
2. Wait for Bob to send his encrypted message. You'll see ciphertext blocks arrive.
3. Click **Decrypt incoming message**. This calls crypto-service with your `d`, and the plaintext appears only on your screen.

You don't need to do anything with the public key `n, e` yourself — that's Bob's job when he encrypts.

### Playing as Bob

You hold the **public key**. Your job is to get a message to Alice.

1. When the round starts, you see the public key `n, e` (the same one Eve sees — that's how RSA works, the public half really is public).
2. Type a short message and click **Encrypt & send**. This gets encrypted server-side and broadcast to the whole room as ciphertext — including to Eve, deliberately, since that's the "interception" moment of the game.
3. There's nothing more for you to do this round — Alice takes it from here, and Eve is racing the clock to catch up.

### Playing as Eve

You're eavesdropping. You see everything Alice and Bob exchange **except** the private key `d`. Your job is to reconstruct it yourself before time runs out.

1. You see the public key `n, e` the moment the round starts, and the ciphertext blocks the moment Bob sends his message.
2. To break the key, you need to factor `n` into its two prime factors, `p` and `q`. RSA's security relies on this being hard for large `n` — but these keys are deliberately small (16–32 bits) so it's a solvable puzzle rather than a wall.
3. Enter your guessed `p` and `q` and click **Attempt factorization**. If you're right, the server rebuilds the private key from your factors and decrypts whatever's been intercepted so far — you'll see the plaintext revealed to the whole room.
4. There's a short cooldown between attempts, so you can't just spam random guesses as fast as possible.

**How to actually factor `n`:** for these key sizes, trial division works — try dividing `n` by every integer from 2 up to `√n` until one divides evenly. By hand this is only realistic for the smallest round; for round 2–3 sizes, write a few lines of code:

```python
n = 44719
p = next(i for i in range(2, n) if n % i == 0)
q = n // p
```

### Winning

- If Eve factors the key correctly before time runs out, she wins that round.
- If time runs out first, Alice and Bob win that round.
- After 3 rounds, whoever won more rounds wins the match.

---

## Difficulty curve

Fixed, not adjustable — three rounds, each with a larger key and a longer clock, so Eve's factoring gets harder while Alice and Bob's window to communicate grows to compensate:

| Round | Key size | Time limit |
|-------|----------|------------|
| 1     | 16-bit   | 60s        |
| 2     | 24-bit   | 90s        |
| 3     | 32-bit   | 120s       |

---

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

- **gateway** — the only service holding WebSocket connections. Verifies each player's token with `auth` on connect, registers them with `match`, forwards game actions, and fans Redis pub/sub events back out — either to the whole room, or privately to a single player.
- **auth** — name + room code in, short-lived JWT out. No password accounts. Also checks with `match` that a randomly generated room code isn't already in use before handing it out.
- **match** — the authoritative game state machine: role assignment, the round timer, the difficulty curve, scoring, attack-cooldown enforcement, and win conditions. Calls `crypto` for every RSA operation and reports each round's result to `stats`.
- **crypto** — the only service that touches RSA math: keygen, encrypt, decrypt, and `/crack`, which verifies Eve's factors and — if correct — rebuilds the private key and decrypts whatever's been intercepted.
- **stats** — persists round results to Postgres and serves a win-count leaderboard.
- **web-client** — static HTML/CSS/JS, no build step or framework. Talks to `auth` over HTTP for joining, and to `gateway` over WebSocket for everything else.

### Why a room's public key is broadcast but the private key isn't

This is the core mechanic the whole architecture is built around, so it's worth being explicit about it. Redis pub/sub channels follow a `room:{room_id}` naming pattern for room-wide broadcasts. Gateway additionally subscribes to `room:{room_id}:player:{player_id}` sub-channels for point-to-point delivery — a single wildcard subscription (`room:*`) catches both patterns, since Redis's glob matching spans the colons. This is what lets `match`-service publish Alice's private key to a channel only her own WebSocket connection is listening on, while the public key and ciphertext go out to the whole room the normal way.

### Why match-service keeps state in memory rather than Redis

`RoomState` (players, roles, round number, current key material, score) lives in a plain Python dict inside the single `match-service` process, not in Redis or Postgres. This is a deliberate scope decision for a project running one instance of each service — it's simpler to reason about and debug. The tradeoff: if you ever needed to run more than one `match-service` instance behind a load balancer, this state would need to move into Redis (which is already in the stack for pub/sub), since two instances wouldn't share room state. Not built, because it's out of scope here — noted directly in `match/app/state.py`.

### Why crypto-service implements RSA by hand instead of using a library

Standard crypto libraries (e.g. Python's `cryptography` package) refuse to generate keys below roughly 512 bits — correctly, since that's far too weak for real security. This game's entire premise depends on keys small enough to be crackable by a human or a short script in under two minutes, so `crypto-service` implements textbook RSA directly with `sympy` for prime generation. This is explicitly *not* production-safe cryptography and isn't meant to be reused outside this project.

### Why Eve's win path lives entirely server-side

Every attack attempt is verified by `crypto-service` against the real `n`, not by the client. A client could trivially fabricate "I factored it correctly" otherwise. The full sequence for an attack: gateway forwards Eve's guessed `p, q` to match-service, which forwards them to crypto-service's `/crack` endpoint; that endpoint checks `p * q == n`, and only if that holds does it rebuild the private exponent `d` from `p`, `q`, and the public `e`, then decrypt whatever ciphertext has been intercepted so far. Nothing about whether an attempt is "correct" is ever decided or trusted client-side.

---

## Running it

```bash
docker compose up --build
```

This starts Redis, Postgres, all five backend services, and a static file server for the web client.

| Service      | Port  |
|--------------|-------|
| web-client   | 8080  |
| gateway (WS) | 8000  |
| auth         | 8001  |
| match        | 8002  |
| crypto       | 8003  |
| stats        | 8004  |
| Postgres     | 5432* |
| Redis        | 6379  |

\* Host-side Postgres port may differ if `5432` is already in use on your machine — check the `ports:` mapping under `postgres:` in `docker-compose.yml`. This only affects connecting to Postgres directly from your host; every container still talks to it internally on `5432` regardless.

Open `http://localhost:8080` in three separate browser tabs (or three devices) to play all three roles. Leave the room code blank in the first tab to generate one, then use the same code in the other two.

Each service also runs standalone for local development:

```bash
cd services/crypto
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8003
```

---

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

---

## Known simplifications

Worth a line in a writeup if a grader asks:

- **Match state is in-memory, single-instance.** See "Why match-service keeps state in memory" above.
- **No client-side factoring visualization.** `crypto/app/attacks.py` includes a `trial_division()` helper intended for an animated "Eve is trying factors..." UI, but it isn't wired up to any endpoint — Eve currently just submits a final guess rather than watching a search happen. Left as a stretch goal.
- **Attack rate limiting is a simple fixed cooldown**, not a true rate limiter (no sliding window, no per-IP tracking) — enough to stop naive spam-clicking, not adversarial abuse.
- **Room codes are checked for collisions against active rooms** but not against historical/expired ones, since expired rooms aren't cleaned up from memory — fine at class-project traffic levels.

---

## Status

Complete and playable end to end: lobby → role assignment → 3 timed rounds → scoring → match result, with a leaderboard backed by Postgres.