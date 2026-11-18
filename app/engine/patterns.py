import re

# Base timestamp regex: YYYY-MM-DD or YYYY/MM/DD HH:MM:SS or with .sss
RE_TIMESTAMP = re.compile(r"^(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?)\s+(.*)$")

# Virtual hub prefix in server_log: [HUB "DEFAULT"] ...
RE_HUB_PREFIX = re.compile(r"^\[HUB\s+\"([^\"]+)\"\]\s+(.*)$", re.IGNORECASE)

# Server lifecycle
RE_SERVER_START = re.compile(r"The SoftEther VPN Server service has started", re.IGNORECASE)
RE_SERVER_STOP = re.compile(r"The SoftEther VPN Server service has stopped", re.IGNORECASE)

# Connection creation
RE_CONN_CREATED_1 = re.compile(
    r"For the client\s+([0-9a-fA-F\.:]+):(\d+),\s+connection\s+\"CID-(\d+)\"\s+has been created",
    re.IGNORECASE
)
RE_CONN_CREATED_2 = re.compile(
    r"The connection\s+\"CID-(\d+)\"\s+has been established\.\s*Client IP:\s*([0-9a-fA-F\.:]+),\s*Port:\s*(\d+)",
    re.IGNORECASE
)
RE_CLIENT_CONNECTED = re.compile(
    r"On the TCP Listener.*?Client\s*\(IP address\s*([0-9a-fA-F\.:]+).*?Port\s*(\d+)\)\s+has connected",
    re.IGNORECASE
)

# Authentication attempt (often contains client IP, port, and username before session is made)
RE_AUTH_ATTEMPT = re.compile(
    r"(?:The\s+)?connection\s+\"CID-(\d+)\"\s*\((?:Client IP address|Client IP):\s*([0-9a-fA-F\.:]+)(?:,\s*Port:\s*(\d+))?.*?user name is\s+\"([^\"]+)\"",
    re.IGNORECASE
)

# Authentication success
RE_AUTH_SUCCESS_1 = re.compile(
    r"Connection\s+\"CID-(\d+)\":\s*Successfully authenticated as user\s+\"([^\"]+)\"",
    re.IGNORECASE
)
RE_AUTH_SUCCESS_2 = re.compile(
    r"Connection\s+\"CID-(\d+)\":\s*User\s+\"([^\"]+)\"\s+has logged on",
    re.IGNORECASE
)
RE_AUTH_SUCCESS_3 = re.compile(
    r"User\s+\"([^\"]+)\"\s+has logged on\.\s*(?:\((?:Client IP address|Client IP):\s*([0-9a-fA-F\.:]+)(?:,\s*Port:\s*(\d+))?\))?",
    re.IGNORECASE
)

# Authentication failure
RE_AUTH_FAIL_1 = re.compile(
    r"Connection\s+\"CID-(\d+)\":\s*User authentication failed(?: for the user\s+\"([^\"]+)\")?",
    re.IGNORECASE
)
RE_AUTH_FAIL_2 = re.compile(
    r"Connection\s+\"CID-(\d+)\"\s+terminated by the cause\s+\"User authentication failed",
    re.IGNORECASE
)

# Session created
RE_SESSION_CREATED_1 = re.compile(
    r"(?:Connection\s+\"CID-(\d+)\":\s*)?The new session\s+\"([^\"]+)\"\s+has been created(?:\.\s*\((?:IP address|Client IP):\s*([0-9a-fA-F\.:]+)(?:,\s*Port:\s*(\d+))?.*?\))?",
    re.IGNORECASE
)
RE_SESSION_CREATED_2 = re.compile(
    r"(?:The\s+)?session\s+\"([^\"]+)\"\s+has been created",
    re.IGNORECASE
)

# Session terminated
RE_SESSION_TERMINATED = re.compile(
    r"(?:Session|The session)\s+\"([^\"]+)\"(?:\:)?\s*(?:The session\s+)?(?:has been|was)\s+terminated(?:\.\s*The statistical information is as follows:\s*Total outgoing data size:\s*(\d+)\s*bytes,\s*Total incoming data size:\s*(\d+)\s*bytes)?",
    re.IGNORECASE
)

# Connection terminated
RE_CONN_TERMINATED_1 = re.compile(
    r"(?:The\s+)?connection\s+\"CID-(\d+)\"\s+has been terminated",
    re.IGNORECASE
)
RE_CONN_TERMINATED_2 = re.compile(
    r"(?:The\s+)?connection\s+\"CID-(\d+)\"\s+terminated by the cause\s+\"([^\"]*)\"(?:\s*\(code\s*(\d+)\))?",
    re.IGNORECASE
)

# Extract username from SID if username is in SID format (SoftEther default: SID-USERNAME-ID or SID-USERNAME-[...]-ID)
RE_SID_USERNAME = re.compile(r"^SID-([A-Za-z0-9_\-\.]+?)(?:-\[[^\]]+\])?-(\d+)$", re.IGNORECASE)
