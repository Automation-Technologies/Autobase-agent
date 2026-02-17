from time import time
import base64
import time
import requests
from time import time
from http import HTTPStatus
from base64 import b64encode
from rsa import encrypt, PublicKey
from requests import Session, Response
from steampy import guard
from steampy.models import SteamUrl
from steampy.exceptions import InvalidCredentials, CaptchaRequired, ApiException
import rsa
import json
from urllib.parse import urlparse
from typing import Optional

# Список ошибок Steam (код и текстовое описание)
errors = [
    {"x": 1, "text": "All good! No error. (k_EResultOK)"},
    {"x": 2, "text": "Generic failure. (k_EResultFail)"},
    {"x": 3, "text": "No Steam connection. (k_EResultNoConnection)"},
    {"x": 5, "text": "Invalid password or ticket. (k_EResultInvalidPassword)"},
    {"x": 6, "text": "This user is logged in from another location. (k_EResultLoggedInElsewhere)"},
    {"x": 7, "text": "Invalid protocol version. (k_EResultInvalidProtocolVer)"},
    {"x": 8, "text": "Invalid parameter. (k_EResultInvalidParam)"},
    {"x": 9, "text": "File not found. (k_EResultFileNotFound)"},
    {"x": 10, "text": "Called method is busy, no action taken. (k_EResultBusy)"},
    {"x": 11, "text": "Invalid state. (k_EResultInvalidState)"},
    {"x": 12, "text": "Invalid name. (k_EResultInvalidName)"},
    {"x": 13, "text": "Invalid email address. (k_EResultInvalidEmail)"},
    {"x": 14, "text": "Duplicate name, not unique. (k_EResultDuplicateName)"},
    {"x": 15, "text": "Access denied. (k_EResultAccessDenied)"},
    {"x": 16, "text": "Operation timed out. (k_EResultTimeout)"},
    {"x": 17, "text": "User is VAC banned. (k_EResultBanned)"},
    {"x": 18, "text": "Account not found. (k_EResultAccountNotFound)"},
    {"x": 19, "text": "Invalid SteamID. (k_EResultInvalidSteamID)"},
    {"x": 20, "text": "Requested service is unavailable. (k_EResultServiceUnavailable)"},
    {"x": 21, "text": "User not logged in. (k_EResultNotLoggedOn)"},
    {"x": 22, "text": "Request is pending. (k_EResultPending)"},
    {"x": 23, "text": "Encryption or decryption failed. (k_EResultEncryptionFailure)"},
    {"x": 24, "text": "Insufficient privilege. (k_EResultInsufficientPrivilege)"},
    {"x": 25, "text": "Limit exceeded. (k_EResultLimitExceeded)"},
    {"x": 26, "text": "Access revoked. (k_EResultRevoked)"},
    {"x": 27, "text": "Expired license or guest pass. (k_EResultExpired)"},
    {"x": 28, "text": "Guest pass already redeemed. (k_EResultAlreadyRedeemed)"},
    {"x": 29, "text": "Duplicate request, ignoring. (k_EResultDuplicateRequest)"},
    {"x": 30, "text": "All requested games are already owned. (k_EResultAlreadyOwned)"},
    {"x": 31, "text": "IP address not found. (k_EResultIPNotFound)"},
    {"x": 32, "text": "Persist failed, unable to save changes. (k_EResultPersistFailed)"},
    {"x": 33, "text": "Locking failed. (k_EResultLockingFailed)"},
    {"x": 34, "text": "Logon session replaced. (k_EResultLogonSessionReplaced)"},
    {"x": 35, "text": "Connect failed. (k_EResultConnectFailed)"},
    {"x": 36, "text": "Handshake failed. (k_EResultHandshakeFailed)"},
    {"x": 37, "text": "General I/O failure. (k_EResultIOFailure)"},
    {"x": 38, "text": "Remote disconnect. (k_EResultRemoteDisconnect)"},
    {"x": 39, "text": "Shopping cart not found. (k_EResultShoppingCartNotFound)"},
    {"x": 40, "text": "Action blocked by the user. (k_EResultBlocked)"},
    {"x": 41, "text": "Target is ignoring the sender. (k_EResultIgnored)"},
    {"x": 42, "text": "No match found. (k_EResultNoMatch)"},
    {"x": 43, "text": "Account disabled. (k_EResultAccountDisabled)"},
    {"x": 44, "text": "Service is currently read-only. (k_EResultServiceReadOnly)"},
    {"x": 45, "text": "Account not featured (no funds). (k_EResultAccountNotFeatured)"},
    {"x": 46, "text": "Action allowed only because the request is from an administrator. (k_EResultAdministratorOK)"},
    {"x": 47, "text": "Content version mismatch. (k_EResultContentVersion)"},
    {"x": 48, "text": "Try another CM server. (k_EResultTryAnotherCM)"},
    {"x": 49,
     "text": "Cached logon failed: you are already logged in elsewhere. (k_EResultPasswordRequiredToKickSession)"},
    {"x": 50,
     "text": "User is logged in from another location. (Deprecated; use 6). (k_EResultAlreadyLoggedInElsewhere)"},
    {"x": 51, "text": "Operation suspended/paused (e.g. content download). (k_EResultSuspended)"},
    {"x": 52, "text": "Operation canceled, typically by user. (k_EResultCancelled)"},
    {"x": 53, "text": "Operation canceled due to data corruption. (k_EResultDataCorruption)"},
    {"x": 54, "text": "Operation canceled due to insufficient disk space. (k_EResultDiskFull)"},
    {"x": 55, "text": "Remote or IPC call failed. (k_EResultRemoteCallFailed)"},
    {"x": 56, "text": "Could not verify password, none is set. (k_EResultPasswordUnset)"},
    {"x": 57, "text": "External account not linked to Steam. (k_EResultExternalAccountUnlinked)"},
    {"x": 58, "text": "PlayStation ticket invalid. (k_EResultPSNTicketInvalid)"},
    {"x": 59,
     "text": "External account already linked to another Steam account. (k_EResultExternalAccountAlreadyLinked)"},
    {"x": 60, "text": "Remote file conflict. (k_EResultRemoteFileConflict)"},
    {"x": 61, "text": "Illegal password. (k_EResultIllegalPassword)"},
    {"x": 62, "text": "New value is the same as the old one. (k_EResultSameAsPreviousValue)"},
    {"x": 63, "text": "Account logon denied (2FA error). (k_EResultAccountLogonDenied)"},
    {"x": 64, "text": "Cannot use the old password. (k_EResultCannotUseOldPassword)"},
    {"x": 65, "text": "Logon denied (invalid authentication code). (k_EResultInvalidLoginAuthCode)"},
    {"x": 66, "text": "Logon denied (2FA email issue). (k_EResultAccountLogonDeniedNoMail)"},
    {"x": 67, "text": "Hardware not capable of Intel IPT. (k_EResultHardwareNotCapableOfIPT)"},
    {"x": 68, "text": "Intel IPT initialization failed. (k_EResultIPTInitError)"},
    {"x": 69, "text": "Parental control restrictions in place. (k_EResultParentalControlRestricted)"},
    {"x": 70, "text": "Facebook query returned an error. (k_EResultFacebookQueryError)"},
    {"x": 71, "text": "Logon denied (expired authentication code). (k_EResultExpiredLoginAuthCode)"},
    {"x": 72, "text": "IP login restriction failed. (k_EResultIPLoginRestrictionFailed)"},
    {"x": 73, "text": "Account locked down (suspected hacking). (k_EResultAccountLockedDown)"},
    {"x": 74, "text": "Logon denied: email not verified. (k_EResultAccountLogonDeniedVerifiedEmailRequired)"},
    {"x": 75, "text": "No matching URL. (k_EResultNoMatchingURL)"},
    {"x": 76, "text": "Bad response (missing field, read error, etc.). (k_EResultBadResponse)"},
    {"x": 77, "text": "User must re-enter password. (k_EResultRequirePasswordReEntry)"},
    {"x": 78, "text": "Value out of range. (k_EResultValueOutOfRange)"},
    {"x": 79, "text": "Unexpected error occurred. (k_EResultUnexpectedError)"},
    {"x": 80, "text": "Requested service is disabled. (k_EResultDisabled)"},
    {"x": 81, "text": "Invalid CEG submission. (k_EResultInvalidCEGSubmission)"},
    {"x": 82, "text": "Restricted device. (k_EResultRestrictedDevice)"},
    {"x": 83, "text": "Action cannot be performed due to region lock. (k_EResultRegionLocked)"},
    {"x": 84, "text": "Rate limit exceeded, try again later. (k_EResultRateLimitExceeded)"},
    {"x": 85, "text": "Two-factor code required for logon. (k_EResultAccountLoginDeniedNeedTwoFactor)"},
    {"x": 86, "text": "Requested item was deleted. (k_EResultItemDeleted)"},
    {"x": 87, "text": "Logon denied: throttle in place (possible threat). (k_EResultAccountLoginDeniedThrottle)"},
    {"x": 88, "text": "Two-factor code mismatch (Steam Guard). (k_EResultTwoFactorCodeMismatch)"},
    {"x": 89, "text": "Two-factor activation code mismatch. (k_EResultTwoFactorActivationCodeMismatch)"},
    {"x": 90, "text": "Account associated with multiple partners. (k_EResultAccountAssociatedToMultiplePartners)"},
    {"x": 91, "text": "Data not modified. (k_EResultNotModified)"},
    {"x": 92, "text": "No mobile device linked to this account. (k_EResultNoMobileDevice)"},
    {"x": 93, "text": "Time not synced or out of range. (k_EResultTimeNotSynced)"},
    {"x": 94, "text": "SMS code error. (k_EResultSmsCodeFailed)"},
    {"x": 95, "text": "Account limit exceeded. (k_EResultAccountLimitExceeded)"},
    {"x": 96, "text": "Too many account activity changes. (k_EResultAccountActivityLimitExceeded)"},
    {"x": 97, "text": "Too many changes for this phone number. (k_EResultPhoneActivityLimitExceeded)"},
    {"x": 98, "text": "Cannot refund to original payment method, refund to wallet required. (k_EResultRefundToWallet)"},
    {"x": 99, "text": "Failed to send email. (k_EResultEmailSendFailure)"},
    {"x": 100, "text": "Payment is not settled yet. (k_EResultNotSettled)"},
    {"x": 101, "text": "Captcha is required. (k_EResultNeedCaptcha)"},
    {"x": 102, "text": "GSLT token denied. (k_EResultGSLTDenied)"},
    {"x": 103, "text": "Game server owner denied for another reason. (k_EResultGSOwnerDenied)"},
    {"x": 104, "text": "Invalid item type. (k_EResultInvalidItemType)"},
    {"x": 105, "text": "IP is banned from this action. (k_EResultIPBanned)"},
    {"x": 106, "text": "GSLT has expired due to inactivity. (k_EResultGSLTExpired)"},
    {"x": 107, "text": "Insufficient funds. (k_EResultInsufficientFunds)"},
    {"x": 108, "text": "Too many pending requests. (k_EResultTooManyPending)"}
]


class LoginExecutor:
    def __init__(self, username: str, password: str, shared_secret: str, session: Session) -> None:
        self.username = username
        self.password = password
        self.one_time_code = ''
        self.shared_secret = shared_secret
        self.session = session  # Настройте session.proxies при необходимости
        self.client_id = ''
        self.steamid = ''
        self.request_id = ''
        self.refresh_token = ''
        self.nonce_store = ''
        self.auth_store = ''
        self.nonce_com = ''
        self.auth_com = ''

    def _write_log(self, message: str):
        with open("steam.log", "a", encoding="utf-8") as f:
            f.write(message)

    def _request(self, method: str, url: str, **kwargs) -> Response:
        req_info = f"REQUEST: {method.upper()} {url}\n"
        if "headers" in kwargs:
            req_info += f"Request Headers: {kwargs['headers']}\n"
        if "data" in kwargs:
            req_info += f"Request Data: {kwargs['data']}\n"
        if "params" in kwargs:
            req_info += f"Request Params: {kwargs['params']}\n"
        req_info += "\n"
        self._write_log(req_info)

        if method.upper() == "GET":
            response = self.session.get(url, **kwargs)
        else:
            response = self.session.post(url, **kwargs)

        res_info = f"RESPONSE: {response.status_code} {response.reason}\n"
        res_info += f"Response Headers: {response.headers}\n"
        res_info += f"Response Content: {response.text}\n\n"
        self._write_log(res_info)
        return response

    def _api_call(self, method: str, service: str, endpoint: str, version: str = 'v1', params: dict = None) -> Response:
        url = '/'.join([SteamUrl.API_URL, service, endpoint, version])
        headers = {
            "Referer": SteamUrl.COMMUNITY_URL + '/',
            "Origin": SteamUrl.COMMUNITY_URL
        }
        if method.upper() == 'GET':
            return self._request("GET", url, params=params, headers=headers)
        else:
            return self._request("POST", url, data=params, headers=headers)

    def login(self) -> Session:
        login_response = self._send_login_request()
        # Если требуется, можно раскомментировать обработку капчи или Steam Guard:
        # self._check_for_captcha(login_response)
        # login_response = self._enter_steam_guard_if_necessary(login_response)
        # self._assert_valid_credentials(login_response)
        self._update_stem_guard(login_response)
        self._pool_sessions_steam()
        finalized_response = self._finalize_login()
        self._setstokens(finalized_response)
        self.set_sessionid_cookies()
        return self.session

    def _send_login_request(self) -> Response:
        rsa_params = self._fetch_rsa_params()
        encrypted_password = self._encrypt_password(rsa_params)
        rsa_timestamp = rsa_params['rsa_timestamp']
        request_data = self._prepare_login_request_data(encrypted_password, rsa_timestamp)
        response = self._request("POST", SteamUrl.BeginAuthSessionViaCredentials_URL, data=request_data)
        x_eresult = response.headers.get('x-eresult')
        if not x_eresult:
            raise Exception("Не удалось получить x-eresult из заголовков ответа.")
        eresult_int = int(x_eresult)
        if eresult_int != 1:
            match = next((item for item in errors if item["x"] == eresult_int), None)
            if match:
                raise Exception(f"Авторизация не удалась, eResult={eresult_int}: {match['text']}")
            else:
                raise Exception(f"Авторизация не удалась, неизвестный eResult={eresult_int}.")
        return response

    def set_sessionid_cookies(self):
        # Устанавливаем дополнительные куки для Steam
        self.session.cookies.set('steamRememberLogin', 'true', domain='')
        self.session.cookies.set('timezoneOffset', '14400,0', domain='')

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"'
        }

        # Выполняем GET-запрос к странице, которая устанавливает куку sessionid
        self._request("GET", "https://steamcommunity.com/my/home/", headers=headers)
        cookies = self.session.cookies.get_dict()
        sessionid = cookies.get('sessionid')
        if not sessionid:
            raise Exception("Ошибка: sessionid отсутствует в куках. Логин не удался.")

        community_domain = urlparse(SteamUrl.COMMUNITY_URL).netloc
        store_domain = urlparse(SteamUrl.STORE_URL).netloc

        community_cookie = {
            "name": "sessionid",
            "value": sessionid,
            "domain": community_domain,
            "path": "/"
        }
        store_cookie = {
            "name": "sessionid",
            "value": sessionid,
            "domain": store_domain,
            "path": "/"
        }

        self.session.cookies.set(**community_cookie)
        self.session.cookies.set(**store_cookie)

    @staticmethod
    def _create_session_id_cookie(sessionid: str, domain: str) -> dict:
        return {
            "name": "sessionid",
            "value": sessionid,
            "domain": domain,
            "path": "/"
        }

    def _fetch_rsa_params(self, current_number_of_repetitions: int = 0) -> dict:
        maximal_number_of_repetitions = 5
        # Выполняем запрос для установки начальных куки
        self.session.post(SteamUrl.COMMUNITY_URL)
        self.session.get(SteamUrl.COMMUNITY_URL)

        response = self._request("GET", SteamUrl.GetPasswordRSAPublicKey_URL + self.username)
        try:
            key_response = json.loads(response.text)
        except json.JSONDecodeError as e:
            raise Exception(
                f"Ошибка декодирования JSON при получении RSA параметров: {e}. Текст ответа: {response.text}")
        try:
            rsa_mod = int(key_response["response"]['publickey_mod'], 16)
            rsa_exp = int(key_response["response"]['publickey_exp'], 16)
            rsa_timestamp = key_response["response"]['timestamp']
            return {
                'rsa_key': rsa.PublicKey(rsa_mod, rsa_exp),
                'rsa_timestamp': rsa_timestamp
            }
        except KeyError:
            if current_number_of_repetitions < maximal_number_of_repetitions:
                return self._fetch_rsa_params(current_number_of_repetitions + 1)
            else:
                raise ValueError('Could not obtain rsa-key')

    def _encrypt_password(self, rsa_params: dict) -> str:
        encrypted = rsa.encrypt(self.password.encode('utf-8'), rsa_params['rsa_key'])
        return base64.b64encode(encrypted).decode('utf-8')

    def _prepare_login_request_data(self, encrypted_password: str, rsa_timestamp: str) -> dict:
        return {
            'persistence': "1",
            'encrypted_password': encrypted_password,
            'account_name': self.username,
            'encryption_timestamp': rsa_timestamp,
        }

    @staticmethod
    def _check_for_captcha(login_response: Response) -> None:
        if login_response.json().get('captcha_needed', False):
            raise CaptchaRequired('Captcha required')

    def _enter_steam_guard_if_necessary(self, login_response: Response) -> Response:
        if login_response.json().get('requires_twofactor', False):
            self.one_time_code = guard.generate_one_time_code(self.shared_secret)
            return self._send_login_request()
        return login_response

    @staticmethod
    def _assert_valid_credentials(login_response: Response) -> None:
        if not login_response.json()['response'].get("client_id"):
            raise InvalidCredentials(
                login_response.json()['response'].get('extended_error_message', 'Invalid credentials'))

    def _perform_redirects(self, response_dict: dict) -> None:
        parameters = response_dict.get('transfer_parameters')
        if parameters is None:
            raise Exception('Cannot perform redirects after login, no parameters fetched')
        for url in response_dict.get('transfer_urls', []):
            self._request("POST", url, data=parameters)

    def _fetch_home_page(self) -> Response:
        return self._request("POST", SteamUrl.COMMUNITY_URL + '/my/home/')

    def _update_stem_guard(self, login_response: Response):
        try:
            response_json = login_response.json()
        except json.JSONDecodeError as e:
            raise Exception(f"Ошибка декодирования JSON в _update_stem_guard: {e}. Текст ответа: {login_response.text}")
        self.client_id = response_json["response"]["client_id"]
        self.steamid = response_json["response"]["steamid"]
        self.request_id = response_json["response"]["request_id"]
        code_type = 3
        code = guard.generate_one_time_code(self.shared_secret)
        update_data = {
            'client_id': self.client_id,
            'steamid': self.steamid,
            'code_type': code_type,
            'code': code
        }
        self._request("POST", SteamUrl.UpdateAuthSessionWithSteamGuardCode_URL, data=update_data)

    def _pool_sessions_steam(self):
        pool_data = {
            'client_id': self.client_id,
            'request_id': self.request_id
        }
        response = self._request("POST", SteamUrl.PollAuthSessionStatus_URL, data=pool_data)
        try:
            response_json = response.json()
        except json.JSONDecodeError as e:
            raise Exception(f"Ошибка декодирования JSON в _pool_sessions_steam: {e}. Текст ответа: {response.text}")
        self.refresh_token = response_json.get("response", {}).get("refresh_token", "")

    def _finalize_login(self, proxies: Optional[dict] = None) -> Response:
        redir = "https://steamcommunity.com/login/home/?goto="
        # Извлекаем sessionid из cookies
        sessionid = self.session.cookies.get("sessionid")
        if not sessionid:
            raise Exception("sessionid cookie not found in _finalize_login.")
        files = {
            'nonce': (None, self.refresh_token),
            'sessionid': (None, sessionid),
            'redir': (None, redir)
        }
        headers = {
            'Referer': redir,
            'Origin': 'https://steamcommunity.com'
        }
        return self.session.post("https://login.steampowered.com/jwt/finalizelogin", headers=headers, files=files)

    def _setstokens(self, fin_resp: Response):
        if not fin_resp.text.strip():
            raise Exception("Получен пустой ответ от finalizelogin, не удалось установить токены.")
        try:
            response_json = fin_resp.json()
        except json.JSONDecodeError as e:
            raise Exception(f"Ошибка декодирования JSON в _setstokens: {e}. Текст ответа: {fin_resp.text}")
        try:
            self.nonce_store = response_json["transfer_info"][0]["params"]["nonce"]
            self.auth_store = response_json["transfer_info"][0]["params"]["auth"]
            self.nonce_com = response_json["transfer_info"][1]["params"]["nonce"]
            self.auth_com = response_json["transfer_info"][1]["params"]["auth"]
        except (KeyError, IndexError) as e:
            raise Exception(f"Ошибка при извлечении токенов из ответа: {e}. Текст ответа: {fin_resp.text}")

        store_data = {
            'nonce': self.nonce_store,
            'auth': self.auth_store,
            'steamID': self.steamid
        }
        com_data = {
            'nonce': self.nonce_com,
            'auth': self.auth_com,
            'steamID': self.steamid
        }
        self._request("POST", SteamUrl.Settoken_community_URL, data=com_data)
        self._request("POST", SteamUrl.Settoken_store_URL, data=store_data)
