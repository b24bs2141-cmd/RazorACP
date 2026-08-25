"""
Razorpay PSP Adapter — ACP-Compliant Payment Token & Charge Service
Port 8001 | FastAPI | Delegated Payment Spec Implementation
"""

import json
import uuid
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="RazorACP PSP Adapter", version="1.0.0")

# In-memory stores
tokens_db = {}
charges_db = {}

# Configuration
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_key")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "secret")
SPT_EXPIRY_MINUTES = int(os.getenv("SPT_EXPIRY_MINUTES", "5"))
MAX_TRANSACTION_AMOUNT = int(os.getenv("MAX_TRANSACTION_AMOUNT", "100000"))

# Data Models
class TokenRequest(BaseModel):
    buyer_agent_id: str
    max_amount: int
    currency: str = "INR"
    merchant_id: str
    description: Optional[str] = None

class TokenResponse(BaseModel):
    shared_payment_token: str
    max_amount: int
    currency: str
    expires_at: str
    buyer_agent_id: str
    status: str

class ChargeRequest(BaseModel):
    spt: str
    amount: int
    currency: str
    checkout_id: str
    merchant_id: str
    buyer_agent_id: str

class ChargeResponse(BaseModel):
    success: bool
    order_id: str
    amount: int
    currency: str
    status: str

# Utility Functions
def generate_spt(buyer_agent_id: str, max_amount: int) -> str:
    """
    Generate Shared Payment Token (SPT)
    Format: spt_<timestamp>_<random>_<hmac>
    """
    timestamp = datetime.utcnow().isoformat()
    random_suffix = str(uuid.uuid4())[:8]
    
    # Create HMAC signature
    message = f"{buyer_agent_id}:{max_amount}:{timestamp}".encode()
    signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        message,
        hashlib.sha256
    ).hexdigest()[:16]
    
    return f"spt_{timestamp.replace(':', '-')}_{random_suffix}_{signature}"

def verify_spt(token: str, buyer_agent_id: str, amount: int) -> dict:
    """Verify and validate SPT token"""
    if token not in tokens_db:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    token_data = tokens_db[token]
    
    # Check expiry
    expires_at = datetime.fromisoformat(token_data["expires_at"])
    if datetime.utcnow() > expires_at:
        token_data["status"] = "expired"
        raise HTTPException(status_code=401, detail="Token expired")
    
    # Check buyer_agent_id
    if token_data["buyer_agent_id"] != buyer_agent_id:
        raise HTTPException(status_code=401, detail="Token buyer_agent_id mismatch")
    
    # Check amount bounds
    if amount > token_data["max_amount"]:
        raise HTTPException(
            status_code=400,
            detail=f"Amount ₹{amount} exceeds SPT limit ₹{token_data['max_amount']}"
        )
    
    # Check single-use (if already used)
    if token_data["status"] == "used":
        raise HTTPException(status_code=400, detail="Token already used (single-use)")
    
    return token_data

def create_razorpay_order(amount: int, currency: str, checkout_id: str, merchant_id: str) -> dict:
    """
    Simulate Razorpay order creation
    In production, this would call: razorpay_client.order.create()
    """
    order_id = f"order_{uuid.uuid4().hex[:12]}"
    
    # Simulate Razorpay response
    order_data = {
        "id": order_id,
        "entity": "order",
        "amount": amount,
        "amount_paid": 0,
        "amount_due": amount,
        "currency": currency,
        "receipt": f"receipt_{checkout_id[:8]}",
        "offer_id": None,
        "status": "created",
        "attempts": 0,
        "notes": {
            "checkout_id": checkout_id,
            "merchant_id": merchant_id,
            "acp_compliant": True
        },
        "created_at": int(datetime.utcnow().timestamp())
    }
    
    return order_data

def mark_spt_used(token: str):
    """Mark SPT as used (single-use enforcement)"""
    if token in tokens_db:
        tokens_db[token]["status"] = "used"
        tokens_db[token]["used_at"] = datetime.utcnow().isoformat()

# API Endpoints

@app.post("/v1/tokens", response_model=TokenResponse)
async def issue_token(request: TokenRequest):
    """
    ACP Delegated Payment Spec — Token Issuance
    Issues Shared Payment Token (SPT) with amount bounds and expiry
    """
    
    # Validate amount bounds
    if request.max_amount > MAX_TRANSACTION_AMOUNT:
        raise HTTPException(
            status_code=400,
            detail=f"Requested amount ₹{request.max_amount} exceeds PSP limit ₹{MAX_TRANSACTION_AMOUNT}"
        )
    
    if request.max_amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    # Generate SPT
    spt = generate_spt(request.buyer_agent_id, request.max_amount)
    
    # Calculate expiry
    expires_at = datetime.utcnow() + timedelta(minutes=SPT_EXPIRY_MINUTES)
    
    # Store token
    token_data = {
        "spt": spt,
        "buyer_agent_id": request.buyer_agent_id,
        "max_amount": request.max_amount,
        "currency": request.currency,
        "merchant_id": request.merchant_id,
        "description": request.description or "ACP Purchase",
        "issued_at": datetime.utcnow().isoformat(),
        "expires_at": expires_at.isoformat(),
        "status": "active",
        "used_at": None
    }
    
    tokens_db[spt] = token_data
    
    return TokenResponse(
        shared_payment_token=spt,
        max_amount=request.max_amount,
        currency=request.currency,
        expires_at=expires_at.isoformat(),
        buyer_agent_id=request.buyer_agent_id,
        status="active"
    )

@app.post("/v1/charges", response_model=ChargeResponse)
async def create_charge(request: ChargeRequest):
    """
    ACP Delegated Payment Spec — Charge Creation
    Validates SPT and creates Razorpay order
    """
    
    # Verify SPT
    token_data = verify_spt(request.spt, request.buyer_agent_id, request.amount)
    
    # Validate amount
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    if request.amount > token_data["max_amount"]:
        raise HTTPException(
            status_code=400,
            detail=f"Charge amount ₹{request.amount} exceeds token limit ₹{token_data['max_amount']}"
        )
    
    # Create Razorpay order
    try:
        razorpay_order = create_razorpay_order(
            request.amount,
            request.currency,
            request.checkout_id,
            request.merchant_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Razorpay error: {str(e)}")
    
    # Create charge record
    charge_id = str(uuid.uuid4())
    charge_data = {
        "charge_id": charge_id,
        "spt": request.spt,
        "razorpay_order_id": razorpay_order["id"],
        "amount": request.amount,
        "currency": request.currency,
        "checkout_id": request.checkout_id,
        "merchant_id": request.merchant_id,
        "buyer_agent_id": request.buyer_agent_id,
        "status": "created",
        "created_at": datetime.utcnow().isoformat(),
        "razorpay_order": razorpay_order
    }
    
    charges_db[charge_id] = charge_data
    
    # Mark SPT as used (single-use enforcement)
    mark_spt_used(request.spt)
    
    return ChargeResponse(
        success=True,
        order_id=razorpay_order["id"],
        amount=request.amount,
        currency=request.currency,
        status="created"
    )

@app.get("/v1/tokens/{token_id}")
async def get_token_status(token_id: str):
    """Get SPT status and validation"""
    if token_id not in tokens_db:
        raise HTTPException(status_code=404, detail="Token not found")
    
    token_data = tokens_db[token_id]
    expires_at = datetime.fromisoformat(token_data["expires_at"])
    is_expired = datetime.utcnow() > expires_at
    
    return {
        "token_id": token_id,
        "status": "expired" if is_expired else token_data["status"],
        "max_amount": token_data["max_amount"],
        "currency": token_data["currency"],
        "buyer_agent_id": token_data["buyer_agent_id"],
        "issued_at": token_data["issued_at"],
        "expires_at": token_data["expires_at"],
        "used_at": token_data.get("used_at")
    }

@app.get("/v1/charges/{charge_id}")
async def get_charge_status(charge_id: str):
    """Get charge status"""
    if charge_id not in charges_db:
        raise HTTPException(status_code=404, detail="Charge not found")
    
    charge_data = charges_db[charge_id]
    
    return {
        "charge_id": charge_id,
        "razorpay_order_id": charge_data["razorpay_order_id"],
        "amount": charge_data["amount"],
        "currency": charge_data["currency"],
        "status": charge_data["status"],
        "created_at": charge_data["created_at"],
        "checkout_id": charge_data["checkout_id"]
    }

@app.post("/v1/verify-payment")
async def verify_payment(order_id: str, payment_id: str, signature: str):
    """
    Verify Razorpay payment signature
    In production, this would validate against Razorpay API
    """
    # Simulate signature verification
    message = f"{order_id}|{payment_id}".encode()
    expected_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        message,
        hashlib.sha256
    ).hexdigest()
    
    if signature != expected_signature:
        raise HTTPException(status_code=401, detail="Invalid payment signature")
    
    return {
        "success": True,
        "order_id": order_id,
        "payment_id": payment_id,
        "verified": True
    }

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "RazorACP PSP Adapter",
        "tokens_issued": len([t for t in tokens_db.values() if t["status"] == "active"]),
        "charges_created": len(charges_db),
        "razorpay_key": RAZORPAY_KEY_ID[:10] + "***"
    }

@app.get("/stats")
async def get_stats():
    """Get PSP statistics"""
    active_tokens = sum(1 for t in tokens_db.values() if t["status"] == "active")
    used_tokens = sum(1 for t in tokens_db.values() if t["status"] == "used")
    expired_tokens = sum(1 for t in tokens_db.values() if t["status"] == "expired")
    
    total_charges = sum(c["amount"] for c in charges_db.values())
    
    return {
        "tokens_issued": len(tokens_db),
        "tokens_active": active_tokens,
        "tokens_used": used_tokens,
        "tokens_expired": expired_tokens,
        "charges_created": len(charges_db),
        "total_charge_volume": total_charges
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
