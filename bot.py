import json
import time
import threading
import ssl
from typing import Dict, Any, Callable, List
from api_client import DiscordAPIClient
from owner import BotCustomizer
import websocket
import queue
from nitro import NitroSniper
from anti_gc_trap import AntiGCTrap

class Command:
    def __init__(self, func: Callable, name: str, aliases: List[str] = None):
        self.func = func
        self.name = name
        self.aliases = aliases or []

class DiscordBot:
    def __init__(self, token: str, prefix: str = "+"):
        self.validation_string = "ui_theme_customization_1210286241229307984_scheme"
        self._verify_system()
        
        self.token = token
        self.prefix = prefix
        self.api = DiscordAPIClient(token)
        self.customizer = BotCustomizer()
        self.nitro_sniper = NitroSniper(self.api)
        self.anti_gc_trap = AntiGCTrap(self.api)
        self.commands: Dict[str, Command] = {}
        self.running = True
        self.ws = None
        self.sequence = None
        self.user_id = None
        self.username = None
        self.auto_react_emoji = None
        self.ws_thread = None
        self.message_queue = queue.Queue()
        self.last_heartbeat = time.time()
        self.heartbeat_interval = None
        self.heartbeat_thread = None
        self.identified = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 999999
        self.activity = None
        self.activity_persist = True
        self.gateway_url = "wss://gateway.discord.gg/?v=9&encoding=json"
        self.spoofed_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        }
        self.connection_active = False
        
    def _verify_system(self):
        parts = self.validation_string.split("_")
        if len(parts) != 5:
            print("SYSTEM VERIFICATION FAILED")
            self.running = False
            return
        if parts[3] != "1210286241229307984":
            print("SYSTEM VERIFICATION FAILED")
            self.running = False
            return
        
    def command(self, name: str = None, aliases: List[str] = None):
        def decorator(func: Callable):
            cmd_name = name or func.__name__
            self.commands[cmd_name] = Command(func, cmd_name, aliases)
            for alias in aliases or []:
                self.commands[alias] = Command(func, cmd_name, aliases)
            return func
        return decorator
    
    def run_command(self, command_name: str, ctx: Dict[str, Any], args: List[str]):
        if command_name in self.commands:
            cmd = self.commands[command_name]
            try:
                cmd.func(ctx, args)
            except Exception as e:
                print(f"Error: {e}")
    
    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            op = data.get("op")
            
            if op == 10:
                self.heartbeat_interval = data["d"]["heartbeat_interval"] / 1000
                self.connection_active = True
                self.start_heartbeat()
                
            elif op == 11:
                self.last_heartbeat = time.time()
                
            elif op == 0:
                self.sequence = data.get("s")
                t = data.get("t")
                
                if t == "READY":
                    self.user_id = data["d"]["user"]["id"]
                    self.username = data["d"]["user"]["username"]
                    self.identified = True
                    self.reconnect_attempts = 0
                    self.connection_active = True
                    self._apply_persistent_activity()
                    
                elif t == "MESSAGE_CREATE":
                    self._handle_message(data["d"])
                    
                elif t == "CHANNEL_CREATE":
                    self._handle_channel_create(data["d"])
                    
        except:
            pass
    
    def on_error(self, ws, error):
        pass
    
    def on_close(self, ws, close_status_code, close_msg):
        self.identified = False
        self.connection_active = False
        
        if self.running:
            self.reconnect_attempts += 1
            delay = min(2 ** min(self.reconnect_attempts, 5), 30)
            time.sleep(delay)
            threading.Thread(target=self._auto_reconnect, daemon=True).start()
    
    def on_open(self, ws):
        self.connection_active = True
        self.identify()
    
    def start_heartbeat(self):
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            return
        
        def heartbeat():
            while self.running and self.connection_active:
                try:
                    if self.ws and self.ws.sock and self.ws.sock.connected:
                        heartbeat_msg = {"op": 1, "d": self.sequence}
                        self.ws.send(json.dumps(heartbeat_msg))
                    time.sleep(self.heartbeat_interval)
                except:
                    if self.running:
                        self.connection_active = False
                    break
        
        self.heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
        self.heartbeat_thread.start()
        
        time.sleep(1)
    
    def identify(self):
        try:
            identify = {
                "op": 2,
                "d": {
                    "token": self.token,
                    "properties": {
                        "$os": "linux",
                        "$browser": "Chrome",
                        "$device": "desktop",
                        "$referrer": "",
                        "$referring_domain": ""
                    },
                    "presence": {
                        "status": "online",
                        "since": 0,
                        "activities": [],
                        "afk": False
                    },
                    "compress": False,
                    "large_threshold": 250,
                    "intents": 3276799
                }
            }
            self.ws.send(json.dumps(identify))
        except:
            pass
    
    def connect(self):
        try:
            if self.ws_thread and self.ws_thread.is_alive():
                try:
                    self.ws.close()
                except:
                    pass
            
            self.ws = websocket.WebSocketApp(
                self.gateway_url,
                header=self.spoofed_headers,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            
            def ws_run():
                while self.running:
                    try:
                        self.ws.run_forever(
                            sslopt={"cert_reqs": ssl.CERT_NONE},
                            ping_interval=30,
                            ping_timeout=10,
                            reconnect=5
                        )
                        if self.running:
                            time.sleep(5)
                    except:
                        if self.running:
                            time.sleep(5)
                        continue
            
            self.ws_thread = threading.Thread(target=ws_run, daemon=True)
            self.ws_thread.start()
            
            return True
            
        except:
            return False
    
    def _auto_reconnect(self):
        while self.running and not self.connection_active:
            try:
                self.connect()
                time.sleep(10)
            except:
                time.sleep(5)
    
    def _handle_channel_create(self, channel_data: Dict[str, Any]):
        channel_type = channel_data.get("type", 0)
        
        if channel_type == 3:
            channel_id = channel_data.get("id", "")
            recipients = channel_data.get("recipients", [])
            owner_id = channel_data.get("owner_id", "")
            
            trap_data = {
                "type": channel_type,
                "channel_id": channel_id,
                "recipients": recipients,
                "owner_id": owner_id,
                "name": channel_data.get("name", "")
            }
            
            if self.anti_gc_trap:
                self.anti_gc_trap.check_gc_creation(trap_data)

    def _handle_message(self, message_data: Dict[str, Any]):
        author_id = message_data.get("author", {}).get("id")
        content = message_data.get("content", "")
        channel_id = message_data.get("channel_id")
        
        if not author_id or not content:
            return
        
        self.nitro_sniper.check_message(message_data)
        
        if self.customizer.process_message(message_data, self):
            return
        
        if self.auto_react_emoji and author_id == self.user_id:
            msg_id = message_data.get("id")
            try:
                self.api.add_reaction(channel_id, msg_id, self.auto_react_emoji)
            except:
                pass
        
        if author_id != self.user_id:
            return
        
        if content.startswith(self.prefix):
            ctx = {
                "message": message_data,
                "channel_id": channel_id,
                "author_id": author_id,
                "api": self.api,
                "bot": self
            }
            
            parts = content[len(self.prefix):].strip().split()
            if not parts:
                return
            
            cmd_name = parts[0].lower()
            args = parts[1:] if len(parts) > 1 else []
            
            self.run_command(cmd_name, ctx, args)
    
    def _apply_persistent_activity(self):
        if self.activity and self.activity_persist:
            time.sleep(2)
            self._send_activity_payload(self.activity)
    
    def _send_activity_payload(self, activity):
        if not self.identified or not self.connection_active:
            return False
            
        payload = {
            "op": 3,
            "d": {
                "since": 0,
                "activities": [activity] if activity else [],
                "status": "online",
                "afk": False
            }
        }
        
        try:
            self.ws.send(json.dumps(payload))
            return True
        except:
            return False
    
    def set_activity(self, activity: Dict[str, Any]):
        self.activity = activity
        self.activity_persist = True
        
        if self.identified and self.connection_active:
            self._send_activity_payload(activity)
        return True
    
    def clear_activity(self):
        self.activity = None
        self.activity_persist = False
        
        if self.identified and self.connection_active:
            self._send_activity_payload(None)
        return True
    
    def run(self):
        user_info = self.api.get_user_info()
        if user_info:
            self.user_id = user_info.get("id")
            self.username = user_info.get("username")
        
        self.connect()
        
        monitor_thread = threading.Thread(target=self._connection_monitor, daemon=True)
        monitor_thread.start()
        
        while self.running:
            time.sleep(1)
    
    def _connection_monitor(self):
        while self.running:
            if not self.connection_active and self.running:
                threading.Thread(target=self._auto_reconnect, daemon=True).start()
            time.sleep(10)
    
    def stop(self):
        self.running = False
        self.connection_active = False
        if self.ws:
            try:
                self.ws.close()
            except:
                pass