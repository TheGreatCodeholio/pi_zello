import pyaudio
import math
import struct
import wave
import time
import os
import subprocess
import datetime
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Hash import SHA256
from threading import Thread
import etc.config as config
from lib.zello_handler import ZelloSend
import base64
import json

Threshold = config.vox_volume_threshold

SHORT_NORMALIZE = (1.0 / 32768.0)
chunk = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
swidth = 2

TIMEOUT_LENGTH = config.vox_delay
RECORDING_LENGTH_THRESHOLD = config.vox_length_threshold
f_name_directory = config.record_path + "/" + config.channel.replace(" ", "")


class Recorder:

    @staticmethod
    def rms(frame):
        count = len(frame) / swidth
        format = "%dh" % (count)
        shorts = struct.unpack(format, frame)

        sum_squares = 0.0
        for sample in shorts:
            n = sample * SHORT_NORMALIZE
            sum_squares += n * n
        rms = math.pow(sum_squares / count, 0.5)

        return rms * 1000

    def __init__(self):
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=FORMAT,
                                  channels=CHANNELS,
                                  rate=RATE,
                                  input=True,
                                  output=True,
                                  frames_per_buffer=chunk)

    def record(self):
        print('Noise detected, recording beginning')
        rec = []
        rec_start = time.time()
        current = time.time()
        end = time.time() + TIMEOUT_LENGTH

        while current <= end:

            data = self.stream.read(chunk)
            if self.rms(data) >= Threshold: end = time.time() + TIMEOUT_LENGTH

            current = time.time()
            rec.append(data)
        rec_length = time.time() - rec_start
        config.token = self.create_token()
        self.write(rec_length, b''.join(rec))

    def write(self, rec_length, recording):
        if rec_length > RECORDING_LENGTH_THRESHOLD:
            x = datetime.datetime.now()
            if not os.path.exists(f_name_directory):
                os.mkdir(f_name_directory)
            if not os.path.exists(f_name_directory + "/" + str(x.year)):
                os.mkdir(f_name_directory + "/" + str(x.year))
            if not os.path.exists(f_name_directory + "/" + str(x.year) + "/" + str(x.month)):
                os.mkdir(f_name_directory + "/" + str(x.year) + "/" + str(x.month))
            if not os.path.exists(f_name_directory + "/" + str(x.year) + "/" + str(x.month) + "/" + str(x.day)):
                os.mkdir(f_name_directory + "/" + str(x.year) + "/" + str(x.month) + "/" + str(x.day))

            file_path = f_name_directory + "/" + str(x.year) + "/" + str(x.month) + "/" + str(x.day)
            file_name = str(x.hour) + str(x.minute) + "_" + str(x.second)

            wf = wave.open(file_path + "/" + file_name + ".wav", 'wb')
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(recording)
            wf.close()
            print('Written to file: {}'.format(file_path + "/" + file_name))
            subprocess.call(
                "opusenc " + file_path + "/" + file_name + ".wav" + " " + file_path + "/" + file_name + ".opus",
                shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
            if os.path.exists(file_path + "/" + file_name + ".wav"):
                os.remove(file_path + "/" + file_name + ".wav")

            print("Sending To Zello")
            ZelloSend(config, file_path + "/" + file_name + ".opus").zello_init_upload()

            print('Returning to listening')
        else:
            print("Recording too short not saving.")

    def listen(self):
        print('Listening beginning')
        while True:
            input = self.stream.read(chunk)
            rms_val = self.rms(input)
            if rms_val > Threshold:
                self.record()

    def create_token(self):
        key = RSA.import_key(config.private_key)
        # Create a Zello-specific JWT.  Can't use PyJWT because Zello doesn't support url safe base64 encoding in the JWT.
        header = {"typ": "JWT", "alg": "RS256"}
        payload = {"iss": config.issuer, "exp": round(time.time() + 60)}
        signer = pkcs1_15.new(key)
        json_header = json.dumps(header, separators=(",", ":"), cls=None).encode("utf-8")
        json_payload = json.dumps(payload, separators=(",", ":"), cls=None).encode("utf-8")
        h = SHA256.new(base64.standard_b64encode(json_header) + b"." + base64.standard_b64encode(json_payload))
        signature = signer.sign(h)
        token = (base64.standard_b64encode(json_header) + b"." + base64.standard_b64encode(
            json_payload) + b"." + base64.standard_b64encode(signature))
        return token


a = Recorder()

a.listen()
