"""myTNB API client configuration."""

from __future__ import annotations

import logging

# Base URLs
LEGACY_BASE_URL = "https://mytnbapp.tnb.com.my/v7/mytnbws.asmx"
REST_BASE_URL = "https://api.mytnb.com.my"
SITECORE_LOGIN_URL = "https://www.mytnb.com.my/api/sitecore/Account/Login"
SSO_HANDLER_URL = "https://myaccount.mytnb.com.my/SSO/SSOHandler"

# Default user agents
USER_AGENT = "RestSharp/110.2.0.0"
USER_AGENT_IOS = "myTNB/1425 CFNetwork/3860.500.112 Darwin/25.4.0"

# Default API key for token generation (embedded in the mobile app)
DEFAULT_API_KEY = "gpUS5pe4aO2yMbId7bFa13dGfYYnBWbjn3vqn0d7"

# Default security key for legacy ASMX requests (embedded in the mobile app)
DEFAULT_SECURE_KEY_K1 = "E6148656-205B-494C-BC95-CC241423E72F"

logger = logging.getLogger(__name__)
