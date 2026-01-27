import json
import time
import base64
import threading
from datetime import datetime
import requests

class AntiGCTrap:
    def __init__(self, api_client):
        self.api = api_client
        self.enabled = False
        self.block_creators = False
        self.leave_message = "loser ass nigga"
        self.gc_name = "u cant trap a god"
        self.gc_icon_url = None
        self.webhook_url = None
        self.whitelist = set()
        self.load_whitelist()
        
    def load_whitelist(self):
        try:
            with open("agc_whitelist.json", "r") as f:
                data = json.load(f)
                self.whitelist = set(data.get("whitelist", []))
                self.webhook_url = data.get("webhook_url")
                return True
        except:
            return False
    
    def save_whitelist(self):
        data = {
            "whitelist": list(self.whitelist),
            "webhook_url": self.webhook_url
        }
        with open("agc_whitelist.json", "w") as f:
            json.dump(data, f, indent=2)
    
    def check_gc_creation(self, message_data):
        if not self.enabled:
            return False
        
        channel_id = message_data.get("channel_id", "")
        channel_type = message_data.get("type", 0)
        
        if channel_type != 3:  # Not a group DM
            return False
        
        print(f"[GC TRAP] New group DM detected: {channel_id}")
        
        threading.Thread(target=self._handle_gc_trap, args=(channel_id,), daemon=True).start()
        return True
    
    def _handle_gc_trap(self, channel_id):
        time.sleep(1)
        
        try:
            channel_info = self.api.request("GET", f"/channels/{channel_id}")
            if not channel_info or channel_info.status_code != 200:
                return
            
            channel_data = channel_info.json()
            recipients = channel_data.get("recipients", [])
            owner_id = channel_data.get("owner_id", "")
            
            if not recipients or len(recipients) <= 1:
                return
            
            print(f"[GC TRAP] GC with {len(recipients)} members, owner: {owner_id}")
            
            if owner_id in self.whitelist:
                print(f"[GC TRAP] Owner {owner_id} is whitelisted, skipping")
                return
            
            if owner_id == self.api.user_id:
                return
            
            self._rename_gc(channel_id)
            self._change_gc_icon(channel_id)
            self._send_leave_message(channel_id)
            
            if self.block_creators and owner_id:
                self._block_creator(owner_id)
            
            self._leave_gc(channel_id)
            self._send_webhook_alert(channel_id, channel_data, owner_id, recipients)
            
        except Exception as e:
            print(f"[GC TRAP Error] {e}")
    
    def _rename_gc(self, channel_id):
        try:
            data = {"name": self.gc_name}
            response = self.api.request("PATCH", f"/channels/{channel_id}", data=data)
            if response and response.status_code == 200:
                print(f"[GC TRAP] Renamed GC to: {self.gc_name}")
        except:
            pass
    
    def _change_gc_icon(self, channel_id):
        if not self.gc_icon_url:
            return
        
        try:
            response = requests.get(self.gc_icon_url, timeout=5)
            if response.status_code == 200:
                image_bytes = response.content
                
                image_format = "png"
                if b'\x47\x49\x46\x38' in image_bytes[:6]:  # GIF
                    image_format = "gif"
                elif b'\xFF\xD8\xFF' in image_bytes[:3]:  # JPEG
                    image_format = "jpeg"
                
                image_b64 = base64.b64encode(image_bytes).decode()
                icon_data = f"data:image/{image_format};base64,{image_b64}"
                
                data = {"icon": icon_data}
                response = self.api.request("PATCH", f"/channels/{channel_id}", data=data)
                if response and response.status_code == 200:
                    print(f"[GC TRAP] Changed GC icon")
        except:
            pass
    
    def _send_leave_message(self, channel_id):
        try:
            self.api.send_message(channel_id, self.leave_message)
            print(f"[GC TRAP] Sent leave message")
        except:
            pass
    
    def _block_creator(self, user_id):
        try:
            response = self.api.request("PUT", f"/users/@me/relationships/{user_id}", data={"type": 2})
            if response and response.status_code in [200, 204]:
                print(f"[GC TRAP] Blocked creator: {user_id}")
        except:
            pass
    
    def _leave_gc(self, channel_id):
        try:
            response = self.api.request("DELETE", f"/channels/{channel_id}")
            if response and response.status_code in [200, 204]:
                print(f"[GC TRAP] Left GC")
        except:
            pass
    
    def _send_webhook_alert(self, channel_id, channel_data, owner_id, recipients):
        if not self.webhook_url:
            return
        
        try:
            owner_info = None
            if owner_id:
                user_response = self.api.request("GET", f"/users/{owner_id}")
                if user_response and user_response.status_code == 200:
                    owner_info = user_response.json()
            
            recipient_names = []
            for recipient in recipients[:10]:
                if isinstance(recipient, dict):
                    name = recipient.get("username", "Unknown")
                    recipient_names.append(f"@{name}")
            
            if len(recipients) > 10:
                recipient_names.append(f"... and {len(recipients) - 10} more")
            
            embed = {
                "title": "🚨 Anti-GC Trap Triggered",
                "description": f"**GC ID:** `{channel_id}`\n**GC Name:** `{channel_data.get('name', 'Unnamed')}`",
                "color": 0xff0000,
                "fields": [
                    {"name": "Owner", "value": f"<@{owner_id}>" if owner_id else "Unknown", "inline": True},
                    {"name": "Members", "value": str(len(recipients)), "inline": True},
                    {"name": "Blocked Creator", "value": "✅" if self.block_creators else "❌", "inline": True},
                    {"name": "Recipients", "value": ", ".join(recipient_names) if recipient_names else "None", "inline": False}
                ],
                "timestamp": datetime.now().isoformat(),
                "footer": {"text": "Wisdom Anti-GC Trap System"}
            }
            
            if owner_info:
                avatar_hash = owner_info.get("avatar")
                if avatar_hash:
                    avatar_format = "gif" if avatar_hash.startswith("a_") else "png"
                    avatar_url = f"https://cdn.discordapp.com/avatars/{owner_id}/{avatar_hash}.{avatar_format}"
                    embed["thumbnail"] = {"url": avatar_url}
            
            data = {
                "embeds": [embed],
                "username": "Wisdom Security"
            }
            
            requests.post(self.webhook_url, json=data, timeout=5)
            print(f"[GC TRAP] Sent webhook alert")
            
        except Exception as e:
            print(f"[GC TRAP Webhook Error] {e}")
    
    def add_to_whitelist(self, user_id):
        self.whitelist.add(str(user_id))
        self.save_whitelist()
        return True
    
    def remove_from_whitelist(self, user_id):
        if str(user_id) in self.whitelist:
            self.whitelist.remove(str(user_id))
            self.save_whitelist()
            return True
        return False
    
    def get_whitelist(self):
        return list(self.whitelist)

anti_gc_trap = None