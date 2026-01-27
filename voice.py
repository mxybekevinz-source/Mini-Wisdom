import json
import asyncio
import websockets
import time
import threading
import ssl
import socket
import struct
import random
import urllib.parse

class VoiceClient:
    def __init__(self, api_client, token):
        self.api = api_client
        self.token = token
        self.voice_ws = None
        self.gateway_ws = None
        self.udp_socket = None
        self.voice_thread = None
        self.gateway_thread = None
        self.running = False
        self.gateway_running = False
        self.voice_gateway_url = None
        self.session_id = None
        self.token_v = None
        self.endpoint = None
        self.guild_id = None
        self.channel_id = None
        self.user_id = None
        self.sequence = None
        self.heartbeat_interval = None
        self.ssrc = None
        self.secret_key = None
        self.speaking = False
        self.is_dm_call = False
        self.call_channel_id = None
    
    def connect_to_voice(self, target_id, is_dm=False):
        if is_dm:
            return self._connect_to_dm_voice(target_id)
        else:
            return self._connect_to_guild_voice(target_id)
    
    def _connect_to_guild_voice(self, channel_id):
        self.channel_id = channel_id
        self.is_dm_call = False
        
        guild_id = self._get_guild_id_from_channel(channel_id)
        if not guild_id:
            print(f"No guild found for channel {channel_id}")
            return False
        
        self.guild_id = guild_id
        self.user_id = self.api.user_id
        
        print(f"Joining server voice: guild={guild_id}, channel={channel_id}")
        
        response = self.api.request("POST", f"/guilds/{guild_id}/voice-states/@me", data={
            "channel_id": channel_id,
            "self_mute": False,
            "self_deaf": False
        })
        
        if response and response.status_code in [200, 204]:
            print(f"Server voice join request successful")
            self.voice_thread = threading.Thread(target=self._voice_connect_thread, daemon=True)
            self.voice_thread.start()
            return True
        
        print(f"Server voice join failed: {response.status_code if response else 'No response'}")
        return False
    
    def _connect_to_dm_voice(self, channel_id):
        self.call_channel_id = channel_id
        self.is_dm_call = True
        
        print(f"Starting DM voice call in channel {channel_id}")
        
        self.gateway_thread = threading.Thread(target=self._gateway_connect_thread, daemon=True)
        self.gateway_thread.start()
        return True
    
    def _get_guild_id_from_channel(self, channel_id):
        user_guilds = self.api.get_guilds()
        for guild in user_guilds:
            guild_channels = self.api.get_channels(guild['id'])
            for channel in guild_channels:
                if str(channel['id']) == str(channel_id):
                    return guild['id']
        return None
    
    def _voice_connect_thread(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._connect_voice_gateway())
    
    def _gateway_connect_thread(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._connect_main_gateway())
    
    async def _connect_main_gateway(self):
        self.gateway_running = True
        
        try:
            ws_url = "wss://gateway.discord.gg/?v=9&encoding=json"
            
            ws = await websockets.connect(
                ws_url,
                max_size=None,
                ping_interval=20,
                ping_timeout=20
            )
            
            self.gateway_ws = ws
            
            await self._identify_gateway(ws)
            await self._start_call(ws)
            
            async for message in ws:
                await self._handle_gateway_message(ws, message)
                
        except Exception as e:
            print(f"Gateway error: {e}")
        finally:
            self.gateway_running = False
            if self.gateway_ws:
                await self.gateway_ws.close()
    
    async def _identify_gateway(self, ws):
        identify = {
            "op": 2,
            "d": {
                "token": self.token,
                "properties": {
                    "$os": "windows",
                    "$browser": "Chrome",
                    "$device": ""
                },
                "presence": {
                    "status": "online",
                    "activities": [],
                    "afk": False
                },
                "compress": False,
                "large_threshold": 250,
                "intents": 513
            }
        }
        await ws.send(json.dumps(identify))
        print("Sent identify to gateway")
    
    async def _start_call(self, ws):
        call_data = {
            "op": 4,
            "d": {
                "guild_id": None,
                "channel_id": str(self.call_channel_id),
                "self_mute": True,
                "self_deaf": False,
                "self_video": False
            }
        }
        await ws.send(json.dumps(call_data))
        print(f"Started DM call in channel {self.call_channel_id}")
    
    async def _handle_gateway_message(self, ws, message):
        try:
            if len(message) > 1000000:
                print(f"Received large message ({len(message)} bytes), skipping...")
                return
                
            data = json.loads(message)
            op = data.get("op")
            t = data.get("t")
            
            if op == 10:
                self.heartbeat_interval = data["d"]["heartbeat_interval"] / 1000
                print(f"Gateway heartbeat interval: {self.heartbeat_interval}s")
                asyncio.create_task(self._gateway_heartbeat(ws))
            
            elif op == 0:
                if t == "VOICE_STATE_UPDATE":
                    voice_data = data["d"]
                    if voice_data.get("user_id") == self.api.user_id:
                        self.session_id = voice_data.get("session_id")
                        self.token_v = voice_data.get("token")
                        self.endpoint = voice_data.get("endpoint")
                        
                        if self.endpoint:
                            self.endpoint = self.endpoint.replace(':443', '')
                            print(f"Got voice endpoint: {self.endpoint}")
                            self.voice_thread = threading.Thread(target=self._voice_connect_thread, daemon=True)
                            self.voice_thread.start()
                
                elif t == "READY":
                    print("Gateway ready - skipping large READY data")
            
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
        except Exception as e:
            print(f"Gateway message error: {e}")
    
    async def _gateway_heartbeat(self, ws):
        while self.gateway_running:
            try:
                heartbeat_msg = {"op": 1, "d": self.sequence}
                await ws.send(json.dumps(heartbeat_msg))
                await asyncio.sleep(self.heartbeat_interval)
            except:
                break
    
    async def _connect_voice_gateway(self):
        if not self.endpoint or not self.token_v or not self.session_id:
            print("Missing voice connection data")
            return
        
        self.voice_gateway_url = f"wss://{self.endpoint}/?v=4"
        print(f"Connecting to voice gateway: {self.voice_gateway_url}")
        
        try:
            ws = await websockets.connect(
                self.voice_gateway_url,
                max_size=None,
                ping_interval=20,
                ping_timeout=20
            )
            self.voice_ws = ws
            self.running = True
            
            await self._voice_identify(ws)
            
            async for message in ws:
                await self._handle_voice_message(ws, message)
                
        except Exception as e:
            print(f"Voice gateway error: {e}")
        finally:
            self.running = False
            if self.voice_ws:
                await self.voice_ws.close()
    
    async def _voice_identify(self, ws):
        server_id = str(self.guild_id) if self.guild_id else None
        identify = {
            "op": 0,
            "d": {
                "server_id": server_id,
                "user_id": str(self.api.user_id),
                "session_id": self.session_id,
                "token": self.token_v
            }
        }
        await ws.send(json.dumps(identify))
        print(f"Voice identified for {'DM call' if self.is_dm_call else 'server voice'}")
    
    async def _handle_voice_message(self, ws, message):
        try:
            data = json.loads(message)
            op = data.get('op')
            
            if op == 2:
                self.ssrc = data['d']['ssrc']
                self.secret_key = data['d']['secret_key']
                self.heartbeat_interval = data['d']['heartbeat_interval'] / 1000
                
                print(f"✓ Voice ready! SSRC: {self.ssrc}")
                print(f"✓ Successfully connected to voice!")
                asyncio.create_task(self._voice_heartbeat(ws))
                await self._select_protocol(ws)
                
            elif op == 4:
                await self._speaking(ws, True)
                print("Speaking enabled")
                
            elif op == 8:
                self.heartbeat_interval = data['d']['heartbeat_interval'] / 1000
                
        except Exception as e:
            print(f"Voice message error: {e}")
    
    async def _voice_heartbeat(self, ws):
        while self.running:
            try:
                heartbeat_msg = {"op": 3, "d": None}
                await ws.send(json.dumps(heartbeat_msg))
                await asyncio.sleep(self.heartbeat_interval)
            except:
                break
    
    async def _select_protocol(self, ws):
        select_protocol = {
            "op": 1,
            "d": {
                "protocol": "udp",
                "data": {
                    "address": "127.0.0.1",
                    "port": 0,
                    "mode": "xsalsa20_poly1305"
                }
            }
        }
        await ws.send(json.dumps(select_protocol))
    
    async def _speaking(self, ws, speaking):
        speaking_msg = {
            "op": 5,
            "d": {
                "speaking": 1 if speaking else 0,
                "delay": 0,
                "ssrc": self.ssrc
            }
        }
        await ws.send(json.dumps(speaking_msg))
        self.speaking = speaking
    
    def disconnect(self):
        self.running = False
        self.gateway_running = False
        
        if self.guild_id and not self.is_dm_call:
            try:
                self.api.request("POST", f"/guilds/{self.guild_id}/voice-states/@me", data={
                    "channel_id": None
                })
                print(f"Left server voice channel")
            except:
                pass
        
        print(f"Disconnected from {'DM call' if self.is_dm_call else 'server voice'}")

class SimpleVoice:
    def __init__(self, api_client, token):
        self.api = api_client
        self.token = token
        self.active_connections = {}
    
    def join_vc(self, target_id, is_dm=False):
        connection_key = f"dm_{target_id}" if is_dm else f"guild_{target_id}"
        
        if connection_key in self.active_connections:
            self.leave_vc(target_id, is_dm)
        
        print(f"Connecting to {'DM' if is_dm else 'server'} voice: {target_id}")
        voice_client = VoiceClient(self.api, self.token)
        success = voice_client.connect_to_voice(target_id, is_dm)
        
        if success:
            self.active_connections[connection_key] = voice_client
            time.sleep(3)
            return True
        return False
    
    def leave_vc(self, target_id=None, is_dm=False):
        if target_id:
            connection_key = f"dm_{target_id}" if is_dm else f"guild_{target_id}"
            if connection_key in self.active_connections:
                print(f"Disconnecting from {connection_key}")
                success = self.active_connections[connection_key].disconnect()
                del self.active_connections[connection_key]
                return success
        else:
            success = True
            for key, client in list(self.active_connections.items()):
                print(f"Disconnecting from {key}")
                if not client.disconnect():
                    success = False
                del self.active_connections[key]
            return success
        return False
    
    def is_in_voice(self, target_id=None, is_dm=False):
        if target_id:
            connection_key = f"dm_{target_id}" if is_dm else f"guild_{target_id}"
            return connection_key in self.active_connections
        return len(self.active_connections) > 0