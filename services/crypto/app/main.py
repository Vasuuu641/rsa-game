from fastapi import FastAPI
from pydantic import BaseModel

from . import rsa_ops, attacks

app = FastAPI(title="crypto-service")


@app.get("/health")
async def health():
    return {"status": "ok"}


class KeygenRequest(BaseModel):
    key_bits: int = 24  # match-service passes the per-round value from difficulty.py


class KeygenResponse(BaseModel):
    n: int
    e: int
    d: int
    key_bits: int


@app.post("/keygen", response_model=KeygenResponse)
async def keygen(req: KeygenRequest):
    keypair = rsa_ops.generate_keypair(req.key_bits)
    # NOTE: d is returned here for the owning player's client to hold.
    # match-service must only ever broadcast n/e (the public half) to
    # the room — d gets routed point-to-point to Alice only.
    return KeygenResponse(
        n=keypair["n"], e=keypair["e"], d=keypair["d"], key_bits=keypair["key_bits"]
    )


class EncryptRequest(BaseModel):
    message: str
    n: int
    e: int


class EncryptResponse(BaseModel):
    blocks: list[int]


@app.post("/encrypt", response_model=EncryptResponse)
async def encrypt(req: EncryptRequest):
    blocks = rsa_ops.text_to_blocks(req.message, req.n)
    ciphertext = [rsa_ops.encrypt_block(b, req.n, req.e) for b in blocks]
    return EncryptResponse(blocks=ciphertext)


class DecryptRequest(BaseModel):
    blocks: list[int]
    n: int
    d: int


class DecryptResponse(BaseModel):
    message: str


@app.post("/decrypt", response_model=DecryptResponse)
async def decrypt(req: DecryptRequest):
    plain_blocks = [rsa_ops.decrypt_block(b, req.n, req.d) for b in req.blocks]
    return DecryptResponse(message=rsa_ops.blocks_to_text(plain_blocks))


class AttackRequest(BaseModel):
    n: int
    candidate_p: int
    candidate_q: int


class AttackResponse(BaseModel):
    correct: bool


@app.post("/verify-attack", response_model=AttackResponse)
async def verify_attack(req: AttackRequest):
    correct = attacks.verify_factors(req.n, req.candidate_p, req.candidate_q)
    return AttackResponse(correct=correct)


class CrackRequest(BaseModel):
    n: int
    e: int
    candidate_p: int
    candidate_q: int
    blocks: list[int] = []  # the intercepted ciphertext, if any has been sent yet


class CrackResponse(BaseModel):
    correct: bool
    plaintext: str | None = None


@app.post("/crack", response_model=CrackResponse)
async def crack(req: CrackRequest):
    """
    The full "Eve wins" path: verify her factors are actually right,
    then — since p and q plus the public e are all you need — rebuild
    d ourselves and decrypt whatever ciphertext has been intercepted
    so far. This is the payoff moment for a correct attack.
    """
    if not attacks.verify_factors(req.n, req.candidate_p, req.candidate_q):
        return CrackResponse(correct=False)

    if not req.blocks:
        # Factors are right, but nothing has been sent to decrypt yet.
        return CrackResponse(correct=True, plaintext=None)

    d = rsa_ops.derive_private_key(req.candidate_p, req.candidate_q, req.e)
    plain_blocks = [rsa_ops.decrypt_block(b, req.n, d) for b in req.blocks]
    return CrackResponse(correct=True, plaintext=rsa_ops.blocks_to_text(plain_blocks))


# TODO: rate-limit /verify-attack and /crack per room so Eve can't
# brute-force by spamming requests faster than the game's "attempts
# used" counter tracks — either here or in match-service, which is the
# only caller of this service.
