from flask import Flask, request, jsonify
import asyncio, time, json, binascii, requests, aiohttp
from collections import defaultdict
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

import like_pb2
import like_count_pb2
import uid_generator_pb2

app = Flask(__name__)

KEY_LIMIT = 150
token_tracker = defaultdict(lambda: [0, time.time()])

# ================= UTIL =================

def midnight_ts():
    now = datetime.now()
    return datetime(now.year, now.month, now.day).timestamp()

def load_tokens(server):
    try:
        if server == "ID":
            f = "token_id.json"
        elif server in {"BR", "US", "SAC", "NA"}:
            f = "token_br.json"
        else:
            f = "token_bd.json"
        with open(f) as fp:
            return json.load(fp)
    except:
        return []

def encrypt(data: bytes) -> str:
    key = b'Yg&tc%DEuh6%Zc^8'
    iv  = b'6oyZDr22E3ychjM%'
    aes = AES.new(key, AES.MODE_CBC, iv)
    return binascii.hexlify(aes.encrypt(pad(data, 16))).decode()

def uid_encrypt(uid):
    m = uid_generator_pb2.uid_generator()
    m.krishna_ = int(uid)
    m.teamXdarks = 1
    return encrypt(m.SerializeToString())

def decode_info(raw):
    try:
        info = like_count_pb2.Info()
        info.ParseFromString(raw)
        return info
    except:
        return None

def profile_request(enc_uid, server, token):
    url = (
        "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
        if server in {"BR", "US", "SAC", "NA"}
        else "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"
    )
    try:
        r = requests.post(
            url,
            data=bytes.fromhex(enc_uid),
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
            verify=False
        )
        if r.status_code != 200:
            return None
        return decode_info(r.content)
    except:
        return None

# ================= LIKE SPAM =================

async def send_like(enc_like, token, url):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                url,
                data=bytes.fromhex(enc_like),
                headers={"Authorization": f"Bearer {token}"}
            ):
                return True
    except:
        return False

async def spam_like(uid, server, tokens):
    proto = like_pb2.like()
    proto.uid = int(uid)
    proto.region = server
    enc_like = encrypt(proto.SerializeToString())

    url = (
        "https://client.us.freefiremobile.com/LikeProfile"
        if server in {"BR", "US", "SAC", "NA"}
        else "https://clientbp.ggblueshark.com/LikeProfile"
    )

    tasks = []
    for i in range(50):
        token = tokens[i % len(tokens)]["token"]
        tasks.append(send_like(enc_like, token, url))

    results = await asyncio.gather(*tasks)
    return sum(1 for r in results if r)

# ================= ROUTE =================

@app.route("/like", methods=["GET"])
def like():
    uid = request.args.get("uid")
    server = request.args.get("server_name", "").upper()
    key = request.args.get("key")

    if key != "jenil":
        return jsonify({"error": "invalid api key"}), 403
    if not uid or not server:
        return jsonify({"error": "uid & server_name required"}), 400

    tokens = load_tokens(server)
    if not tokens:
        return jsonify({"error": "token file not found"}), 500

    token = tokens[0]["token"]
    enc_uid = uid_encrypt(uid)

    # rate limit
    today = midnight_ts()
    count, last = token_tracker[token]
    if last < today:
        token_tracker[token] = [0, time.time()]
        count = 0
    if count >= KEY_LIMIT:
        return jsonify({"error": "daily limit reached"}), 429

    # BEFORE
    before_info = profile_request(enc_uid, server, token)
    before_like = before_info.AccountInfo.Likes if before_info else -1
    nickname = before_info.AccountInfo.PlayerNickname if before_info else "unknown"

    # SPAM LIKE
    try:
        loop = asyncio.get_event_loop()
    except:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    success_like = loop.run_until_complete(spam_like(uid, server, tokens))

    time.sleep(2)

    # AFTER
    after_info = profile_request(enc_uid, server, token)
    after_like = after_info.AccountInfo.Likes if after_info else -1

    # RESULT
    if before_like != -1 and after_like != -1:
        given = after_like - before_like
        mode = "real"
    else:
        given = success_like
        mode = "estimate"

    if given > 0:
        token_tracker[token][0] += 1
        count += 1

    return jsonify({
        "UID": int(uid),
        "PlayerNickname": nickname,
        "LikesBefore": before_like,
        "LikesAfter": after_like,
        "LikesGiven": given,
        "mode": mode,
        "remains": f"({KEY_LIMIT-count}/{KEY_LIMIT})"
    })

if __name__ == "__main__":
    app.run(debug=True)
