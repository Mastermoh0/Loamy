"""Fail-closed production configuration; no production mode through the preview launcher."""
from dataclasses import dataclass
import os
from urllib.parse import urlsplit, parse_qs


def https_origin(value, name):
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
        raise RuntimeError(f'{name} must be an HTTPS origin without a path or credentials')
    if parsed.hostname in {'localhost', '127.0.0.1', 'testserver'}:
        raise RuntimeError(f'{name} must be a public deployment origin')
    return value.rstrip('/')


@dataclass(frozen=True)
class ProductionSettings:
    database_url: str
    web_origin: str
    api_origin: str

    @classmethod
    def from_env(cls):
        if os.getenv('LOAMY_LOCAL_PREVIEW') == '1':
            raise RuntimeError('Production must not run with the local-preview flag')
        web = https_origin(os.environ.get('LOAMY_WORKSPACE_WEB_ORIGIN', ''), 'LOAMY_WORKSPACE_WEB_ORIGIN')
        api = https_origin(os.environ.get('LOAMY_WORKSPACE_API_ORIGIN', ''), 'LOAMY_WORKSPACE_API_ORIGIN')
        dsn = os.environ.get('LOAMY_WORKSPACE_DATABASE_URL', '')
        parsed = urlsplit(dsn)
        if parsed.scheme not in {'postgres', 'postgresql'} or not parsed.hostname or not parsed.username or not parsed.password:
            raise RuntimeError('A dedicated PostgreSQL application-role connection is required')
        if parsed.username.split('.')[0] != 'loamy_enterprise_app':
            raise RuntimeError('Use the least-privilege loamy_enterprise_app role, not the database owner')
        if parse_qs(parsed.query).get('sslmode') != ['verify-full']:
            raise RuntimeError('Database TLS must verify the server certificate: sslmode=verify-full')
        if os.getenv('LOAMY_MAIL_TRANSPORT') != 'smtp':
            raise RuntimeError('Production requires real SMTP; captured verification is not accepted')
        for name in ['LOAMY_SMTP_HOST', 'LOAMY_SMTP_FROM', 'LOAMY_SMTP_USERNAME', 'LOAMY_SMTP_PASSWORD']:
            if not os.getenv(name):
                raise RuntimeError(f'{name} is required')
        if os.getenv('LOAMY_SMTP_SECURITY', 'starttls') not in {'starttls', 'ssl'}:
            raise RuntimeError('SMTP requires TLS')
        return cls(dsn, web, api)
