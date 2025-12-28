from flask import Flask, request, jsonify
import asyncio, time, json, binascii, requests, aiohttp
from collections import defaultdict
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson

import like_pb2
import like_count_pb2
import uid_generator_pb2

app = Flask(__name__)

KEY_LIMIT = 150
token_tracker = defaultdict(lambda: [0, time.time()])

# ---------- utils ----------
def get_today_midnight_timestamp():
    now = datetime.now()
    return datetime(now.year, now.month, now.day).timestamp()

def load_tokens(server_name):
    try:
        if server_name == "ID":
            with open("token_id.json") as f:
                return json.load(f)
        elif server_name in {"BR", "US", "SAC", "NA"}:
            with open("token_br.json") as f:
                return json.load(f)
        else:
            with open("token_bd.json") as f:
                return json.load(f)
    except:
        return []

def encrypt_message(data):
    key = b'Yg&tc%DEuh6%Zc^8'
    iv = b'6oyZDr22E3ychjM%'
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return binascii.hexlify(cipher.encrypt(pad(data, AES.block_size))).decode()

def create_uid_proto(uid):
    msg = uid_generator_pb2.uid_generator()
    msg.krishna_ = int(uid)
    msg.teamXdarks = 1
    return encrypt_message(msg.SerializeToString())

def decode_protobuf(binary):
    try:
        info = like_count_pb2.Info()
        info.ParseFromString(binary)
        return info
    except:
        return None

def make_request(enc_uid, server_name, token):
    url = (
        "https://client.us.freefiremobile.com/GetPlayerPersonalShow"
        if server_name in {"BR", "US", "SAC", "NA"}
        else "https://clientbp.ggblueshark.com/GetPlayerPersonalShow"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Dalvik/2.1.0",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        r = requests.post(url, data=bytes.fromhex(enc_uid), headers=headers, timeout=10, verify=False)
        return decode_protobuf(r.content)
    except:
        return None

async def send_like(enc_uid, token, url):
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Dalvik/2.1.0",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(url, data=bytes.fromhex(enc_uid), headers=headers):
            pass

async def send_multiple(uid, server_name, url, tokens):
    proto = like_pb2.like()
    proto.uid = int(uid)
    proto.region = server_name
    enc = encrypt_message(proto.SerializeToString())

    tasks = []
    for i in range(50):
        tasks.append(send_like(enc, tokens[i % len(tokens)]["token"], url))
    await asyncio.gather(*tasks)

# ---------- route ----------
@app.route("/like", methods=["GET"])
def like():
    uid = request.args.get("uid")
    server_name = request.args.get("server_name", "").upper()
    key = request.args.get("key")

    if key != "jenil":
        return jsonify({"error": "invalid api key"}), 403
    if not uid or not server_name:
        return jsonify({"error": "uid & server_name required"}), 400

    tokens = load_tokens(server_name)
    if not tokens:
        return jsonify({"error": "token file missing"}), 500

    token = tokens[0]["token"]
    enc_uid = create_uid_proto(uid)

    today = get_today_midnight_timestamp()
    count, last = token_tracker[token]
    if last < today:
        token_tracker[token] = [0, time.time()]
        count = 0
    if count >= KEY_LIMIT:
        return jsonify({"error": "limit reached"}), 429

    before = make_request(enc_uid, server_name, token)
    if before is None:
        return jsonify({"error": "failed fetch before"}), 502

    before_like = before.AccountInfo.Likes

    like_url = (
        "https://client.us.freefiremobile.com/LikeProfile"
        if server_name in {"BR", "US", "SAC", "NA"}
        else "https://clientbp.ggblueshark.com/LikeProfile"
    )

    try:
        loop = asyncio.get_event_loop()
    except:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(send_multiple(uid, server_name, like_url, tokens))

    after = make_request(enc_uid, server_name, token)
    if after is None:
        return jsonify({"error": "failed fetch after"}), 502

    after_like = after.AccountInfo.Likes
    given = after_like - before_like

    if given > 0:
        token_tracker[token][0] += 1
        count += 1

    return jsonify({
        "UID": after.AccountInfo.UID,
        "PlayerNickname": after.AccountInfo.PlayerNickname,
        "LikesBefore": before_like,
        "LikesAfter": after_like,
        "LikesGiven": given,
        "remains": f"({KEY_LIMIT-count}/{KEY_LIMIT})"
    })

if __name__ == "__main__":
    app.run(debug=True)
