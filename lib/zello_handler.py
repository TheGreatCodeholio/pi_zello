import asyncio
import base64
import json
import time
import aiohttp
import socket
from lib import opus_file_stream


class ZelloSend:
    def __init__(self, config, audio_file):
        self.config = config
        self.audio = audio_file
        self.endpoint = "wss://zello.io/ws"
        self.ws_timeout = 2
        self.zello_ws = None
        self.zello_stream_id = None

    def zello_init_upload(self, loop):
        try:
            loop.run_until_complete(ZelloSend(self.config, self.audio).zello_stream_audio_to_channel())
        except KeyboardInterrupt:
            try:
                if self.zello_ws and self.zello_stream_id:
                    loop.run_until_complete(
                        ZelloSend(self.config, self.audio).zello_stream_stop(self.zello_ws, self.zello_stream_id))

            except aiohttp.client_exceptions.ClientError as error:
                print("Error during stopping. ", error)

            def shutdown_exception_handler(loop, context):
                if "exception" in context and isinstance(context["exception"], asyncio.CancelledError):
                    return
                loop.default_exception_handler(context)

            loop.set_exception_handler(shutdown_exception_handler)
            tasks = asyncio.gather(*asyncio.all_tasks(loop=loop), return_exceptions=True)
            tasks.add_done_callback(lambda t: loop.stop())
            tasks.cancel()
            while not tasks.done() and not loop.is_closed():
                loop.run_forever()
            print("Stopped by user")
            loop.close()
        finally:
            print("Stream complete.")
            # loop.close()

    async def zello_stream_audio_to_channel(self):
        # Pass out the opened WebSocket and StreamID to handle synchronous keyboard interrupt
        try:
            opus_stream = opus_file_stream.OpusFileStream(self.audio)
            conn = aiohttp.TCPConnector(family=socket.AF_INET, ssl=False)
            async with aiohttp.ClientSession(connector=conn) as session:
                async with session.ws_connect(self.endpoint) as ws:
                    self.zello_ws = ws
                    await asyncio.wait_for(ZelloSend(self.config, self.audio).authenticate(ws), self.ws_timeout)
                    stream_id = await asyncio.wait_for(
                        ZelloSend(self.config, self.audio).zello_stream_start(ws, opus_stream), self.ws_timeout)
                    self.zello_stream_id = stream_id
                    print(f"Started streaming {self.audio}")
                    await ZelloSend(self.config, self.audio).zello_stream_send_audio(session, ws, stream_id,
                                                                                     opus_stream)
                    await asyncio.wait_for(ZelloSend(self.config, self.audio).zello_stream_stop(ws, stream_id),
                                           self.ws_timeout)
        except (NameError, aiohttp.client_exceptions.ClientError, IOError) as error:
            print(error)
        except asyncio.TimeoutError:
            print("Communication timeout")

    async def authenticate(self, ws):
        # https://github.com/zelloptt/zello-channel-api/blob/master/AUTH.md
        await ws.send_str(json.dumps({
            "command": "logon",
            "seq": 1,
            "auth_token": self.config.token.decode("utf-8"),
            "username": self.config.user["username"],
            "password": self.config.user["password"],
            "channel": self.config.channel
        }))

        is_authorized = False
        is_channel_available = False
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if "refresh_token" in data:
                    is_authorized = True
                elif "command" in data and "status" in data and data["command"] == "on_channel_status":
                    is_channel_available = data["status"] == "online"
                if is_authorized and is_channel_available:
                    break

        if not is_authorized or not is_channel_available:
            raise NameError('Authentication failed')

    async def zello_stream_start(self, ws, opus_stream):
        sample_rate = opus_stream.sample_rate
        frames_per_packet = opus_stream.frames_per_packet
        packet_duration = opus_stream.packet_duration

        # Sample_rate is in little endian.
        # https://github.com/zelloptt/zello-channel-api/blob/409378acd06257bcd07e3f89e4fbc885a0cc6663/sdks/js/src/classes/utils.js#L63
        codec_header = base64.b64encode(sample_rate.to_bytes(2, "little") + frames_per_packet.to_bytes(1, "big") + packet_duration.to_bytes(1, "big")).decode()

        await ws.send_str(json.dumps({
            "command": "start_stream",
            "seq": 2,
            "type": "audio",
            "codec": "opus",
            "codec_header": codec_header,
            "packet_duration": packet_duration
        }))

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if "success" in data and "stream_id" in data and data["success"]:
                    return data["stream_id"]
                elif "error" in data:
                    print("Got an error:", data["error"])
                    break
                else:
                    # Ignore the messages we are not interested in
                    continue

        raise NameError('Failed to create Zello audio stream')

    async def zello_stream_stop(self, ws, stream_id):
        await ws.send_str(json.dumps({
            "command": "stop_stream",
            "stream_id": stream_id
        }))

    async def send_audio_packet(self, ws, packet):
        # Once the data has been sent - listen on websocket, connection may be closed otherwise.
        await ws.send_bytes(packet)
        await ws.receive()

    def generate_zello_stream_packet(self, stream_id, packet_id, data):
        # https://github.com/zelloptt/zello-channel-api/blob/master/API.md#stream-data
        return (1).to_bytes(1, "big") + stream_id.to_bytes(4, "big") + \
               packet_id.to_bytes(4, "big") + data

    async def zello_stream_send_audio(self, session, ws, stream_id, opus_stream):
        packet_duration_sec = opus_stream.packet_duration / 1000
        start_ts_sec = time.time_ns() / 1000000000
        time_streaming_sec = 0
        packet_id = 0
        while True:
            data = opus_stream.get_next_opus_packet()

            if not data:
                print("Audio stream is over")
                break

            if session.closed:
                raise NameError("Session is closed!")

            packet_id += 1
            packet = ZelloSend(self.config, self.audio).generate_zello_stream_packet(stream_id, packet_id, data)
            try:
                # Once wait_for() is timed out - it takes additional operational time.
                # Recalculate delay and sleep at the end of the loop to compensate this delay.
                await asyncio.wait_for(
                    ZelloSend(self.config, self.audio).send_audio_packet(ws, packet), packet_duration_sec * 0.8
                )
            except asyncio.TimeoutError:
                pass

            time_streaming_sec += packet_duration_sec
            time_elapsed_sec = (time.time_ns() / 1000000000) - start_ts_sec
            sleep_delay_sec = time_streaming_sec - time_elapsed_sec

            if sleep_delay_sec > 0.001:
                time.sleep(sleep_delay_sec)
