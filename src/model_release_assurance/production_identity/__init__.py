"""Narrow access-token verification for the preparatory production-identity profile.

This package does not perform OIDC login or confer agency or release authority.
"""
from .tokens import AccessIdentity, AccessTokenVerifier, TokenError

__all__ = ["AccessIdentity", "AccessTokenVerifier", "TokenError"]
