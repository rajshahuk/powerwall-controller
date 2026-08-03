"""Tesla FleetAPI OAuth onboarding service.

Drives the one-time Tesla Fleet API setup (partner registration and user
OAuth) from the web UI instead of the pypowerwall CLI wizard, writing
straight into pypowerwall's own `.pypowerwall.fleetapi` cache file (read
and written directly here, since constructing pypowerwall's FleetAPI class
triggers a live (and often unauthenticated) getsites() call as a side
effect of loading its config). Once tokens are obtained, ongoing polling
and token refresh are handled by pypowerwall itself (see
powerwall_service.py's fleetapi mode).
"""

import json
import os
import secrets
import urllib.parse
from dataclasses import dataclass
from typing import Optional

from pypowerwall.fleetapi.fleetapi import (
    FleetAPI,
    CONFIGFILE,
    SCOPE,
    SETUP_TIMEOUT,
    fleet_api_urls,
    _http2_request,
)

from app.config import config

AUTH_BASE_URL = "https://auth.tesla.com/oauth2/v3/authorize"
TOKEN_URL = "https://auth.tesla.com/oauth2/v3/token"

REGIONS = fleet_api_urls  # {"North America, Asia-Pacific": "https://...", ...}


@dataclass
class FleetApiStatus:
    credentials_saved: bool
    pem_url: str
    partner_registered: bool
    connected: bool
    site_id: Optional[str] = None
    client_id: str = ""
    domain: str = ""
    redirect_uri: str = ""
    audience: str = ""
    has_client_secret: bool = False


class FleetApiSetupService:
    """Onboards Tesla FleetAPI: credentials -> partner registration -> user OAuth."""

    def __init__(self):
        self._pending_state: Optional[str] = None

    def _configfile(self) -> str:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        return os.path.join(str(config.data_dir), CONFIGFILE)

    def _load_raw(self) -> dict:
        configfile = self._configfile()
        if os.path.isfile(configfile):
            with open(configfile, 'r') as f:
                return json.load(f)
        return {}

    def _save_raw(self, data: dict) -> None:
        # Contains client secret and tokens - write with owner-only permissions
        with open(os.open(self._configfile(), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as f:
            f.write(json.dumps(data, indent=4))

    def get_status(self) -> FleetApiStatus:
        data = self._load_raw()
        domain = data.get('DOMAIN') or ''
        pem_url = (
            f"https://{domain}/.well-known/appspecific/com.tesla.3p.public-key.pem"
            if domain else ""
        )
        return FleetApiStatus(
            credentials_saved=bool(data.get('CLIENT_ID') and data.get('CLIENT_SECRET') and domain),
            pem_url=pem_url,
            partner_registered=bool(data.get('partner_account')),
            connected=bool(data.get('access_token') and data.get('refresh_token')),
            site_id=str(data['site_id']) if data.get('site_id') else None,
            client_id=data.get('CLIENT_ID') or "",
            domain=domain,
            redirect_uri=data.get('REDIRECT_URI') or "",
            audience=data.get('AUDIENCE') or "",
            has_client_secret=bool(data.get('CLIENT_SECRET')),
        )

    def _tesla_error(self, resp) -> str:
        """Extract a human-readable error from a Tesla API response, if any."""
        if resp is None:
            return "no response from Tesla (request failed or timed out)"
        detail = ""
        try:
            body = resp.json()
            detail = body.get('error') or body.get('error_description') or ""
        except Exception:
            detail = (resp.text or "")[:300]
        return f"HTTP {resp.status_code}" + (f" - {detail}" if detail else "")

    def save_credentials(self, client_id: str, client_secret: Optional[str], domain: str,
                          redirect_uri: Optional[str], audience: Optional[str]) -> None:
        data = self._load_raw()
        new_audience = audience or list(REGIONS.values())[0]
        if data.get('AUDIENCE') and data['AUDIENCE'] != new_audience:
            # Partner registration is per-region - redo it against the new audience
            data.pop('partner_token', None)
            data.pop('partner_account', None)
        data['CLIENT_ID'] = client_id
        if client_secret:
            data['CLIENT_SECRET'] = client_secret
        data['DOMAIN'] = domain
        data['REDIRECT_URI'] = redirect_uri or f"https://{domain}/api/fleetapi/callback"
        data['AUDIENCE'] = new_audience
        self._save_raw(data)

    def register_partner(self) -> None:
        """Verify the hosted PEM key, then obtain a partner token and register the domain."""
        data = self._load_raw()
        client_id = data.get('CLIENT_ID')
        client_secret = data.get('CLIENT_SECRET')
        domain = data.get('DOMAIN')
        if not (client_id and client_secret and domain):
            raise Exception("Save your Client ID, Client Secret, and Domain first")
        audience = data.get('AUDIENCE') or list(REGIONS.values())[0]
        data['AUDIENCE'] = audience

        pem_url = f"https://{domain}/.well-known/appspecific/com.tesla.3p.public-key.pem"
        resp = _http2_request('GET', pem_url, timeout=SETUP_TIMEOUT)
        if resp is None or resp.status_code != 200:
            status = resp.status_code if resp is not None else "no response"
            raise Exception(f"Could not verify public key at {pem_url} ({status}) - host your PEM public key there first")

        partner_token = data.get('partner_token')
        if not partner_token:
            req = {
                'grant_type': 'client_credentials',
                'client_id': client_id,
                'client_secret': client_secret,
                'scope': SCOPE,
                'audience': audience,
            }
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            resp = _http2_request('POST', TOKEN_URL, data=req, headers=headers, timeout=SETUP_TIMEOUT)
            if resp is None or resp.status_code != 200:
                raise Exception(f"Failed to obtain partner token from Tesla: {self._tesla_error(resp)}")
            partner_token = resp.json().get('access_token')
            data['partner_token'] = partner_token
            self._save_raw(data)

        if not data.get('partner_account'):
            url = f"{audience}/api/1/partner_accounts"
            headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + partner_token}
            resp = _http2_request('POST', url, headers=headers,
                                   data=json.dumps({'domain': domain}), timeout=SETUP_TIMEOUT)
            if resp is None or resp.status_code != 200:
                raise Exception(f"Failed to register partner account with Tesla: {self._tesla_error(resp)}")
            account = resp.json()
            # Tesla can return HTTP 200 with an embedded failure, e.g.
            # {"response": null, "error": "Validation failed: ..."} - a non-200
            # status alone isn't a reliable success signal for this endpoint.
            if not isinstance(account, dict) or account.get('response') is None:
                detail = account.get('error') if isinstance(account, dict) else None
                raise Exception(f"Partner registration rejected by Tesla: {detail or 'no account data returned'}")
            data['partner_account'] = account
            self._save_raw(data)

    def build_authorize_url(self) -> str:
        data = self._load_raw()
        client_id = data.get('CLIENT_ID')
        redirect_uri = data.get('REDIRECT_URI')
        if not (client_id and redirect_uri):
            raise Exception("Save your Client ID and Domain first")
        state = secrets.token_urlsafe(48)
        self._pending_state = state
        scope = urllib.parse.quote(SCOPE)
        redirect_uri_q = urllib.parse.quote(redirect_uri, safe='')
        return (f"{AUTH_BASE_URL}?client_id={client_id}&locale=en-US&prompt=login"
                f"&redirect_uri={redirect_uri_q}&response_type=code&scope={scope}&state={state}")

    def exchange_code(self, code: str, state: str) -> None:
        if not self._pending_state or state != self._pending_state:
            raise Exception("Invalid or expired OAuth state - restart the Connect with Tesla flow")
        self._pending_state = None
        self._exchange_code_for_tokens(code)

    def exchange_code_manual(self, code: str) -> None:
        """Redeem a code pasted by hand (e.g. from https://pypowerwall.com/code),
        for setups where the redirect URI isn't routed back into this app.
        No state check - pypowerwall's own CLI setup doesn't verify it either."""
        self._pending_state = None
        self._exchange_code_for_tokens(code)

    def _exchange_code_for_tokens(self, code: str) -> None:
        data = self._load_raw()
        req = {
            'grant_type': 'authorization_code',
            'client_id': data.get('CLIENT_ID'),
            'client_secret': data.get('CLIENT_SECRET'),
            'code': code,
            'audience': data.get('AUDIENCE'),
            'redirect_uri': data.get('REDIRECT_URI'),
            'scope': SCOPE,
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        resp = _http2_request('POST', TOKEN_URL, data=req, headers=headers, timeout=SETUP_TIMEOUT)
        if resp is None or resp.status_code != 200:
            raise Exception(f"Failed to exchange authorization code for tokens: {self._tesla_error(resp)}")
        body = resp.json()
        access_token = body.get('access_token')
        refresh_token = body.get('refresh_token')
        if not access_token or not refresh_token:
            raise Exception("Tesla did not return valid tokens")
        data['access_token'] = access_token
        data['refresh_token'] = refresh_token
        self._save_raw(data)

        # Constructing FleetAPI now auto-selects the first energy site when
        # none is set yet (see FleetAPI.load_config) - persist that selection.
        fleet = FleetAPI(configfile=self._configfile())
        if fleet.site_id and not data.get('site_id'):
            fleet.save_config()


# Global service instance
fleetapi_setup_service = FleetApiSetupService()
