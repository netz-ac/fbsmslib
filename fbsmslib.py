import requests
import hashlib
import time
import pyotp
import xml.etree.ElementTree as ET
from pyrate_limiter import Rate, Duration, Limiter, InMemoryBucket


class LoginState:
    def __init__(self, challenge: str, blocktime: int):
        self.challenge = challenge
        self.blocktime = blocktime
        self.is_pbkdf2 = challenge.startswith("2$")


class FBSMSLib:
    LOGIN_SID_ROUTE = "/login_sid.lua?version=2"

    rate: list[Rate] = None
    box_url: str = None
    username: str = None
    password: str = None
    totpsecret: pyotp.TOTP = None
    __sid: str = None
    __sid_timeout = None

    def __init__(
        self, url: str, username: str, password: str, totpsecret: str, rate: Rate = None
    ):
        rate = (
            [rate] if rate else [Rate(10, Duration.HOUR)]
        )  # Default rate limit: 10 requests per hour
        self._bucket = InMemoryBucket(rate)
        self._rate_limiter = Limiter(self._bucket)
        self.box_url = url
        self.username = username
        self.password = password
        self.totpsecret = pyotp.TOTP(totpsecret)
        self.get_current_sid()

    def get_current_sid(self) -> str:
        """Get a valid sid, renew if expired"""
        if self.__sid is None or time.time() > self.__sid_timeout:
            self.__sid = self._get_sid()
        self.__sid_timeout = time.time() + 19 * 60  # renew timeout
        return self.__sid

    def _get_sid(self) -> str:
        """Get a sid by solving the PBKDF2 challenge-response process."""
        try:
            state = self.get_login_state()
        except Exception as ex:
            raise Exception("failed to get challenge") from ex

        if state.is_pbkdf2:
            challenge_response = self.calculate_pbkdf2_response(state.challenge)
        else:
            raise Exception(
                "FRITZ!Box does not support PBKDF2. Please update your device firmware (v7.24 or later)."
            )

        if state.blocktime > 0:
            time.sleep(state.blocktime)

        try:
            sid = self.send_response(challenge_response)
        except Exception as ex:
            raise Exception("failed to login") from ex
        if sid == "0000000000000000":
            raise Exception("wrong username or password")
        return sid

    def get_login_state(self) -> LoginState:
        """Get login state from FRITZ!Box using login_sid.lua?version=2"""
        url = self.box_url + self.LOGIN_SID_ROUTE
        http_response = requests.get(url)
        xml = ET.fromstring(http_response.content)
        challenge = xml.find("Challenge").text
        blocktime = int(xml.find("BlockTime").text)
        return LoginState(challenge, blocktime)

    def calculate_pbkdf2_response(self, challenge: str) -> str:
        """Calculate the response for a given challenge via PBKDF2"""
        challenge_parts = challenge.split("$")
        # Extract all necessary values encoded into the challenge
        iter1 = int(challenge_parts[1])
        salt1 = bytes.fromhex(challenge_parts[2])
        iter2 = int(challenge_parts[3])
        salt2 = bytes.fromhex(challenge_parts[4])
        # Hash twice, once with static salt...
        hash1 = hashlib.pbkdf2_hmac("sha256", self.password.encode(), salt1, iter1)
        # Once with dynamic salt.
        hash2 = hashlib.pbkdf2_hmac("sha256", hash1, salt2, iter2)
        return f"{challenge_parts[4]}${hash2.hex()}"

    def send_response(self, challenge_response: str) -> str:
        """Send the response and return the parsed sid. raises an Exception on error"""
        # Build response params
        post_data = {"username": self.username, "response": challenge_response}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        url = self.box_url + self.LOGIN_SID_ROUTE
        http_response = requests.post(url, data=post_data, headers=headers)
        # Parse SID from resulting XML.
        xml = ET.fromstring(http_response.text)
        return xml.find("SID").text

    def get_sms(self) -> list:
        SMS_GET_URL = f"{self.box_url}/data.lua"

        req_data = {
            "xhr": 1,
            "sid": self.get_current_sid(),
            "lang": "de",
            "page": "smsList",
            "xhrId": "all",
        }
        try:
            sms_response = requests.post(SMS_GET_URL, data=req_data)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(e)
        return sms_response.json()["data"]["smsListData"]["messages"]

    def safe_post_request(self, url: str, data: dict) -> requests.Response:
        """Helper function to handle POST requests with error handling."""
        try:
            return requests.post(url, data=data)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Request to {url} failed: {e}")

    def enforce_rate_limit(self):
        """Enforce rate limiting for sending SMS."""
        try:
            self._rate_limiter.try_acquire("sms_send")
        except Exception as e:
            raise RuntimeError(
                "Rate limit exceeded. Please wait before sending more SMS."
            ) from e

    def send_sms(self, receiver: str, message: str):
        self.enforce_rate_limit()  # Apply rate limiting

        SMS_SEND_URL = f"{self.box_url}/data.lua"
        MFA_URL = f"{self.box_url}/twofactor.lua"

        req_data = {
            "xhr": 1,
            "sid": self.get_current_sid(),
            "lang": "de",
            "recipient": receiver,
            "page": "smsSendMsg",
            "apply": "true",
            "newMessage": message,
        }
        response1 = self.safe_post_request(SMS_SEND_URL, req_data)

        if response1.json()["data"]["apply"] != "ok":
            if response1.json()["data"]["apply"] == "valerror":
                raise RuntimeError(f"Validation error: {response1.json()['data']['valerror']}")
            raise RuntimeError(f"Failed to initiate SMS sending. Response: {response1.json()['data']}")

        # Everything done, no 2FA needed
        if "redirect" in response1.json()["data"].keys():
            return

        uid = response1.json()["data"]["new_uid"]

        req_data = {
            "xhr": 1,
            "sid": self.get_current_sid(),
            "lang": "de",
            "receipient": receiver,
            "page": "smsSendMsg",
            "second_apply": "",
            "new_uid": uid,
            "newMessage": message,
        }
        response2 = self.safe_post_request(SMS_SEND_URL, req_data)

        if response2.json()["data"]["second_apply"] == "twofactor":
            if "googleauth" in response2.json()["data"]["twofactor"]:
                # we need tfa_googleauth_info
                req_data = {
                    "xhr": 1,
                    "sid": self.get_current_sid(),
                    "tfa_googleauth_info": "",
                    "no_sidrenew": "",
                }
                self.safe_post_request(MFA_URL, req_data)

                req_data = {
                    "xhr": 1,
                    "sid": self.get_current_sid(),
                    "tfa_googleauth": self.totpsecret.now(),
                    "no_sidrenew": "",
                }
                self.safe_post_request(MFA_URL, req_data)

                req_data = {
                    "xhr": 1,
                    "sid": self.get_current_sid(),
                    "lang": "de",
                    "receipient": receiver,
                    "page": "smsSendMsg",
                    "second_apply": "",
                    "new_uid": uid,
                    "newMessage": message,
                    "confirmed": "",
                    "twofactor": "",
                }
                self.safe_post_request(SMS_SEND_URL, req_data)
            else:
                raise NotImplementedError(
                    f"Two-factor authentication method not implemented: {response2.json()['data']['twofactor']}"
                )
        else:
            raise NotImplementedError(
                f"second_apply is not two_factor: {response2.json()['data']['second_apply']}"
            )

        # return sms_response.json()['data']['smsListData']['messages']

    def send_sms_multiple(self, receiver: list[str], message: str):
        for id, r in enumerate(receiver):
            if id > 0:
                time.sleep(5)
            self.send_sms(r, message)

    def get_sms_incoming(self) -> list:
        messages = self.get_sms()
        return [i for i in messages if i["status_name"] == "received"]
