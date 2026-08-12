import requests
from abc import ABC, abstractmethod
from typing import Dict, Any
from django.conf import settings
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

class BaseSSOProvider(ABC):
    name: str = "base"

    @abstractmethod
    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verifies provider-specific token and returns standardized user info:
        {
            'email': str,
            'first_name': str,
            'last_name': str,
            'provider': str,
            'provider_id': str
        }
        """
        pass

class GoogleSSOProvider(BaseSSOProvider):
    name = "google"

    def verify_token(self, token: str) -> Dict[str, Any]:
        client_id = getattr(settings, 'GOOGLE_CLIENT_ID', '')
        try:
            if client_id:
                id_info = id_token.verify_oauth2_token(token, google_requests.Request(), client_id)
            else:
                id_info = id_token.verify_oauth2_token(token, google_requests.Request())
        except Exception as e:
            raise ValueError(f"Invalid Google token: {str(e)}")

        email = id_info.get('email')
        if not email:
            raise ValueError("Email not provided by Google account.")

        return {
            'email': email,
            'first_name': id_info.get('given_name', ''),
            'last_name': id_info.get('family_name', ''),
            'provider': self.name,
            'provider_id': id_info.get('sub', '')
        }

class GitHubSSOProvider(BaseSSOProvider):
    name = "github"

    def verify_token(self, token: str) -> Dict[str, Any]:
        headers = {'Authorization': f'token {token}', 'Accept': 'application/json'}
        resp = requests.get('https://api.github.com/user', headers=headers)
        if resp.status_code != 200:
            raise ValueError("Invalid GitHub access token.")

        data = resp.json()
        email = data.get('email')

        if not email:
            email_resp = requests.get('https://api.github.com/user/emails', headers=headers)
            if email_resp.status_code == 200:
                emails = email_resp.json()
                for e in emails:
                    if e.get('primary') and e.get('verified'):
                        email = e.get('email')
                        break
                if not email and emails:
                    email = emails[0].get('email')

        if not email:
            raise ValueError("Email not accessible from GitHub account.")

        name_parts = (data.get('name') or data.get('login') or '').split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        return {
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'provider': self.name,
            'provider_id': str(data.get('id', ''))
        }

class MicrosoftSSOProvider(BaseSSOProvider):
    name = "microsoft"

    def verify_token(self, token: str) -> Dict[str, Any]:
        headers = {'Authorization': f'Bearer {token}'}
        resp = requests.get('https://graph.microsoft.com/v1.0/me', headers=headers)
        if resp.status_code != 200:
            raise ValueError("Invalid Microsoft access token.")

        data = resp.json()
        email = data.get('mail') or data.get('userPrincipalName')
        if not email:
            raise ValueError("Email not provided by Microsoft account.")

        return {
            'email': email,
            'first_name': data.get('givenName', ''),
            'last_name': data.get('surname', ''),
            'provider': self.name,
            'provider_id': str(data.get('id', ''))
        }

class SSOProviderRegistry:
    _providers: Dict[str, BaseSSOProvider] = {}

    @classmethod
    def register(cls, provider: BaseSSOProvider):
        cls._providers[provider.name.lower()] = provider

    @classmethod
    def get_provider(cls, name: str) -> BaseSSOProvider:
        provider = cls._providers.get(name.lower())
        if not provider:
            raise ValueError(f"SSO provider '{name}' is not supported. Supported providers: {list(cls._providers.keys())}")
        return provider

    @classmethod
    def list_providers(cls) -> list:
        return list(cls._providers.keys())

# Register default providers
SSOProviderRegistry.register(GoogleSSOProvider())
SSOProviderRegistry.register(GitHubSSOProvider())
SSOProviderRegistry.register(MicrosoftSSOProvider())
