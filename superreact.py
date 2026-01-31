import json
import time
import threading
import concurrent.futures
import tls_client
import random
import base64
import re
from urllib.parse import quote as url_quote

class SuperReact:
    def __init__(self, bot):
        self.bot = bot
        self.token = bot.token
        self.api = bot.api
        self.USER_ID = bot.user_id
        self.FINGERPRINT = None
        self.COOKIES = ""
        self.targets = {}
        self.msr_targets = {}
        self.ssr_targets = {}
        self.emojis = ['👍', '👎', '😂', '❤️', '😍', '🔥', '😭', '🤔', '😎', '🥰', '🤯', '😢', '🙌', '👏', '💯', '⭐', '🎉', '🚀', '💥', '🌟']
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5, thread_name_prefix="SuperReact")
        self.init()

    def create_tls_session(self):
        return tls_client.Session(
            client_identifier="chrome_138",
            random_tls_extension_order=True,
            ja3_string="771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,0-5-10-11-13-16-18-23-27-35-43-45-51-17613-65037-65281,4588-29-23-24,0",
            h2_settings={"HEADER_TABLE_SIZE": 65536, "ENABLE_PUSH": 0, "INITIAL_WINDOW_SIZE": 6291456, "MAX_HEADER_LIST_SIZE": 262144},
            h2_settings_order=["HEADER_TABLE_SIZE", "ENABLE_PUSH", "INITIAL_WINDOW_SIZE", "MAX_HEADER_LIST_SIZE"],
            supported_signature_algorithms=[
                "ecdsa_secp256r1_sha256", "rsa_pss_rsae_sha256", "rsa_pkcs1_sha256",
                "ecdsa_secp384r1_sha384", "rsa_pss_rsae_sha384", "rsa_pkcs1_sha384",
                "rsa_pss_rsae_sha512", "rsa_pkcs1_sha512"
            ],
            supported_versions=["TLS_1_3", "TLS_1_2"],
            key_share_curves=["GREASE", "X25519MLKEM768", "X25519", "secp256r1", "secp384r1"],
            pseudo_header_order=[":method", ":authority", ":scheme", ":path"],
            connection_flow=15663105,
            priority_frames=[]
        )

    def init(self):
        try:
            session = self.create_tls_session()
            r = session.get("https://discord.com/api/v9/experiments")
            if r.status_code != 200:
                raise Exception(f"Status {r.status_code}")
            self.FINGERPRINT = r.json().get("fingerprint", "")
            self.COOKIES = "; ".join(f"{c.name}={c.value}" for c in r.cookies) + "; locale=en-US"
            print(f"[SUCCESS]: Fingerprint acquired.")
            return True
        except Exception as e:
            print(f"[ERROR]: Couldnt get fingerprint, {e}.")
            return False

    def sp(self):
        p = {
            "os": "Windows", "browser": "Chrome", "device": "", "system_locale": "en-US",
            "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "browser_version": "138.0.0.0", "os_version": "10", "referrer": "", "referring_domain": "",
            "release_channel": "stable", "client_build_number": 429117, "client_event_source": None
        }
        return base64.b64encode(json.dumps(p).encode()).decode()

    def hdr(self):
        return {
            "authority": "discord.com",
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "authorization": self.token,
            "cookie": self.COOKIES,
            "content-type": "application/json",
            "origin": "https://discord.com",
            "referer": "https://discord.com/channels/@me",
            "sec-ch-ua": '"Google Chrome";v="138", "Chromium";v="138", "Not=A?Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "x-discord-locale": "en-US",
            "x-fingerprint": self.FINGERPRINT,
            "x-super-properties": self.sp()
        }

    def send_super_reaction_rest(self, guild_id, channel_id, message_id, emoji):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                session = self.create_tls_session()
                is_custom = emoji.startswith("<a:") or emoji.startswith("<:")
                path = (f"{emoji.replace('<','').replace('>','').split(':')[1]}:{emoji.replace('<','').replace('>','').split(':')[2]}" if is_custom else url_quote(emoji))
                g_id = guild_id or "@me"
                headers = self.hdr()
                headers.update({"referer": f"https://discord.com/channels/{g_id}/{channel_id}"})
                url = f"https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}/reactions/{path}/@me"
                params = {"location": "Message Reaction Picker", "type": 1}
                res = session.put(url, headers=headers, params=params)
                if res.status_code == 429:
                    retry_after = float(res.headers.get('Retry-After', 1))
                    print(f"[RATE LIMIT]: Waiting {retry_after}s for reaction.")
                    time.sleep(retry_after)
                    continue
                elif res.status_code >= 500:
                    wait = (2 ** attempt) + (0.1 * attempt)  
                    print(f"[SERVER ERROR]: Retry {attempt+1}/{max_retries} after {wait:.1f}s.")
                    time.sleep(wait)
                    continue
                if res.status_code != 204:
                    raise Exception(f"Unexpected status {res.status_code}")
                print(f"[SUCCESS]: Super reaction succeeded.")
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                raise
        raise Exception("Failed after retries")

    def _react_single(self, guild_id, channel_id, msg_id, emoji):
        try:
            self.send_super_reaction_rest(guild_id, channel_id, msg_id, emoji)
        except Exception as e:
            print(f"[ERROR]: Failed to react to msg {msg_id}: {e}")

    def parse_target_id(self, target_arg):
        if target_arg == "@me":
            return self.USER_ID
        cleaned = target_arg.strip('<@!>').replace('&', '')
        return cleaned if cleaned.isdigit() else None
