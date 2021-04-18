# Pi Zello Client
Python script to stream audio one way to a Zello channel.  Designed for Python 3.7+ Raspberry Pi 3 or 4.

Create a developer account with Zello to get credentials.  Set up a different account than what you normally use for Zello, as trying to use this script with the same account that you're using on your mobile device will cause problems.

For Zello consumer network:
- Go to https://developers.zello.com/ and click Login
- Enter your Zello username and password. If you don't have Zello account download Zello app and create one.
- Complete all fields in the developer profile and click Submit
- Click Keys and Add Key
- Copy and save Sample Development Token, Issuer, and Private Key. Make sure you copy each of the values completely using Select All.
- Click Close
- Copy the contents of the Private Key into a /etc/config.py.
- The Issuer value goes into /etc/config.py.

## etc/config.py
- username:  Zello account username to use for streaming
- password:  Zello account password to use for streaming
- channel:  name of the zello channel to stream to
- record_path: path to where you want to save recordings
- vox_delay: how long to wait at the end of a transmission before stopping recording.
- vox_length_threshold - Minimum length of recording before sent to Zello
- vox_volume_threshold - Minimum Audio level before starting record. Default: 10
- issuer:  Issuer credential from Zello account (see above)
- private_key: Private Key from Zello Development copied between two sets of triple quotes """HERE""""

## Raspberry Pi Dependancies
- Port Audio 
  - sudo apt install portaudio19-dev
- Opus Tools
   - sudo apt install opus-tools

## Python 3 Dependencies
- aiohttp~=3.7.4.post0
- PyAudio~=0.2.11
- pycryptodome~=3.10.1

## Installation
- `pip3 install -r requirements.txt`
- `sudo apt install portaudio19-dev && sudo apt install opus-tools`