"""Two-Factor Authentication utilities using TOTP (Time-based One-Time Password).

Provides:
- TOTP secret generation and QR code generation for authenticator apps
- TOTP code verification with 30-second window
- Backup codes generation and verification (10 single-use codes)
"""

import io
import secrets
import hashlib
import json
from typing import Tuple, Optional

import pyotp
import qrcode
from aiogram.types import BufferedInputFile


def generate_totp_secret() -> str:
    """Generate a new TOTP secret (base32 encoded)."""
    return pyotp.random_base32()


def generate_qr_code(secret: str, username: str, issuer: str = "MGKEIT Pair Alert") -> BufferedInputFile:
    """
    Generate QR code image for TOTP secret.
    
    Args:
        secret: TOTP secret (base32)
        username: User identifier (e.g., user_id or telegram username)
        issuer: Service name shown in authenticator app
    
    Returns:
        BufferedInputFile containing QR code PNG image
    """
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(name=str(username), issuer_name=issuer)
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to bytes - save as PNG
    buf = io.BytesIO()
    # Use PIL Image.save() directly with PNG format
    img.save(buf, "PNG")
    buf.seek(0)
    
    return BufferedInputFile(buf.read(), filename="qr_code.png")


def verify_totp_code(secret: str, code: str) -> bool:
    """
    Verify TOTP code against secret.
    
    Args:
        secret: TOTP secret (base32)
        code: 6-digit code from authenticator app
    
    Returns:
        True if code is valid (within time window), False otherwise
    """
    if not code or not code.isdigit() or len(code) != 6:
        return False
    
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)  # Allow 1 step (30s) before/after current


def generate_backup_codes(count: int = 10) -> list[str]:
    """
    Generate backup codes for emergency access.
    
    Each code is 8 characters: 4 alphanumeric pairs separated by dash (e.g., AB12-CD34-EF56-GH78)
    
    Returns:
        List of backup codes (plain text)
    """
    codes = []
    for _ in range(count):
        # Generate 8 random alphanumeric characters
        code = ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8))
        # Format as XXXX-XXXX
        formatted = f"{code[:4]}-{code[4:]}"
        codes.append(formatted)
    return codes


def hash_backup_code(code: str) -> str:
    """Hash backup code for storage (SHA256)."""
    return hashlib.sha256(code.encode('utf-8')).hexdigest()


def verify_backup_code(code: str, hashed_codes_json: str) -> Tuple[bool, Optional[str]]:
    """
    Verify backup code and return updated hashed codes list (with used code removed).
    
    Args:
        code: Backup code entered by user
        hashed_codes_json: JSON array of hashed backup codes
    
    Returns:
        Tuple of (is_valid, updated_hashed_codes_json)
        - is_valid: True if code matched and was valid
        - updated_hashed_codes_json: JSON with matched code removed, or None if invalid
    """
    try:
        hashed_codes = json.loads(hashed_codes_json)
    except:
        return False, None
    
    # Normalize input code (remove spaces, uppercase)
    normalized_code = code.replace(' ', '').replace('-', '').upper()
    # Re-add dash for consistent format
    if len(normalized_code) == 8:
        normalized_code = f"{normalized_code[:4]}-{normalized_code[4:]}"
    
    code_hash = hash_backup_code(normalized_code)
    
    if code_hash in hashed_codes:
        # Remove used code
        hashed_codes.remove(code_hash)
        return True, json.dumps(hashed_codes)
    
    return False, None


def store_backup_codes(codes: list[str]) -> str:
    """
    Hash backup codes and return JSON for storage.
    
    Args:
        codes: List of plain-text backup codes
    
    Returns:
        JSON string of hashed codes
    """
    hashed = [hash_backup_code(code) for code in codes]
    return json.dumps(hashed)
