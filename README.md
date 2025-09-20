# FBSMSLib

A Python library for Fritz!Box authentication and SMS management. This library allows you to send and receive SMS messages through your Fritz!Box router programmatically.

## Features

- ✅ Send SMS messages with configurable rate limiting
- ✅ Send SMS to multiple recipients
- ✅ Retrieve incoming SMS messages
- ✅ Two-factor authentication (TOTP) support
- ✅ Automatic session management
- ✅ Integrated rate limiting to prevent abuse

## Requirements

- Python 3.11+
- Fritz!Box with firmware version 8.03 or later (PBKDF2 support required)
- SMS functionality enabled on your Fritz!Box
- Valid Fritz!Box user credentials + activated TOTP with SMS permissions

## Quick Start

```python
from fbsmslib import FBSMSLib

# Initialize the library
fbsms = FBSMSLib(
    url="http://192.168.178.1",  # Your Fritz!Box IP
    username="your_username",
    password="your_password",
    totpsecret="YOUR_TOTP_SECRET"
)

# Send a single SMS
fbsms.send_sms("+4915228895456", "Hello from Fritz!Box!")

# Get incoming SMS messages
incoming_messages = fbsms.get_sms_incoming()
for msg in incoming_messages:
    print(f"From: {msg['sender']}")
    print(f"Message: {msg['text']}")
    print(f"Date: {msg['date']}")
    print("-" * 40)
```

The TOTP secret is required since sending SMS requires two-factor authentication to be enabled on the Fritz!Box user.

NOTE: The library is blocking and synchronous right now. The fritzbox web interface is not designed for high-frequency access. Use with caution in multi-threaded or asynchronous environments!

## Configuration

### Fritz!Box Setup

1. Enable SMS functionality in your Fritz!Box settings
2. Create a user account with SMS permissions
3. Go to Fritz!Box settings → System → Fritz!Box Users
4. Edit your user and enable "Authentication app"
5. Scan the QR code and note the secret key

## API Reference

### FBSMSLib Class

#### Constructor

```python
FBSMSLib(url: str, username: str, password: str, totpsecret: str, rate: Rate = None)
```

- `url`: Fritz!Box web interface URL (e.g., "http://192.168.178.1")
- `username`: Fritz!Box username
- `password`: Fritz!Box password
- `totpsecret`: TOTP secret for 2FA (if enabled)
- `rate`: Optional `Rate` object from `pyrate_limiter` to customize rate limiting (default is 10 SMS/hour)

#### Methods

##### send_sms(receiver: str, message: str)

Send an SMS message to a single recipient.

```python
fbsms.send_sms("+4915228895456", "Your message here")
```

##### send_sms_multiple(receiver: list[str], message: str)

Send an SMS message to multiple recipients with automatic delay between sends.

```python
recipients = ["+4915228895456", "+491729925904"]
fbsms.send_sms_multiple(recipients, "Broadcast message")
```

##### get_sms() -> list

Get all SMS messages (sent and received).

```python
all_messages = fbsms.get_sms()
```

##### get_sms_incoming() -> list

Get only incoming SMS messages.

```python
incoming = fbsms.get_sms_incoming()
```

## Examples

### Basic SMS Sending

```python
from fbsmslib import FBSMSLib

fbsms = FBSMSLib(
    url="http://192.168.178.1",
    username="admin",
    password="your_password",
    totpsecret="ABCD1234EFGH5678"
)

# Send a simple message
fbsms.send_sms("+491729925904", "Hello World!")
```

### Monitoring Incoming Messages

```python
import time
from fbsmslib import FBSMSLib

fbsms = FBSMSLib(
    url="http://192.168.178.1",
    username="admin",
    password="your_password",
    totpsecret="ABCD1234EFGH5678"
)

# Check for new messages every 30 seconds
while True:
    incoming = fbsms.get_sms_incoming()
    
    for msg in incoming:
        print(f"📱 New SMS from {msg['sender']}")
        print(f"💬 {msg['text']}")
        print(f"🕐 {msg['date']}")
        print("-" * 40)
    
    time.sleep(30)
```

### Bulk SMS Sending

```python
from fbsmslib import FBSMSLib

fbsms = FBSMSLib(
    url="http://192.168.178.1",
    username="admin",
    password="your_password",
    totpsecret="ABCD1234EFGH5678"
)

# Send to multiple recipients
contacts = [
    "+4915228895456",
    "+491729968532",
    "+491749464308"
]

message = "Important announcement: Server maintenance tonight at 2 AM"
fbsms.send_sms_multiple(contacts, message)
```

### Advanced: Custom Rate Limiting

The library includes built-in rate limiting (10 SMS per hour) on a leaky bucket algorithm. The rate limit is enforced automatically, but may be customized by providing a `Rate` object from the `pyrate_limiter` library.

```python
from fbsmslib import FBSMSLib
from pyrate_limiter import Rate, Duration

fbsms = FBSMSLib(
    url="http://192.168.178.1",
    username="admin",
    password="your_password",
    totpsecret="ABCD1234EFGH5678",
    rate=Rate(2, Duration.MINUTE)  # Custom rate limit: 2 SMS per minute
)

# The library will automatically enforce these rate limits
try:
    for i in range(3):  # Try to send 15 messages
        fbsms.send_sms("+491749464308", f"Message {i}")
except RuntimeError as e:
    print(f"Rate limit hit: {e}")
```

## Error Handling

Common exceptions you might encounter:

- `RuntimeError`: Rate limit exceeded or network issues
- `Exception`: Authentication failures or Fritz!Box communication errors
- `NotImplementedError`: Unsupported 2FA methods

## Troubleshooting

### Common Issues

1. **"FRITZ!Box does not support PBKDF2"**
   - Update your Fritz!Box firmware to version 7.24 or later

2. **"wrong username or password"**
   - Verify your credentials
   - Ensure the user has SMS permissions

3. **Rate limit exceeded**
   - Wait for the rate limit window to reset
   - Consider batching messages with delays

4. **Connection errors**
   - Verify Fritz!Box IP address and network connectivity
   - Check if Fritz!Box web interface is accessible

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License.

## Disclaimer

This library is not affiliated with FRITZ! GmbH. Fritz!Box is a trademark of FRITZ! GmbH.
Use this library responsibly and in accordance with your local telecommunications regulations.