// Point these at your running services. Defaults match docker-compose.yml
// running on localhost — change them if you're deploying elsewhere.
const AUTH_URL = "http://localhost:8001";
const GATEWAY_WS_URL = "ws://localhost:8000";
const STATS_URL = "http://localhost:8004";

const ROLE_LABEL = { alice: "Alice", bob: "Bob", eve: "Eve" };
const ROLE_DESC = {
  alice: "You hold the private key. Wait for Bob's message to arrive, then decrypt it before Eve does.",
  bob: "You hold the public key. Encrypt a short message and send it to Alice — Eve will see it too.",
  eve: "You're eavesdropping. You can see everything Alice and Bob exchange, except the private key. Factor n to break it.",
};

const state = {
  displayName: null,
  playerId: null,
  roomId: null,
  token: null,
  role: null,
  players: [],
  ws: null,
  n: null,
  e: null,
  d: null,
  round: 0,
  keyBits: null,
  ciphertextBlocks: null,
  attemptsUsed: 0,
  defenderWins: 0,
  eveWins: 0,
};

const $ = (id) => document.getElementById(id);

function showScreen(name) {
  ["join", "lobby", "game", "over"].forEach((s) => {
    $(`screen-${s}`).classList.toggle("hidden", s !== name);
  });
}

function logEvent(text, kind = "system") {
  const el = document.createElement("div");
  el.className = `entry ${kind}`;
  el.textContent = text;
  $("event-log").appendChild(el);
  $("event-log").scrollTop = $("event-log").scrollHeight;
}

// ---------------------------------------------------------------------
// Join flow
// ---------------------------------------------------------------------

$("btn-join").addEventListener("click", handleJoin);
$("input-room").addEventListener("keydown", (e) => e.key === "Enter" && handleJoin());
$("input-name").addEventListener("keydown", (e) => e.key === "Enter" && handleJoin());

async function handleJoin() {
  const name = $("input-name").value.trim();
  const room = $("input-room").value.trim().toUpperCase();
  $("join-error").textContent = "";

  if (!name) {
    $("join-error").textContent = "Enter a name to continue.";
    return;
  }

  $("btn-join").disabled = true;
  try {
    const resp = await fetch(`${AUTH_URL}/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name: name, room_id: room || null }),
    });
    if (!resp.ok) throw new Error(`auth-service returned ${resp.status}`);
    const data = await resp.json();

    state.displayName = name;
    state.playerId = data.player_id;
    state.roomId = data.room_id;
    state.token = data.token;

    connectSocket();
    $("lobby-room-code").textContent = state.roomId;
    showScreen("lobby");
  } catch (err) {
    $("join-error").textContent = `Couldn't join: ${err.message}. Is auth-service running on ${AUTH_URL}?`;
  } finally {
    $("btn-join").disabled = false;
  }
}

// ---------------------------------------------------------------------
// WebSocket
// ---------------------------------------------------------------------

function connectSocket() {
  const url = `${GATEWAY_WS_URL}/ws/${state.roomId}?token=${encodeURIComponent(state.token)}`;
  state.ws = new WebSocket(url);

  state.ws.onopen = () => logEvent("Connected to the gateway.", "system");
  state.ws.onclose = () => logEvent("Disconnected from the gateway.", "system");
  state.ws.onerror = () => logEvent("WebSocket error — check that gateway-service is running.", "eve");
  state.ws.onmessage = (evt) => {
    let msg;
    try { msg = JSON.parse(evt.data); } catch { return; }
    handleServerEvent(msg);
  };
}

function send(action, payload = {}) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({ action, ...payload }));
  }
}

function handleServerEvent(msg) {
  switch (msg.type) {
    case "room_updated": return onRoomUpdated(msg);
    case "round_started": return onRoundStarted(msg);
    case "private_key": return onPrivateKey(msg);
    case "ciphertext_sent": return onCiphertextSent(msg);
    case "message_decrypted": return onMessageDecrypted(msg);
    case "attack_result": return onAttackResult(msg);
    case "round_timer": return onRoundTimer(msg);
    case "round_ready": return onRoundReady(msg);
    case "match_over": return onMatchOver(msg);
  }
}

// ---------------------------------------------------------------------
// Event handlers
// ---------------------------------------------------------------------

function onRoomUpdated(msg) {
  state.players = msg.players;
  state.defenderWins = msg.defender_wins ?? 0;
  state.eveWins = msg.eve_wins ?? 0;

  const me = msg.players.find((p) => p.player_id === state.playerId);
  if (me) state.role = me.role;

  renderLobby();

  if (state.role && $("screen-game").classList.contains("hidden") === false) {
    renderHud();
  }
}

function renderLobby() {
  const list = $("lobby-players");
  list.innerHTML = "";
  state.players.forEach((p) => {
    const li = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = p.player_id === state.playerId ? `${p.display_name} (you)` : p.display_name;
    li.appendChild(name);
    if (p.role) {
      const tag = document.createElement("span");
      tag.className = `player-role-tag ${p.role}`;
      tag.textContent = ROLE_LABEL[p.role];
      li.appendChild(tag);
    }
    list.appendChild(li);
  });

  const full = state.players.length === 3;
  $("btn-start-round").classList.toggle("hidden", !full);
  $("lobby-hint").classList.toggle("hidden", full);

  if (full && $("screen-lobby").classList.contains("hidden") === false) {
    enterGameScreen();
  }
}

$("btn-start-round").addEventListener("click", () => send("start_round"));
$("btn-next-round").addEventListener("click", () => send("start_round"));

function enterGameScreen() {
  showScreen("game");
  renderHud();
  renderRolePanel();
  logEvent(`You are ${ROLE_LABEL[state.role]}. ${state.players.length} players in the room.`, state.role);

  if (state.round === 0) {
    $("btn-next-round").textContent = "Begin round 1";
    $("btn-next-round").classList.remove("hidden");
  }
}
function renderHud() {
  $("hud-room").textContent = state.roomId;
  $("hud-role").textContent = ROLE_LABEL[state.role] || "—";
  $("hud-role").className = `role-badge ${state.role || ""}`;
  $("hud-round").textContent = state.round || "—";
  $("hud-score").textContent = `Defenders ${state.defenderWins} – ${state.eveWins} Eve`;
}

function renderRolePanel() {
  ["alice", "bob", "eve"].forEach((r) => $(`panel-${r}`).classList.toggle("hidden", r !== state.role));
  $("role-title").textContent = `${ROLE_LABEL[state.role]}'s console`;
  $("role-desc").textContent = ROLE_DESC[state.role];
}

function onRoundStarted(msg) {
  state.round = msg.round;
  state.keyBits = msg.key_bits;
  state.n = msg.n;
  state.e = msg.e;
  state.d = null;
  state.ciphertextBlocks = null;
  state.attemptsUsed = 0;

  renderHud();
  $("btn-next-round").classList.add("hidden");

  const pub = `n = ${msg.n}, e = ${msg.e} (${msg.key_bits}-bit key)`;
  if (state.role === "alice") {
    $("alice-pub").textContent = pub;
    $("alice-priv").textContent = "waiting on private channel…";
    $("btn-decrypt").disabled = true;
    $("alice-plaintext").classList.add("hidden");
  } else if (state.role === "bob") {
    $("bob-pub").textContent = pub;
    $("bob-message").value = "";
    $("btn-send").disabled = false;
  } else if (state.role === "eve") {
    $("eve-pub").textContent = pub;
    $("eve-cipher").textContent = "nothing intercepted yet";
    $("eve-p").value = "";
    $("eve-q").value = "";
    $("btn-attack").disabled = false;
    $("eve-attempts").textContent = "";
  }

  logEvent(`Round ${msg.round} begins — ${msg.key_bits}-bit key, ${msg.time_limit_seconds}s on the clock.`, "system");
}

function onPrivateKey(msg) {
  state.d = msg.d;
  if (state.role === "alice") {
    $("alice-priv").textContent = `d = ${msg.d}`;
  }
  logEvent("Private key received on your channel only.", "alice");
}

function onCiphertextSent(msg) {
  state.ciphertextBlocks = msg.blocks;
  if (state.role === "alice") {
    $("btn-decrypt").disabled = false;
  }
  if (state.role === "eve") {
    $("eve-cipher").textContent = `[${msg.blocks.join(", ")}]`;
  }
  logEvent(`Bob's message was sent (${msg.blocks.length} block${msg.blocks.length === 1 ? "" : "s"} of ciphertext).`, "bob");
}

$("btn-send").addEventListener("click", () => {
  const text = $("bob-message").value.trim();
  if (!text) return;
  send("send_message", { plaintext: text });
  $("btn-send").disabled = true;
});

$("btn-decrypt").addEventListener("click", () => {
  send("decrypt");
  $("btn-decrypt").disabled = true;
});

function onMessageDecrypted(msg) {
  const box = $("alice-plaintext");
  box.textContent = `Decrypted: "${msg.plaintext}"`;
  box.classList.remove("hidden");
  logEvent("You decrypted the message.", "alice");
}

$("btn-attack").addEventListener("click", () => {
  const p = $("eve-p").value.trim();
  const q = $("eve-q").value.trim();
  if (!p || !q) return;
  send("attack", { candidate_p: Number(p), candidate_q: Number(q) });
});

function onAttackResult(msg) {
  state.attemptsUsed = msg.attempts_used;
  if (state.role === "eve") {
    $("eve-attempts").textContent = `Attempts used: ${msg.attempts_used}`;
  }

  if (msg.timeout) {
    logEvent(`Time expired — Eve did not crack the key in ${state.attemptsUsed} attempt(s).`, "system");
    return;
  }

  if (msg.correct) {
    $("btn-attack").disabled = true;
    const plaintextNote = msg.plaintext ? ` The message read: "${msg.plaintext}".` : "";
    logEvent(`Eve factored n correctly after ${msg.attempts_used} attempt(s).${plaintextNote}`, "eve");
  } else {
    logEvent(`Attack attempt ${msg.attempts_used} was incorrect.`, "eve");
  }
}

function onRoundTimer(msg) {
  const m = Math.floor(msg.seconds_remaining / 60);
  const s = String(msg.seconds_remaining % 60).padStart(2, "0");
  $("hud-timer").textContent = `${m}:${s}`;
}

function onRoundReady(msg) {
  $("hud-timer").textContent = "—";
  $("btn-next-round").textContent = "Start next round";   // <-- add this line
  $("btn-next-round").classList.remove("hidden");
  logEvent(`Round ${state.round} is over. Round ${msg.next_round} is ready when you are.`, "system");
}

function onMatchOver(msg) {
  state.defenderWins = msg.defender_wins;
  state.eveWins = msg.eve_wins;

  const eveWon = msg.winner === "eve";
  $("result-title").textContent = eveWon ? "Eve wins the match" : "Alice & Bob win the match";
  $("result-detail").textContent = eveWon
    ? "Eve broke the key before time ran out on more rounds than she lost."
    : "Alice and Bob kept the channel secure across the majority of rounds.";
  $("result-defender-wins").textContent = msg.defender_wins;
  $("result-eve-wins").textContent = msg.eve_wins;

  showScreen("over");
}

$("btn-play-again").addEventListener("click", () => window.location.reload());

// ---------------------------------------------------------------------
// Leaderboard (best-effort — stats-service is non-blocking for gameplay)
// ---------------------------------------------------------------------

(async function loadLeaderboard() {
  try {
    const resp = await fetch(`${STATS_URL}/leaderboard`);
    if (!resp.ok) throw new Error();
    const rows = await resp.json();
    const body = $("leaderboard-body");
    body.innerHTML = "";
    if (rows.length === 0) {
      body.textContent = "No rounds recorded yet — be the first.";
      return;
    }
    rows.forEach((r) => {
      const row = document.createElement("div");
      row.innerHTML = `<span>${r.role}</span><span>${r.wins}</span>`;
      body.appendChild(row);
    });
  } catch {
    $("leaderboard-body").textContent = "Leaderboard unavailable (is stats-service running?).";
  }
})();
