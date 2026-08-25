"""
Merchant API — ACP-Compliant Product Feed & Checkout Service
Port 8000 | FastAPI | Desi Bazaar Demo Store
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="RazorACP Merchant API", version="1.0.0")

# In-memory stores
products_db = {}
checkouts_db = {}
audit_trail = []

# Load products from JSON
def load_products():
    global products_db
    try:
        with open("data/products.json", "r") as f:
            data = json.load(f)
            products_db = {p["id"]: p for p in data["products"]}
    except FileNotFoundError:
        print("Warning: products.json not found")

load_products()

# Data Models
class Product(BaseModel):
    id: str
    name: str
    description: str
    category: str
    price: int
    currency: str
    sku: str
    inventory: int
    image: str
    rating: float
    reviews_count: int

class CheckoutItem(BaseModel):
    product_id: str
    quantity: int

class CheckoutRequest(BaseModel):
    buyer_agent_id: str
    items: List[CheckoutItem]
    buyer_context: Optional[dict] = None

class CheckoutSession(BaseModel):
    checkout_id: str
    merchant_id: str
    buyer_agent_id: str
    items: List[dict]
    subtotal: int
    tax: int
    total: int
    currency: str
    status: str
    created_at: str
    expires_at: str
    audit_trail: List[dict]

class CompleteCheckoutRequest(BaseModel):
    shared_payment_token: str

# Utility Functions
def log_audit(checkout_id: str, action: str, details: dict):
    """Log action to audit trail"""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "checkout_id": checkout_id,
        "details": details
    }
    audit_trail.append(entry)
    return entry

def calculate_tax(subtotal: int) -> int:
    """Calculate 18% GST"""
    return int(subtotal * 0.18)

# API Endpoints

@app.get("/products", response_model=List[Product])
async def get_products():
    """
    ACP Product Feed Spec
    Returns structured catalog with SKU, price, inventory, category
    """
    return list(products_db.values())

@app.get("/products/{product_id}", response_model=Product)
async def get_product(product_id: str):
    """Get single product details"""
    if product_id not in products_db:
        raise HTTPException(status_code=404, detail="Product not found")
    return products_db[product_id]

@app.post("/checkouts", response_model=CheckoutSession)
async def create_checkout(request: CheckoutRequest):
    """
    ACP Agentic Checkout Spec
    Creates stateful checkout session with bounds checking
    """
    checkout_id = str(uuid.uuid4())
    
    # Validate items
    items = []
    subtotal = 0
    
    for item in request.items:
        if item.product_id not in products_db:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
        
        product = products_db[item.product_id]
        
        if item.quantity > product["inventory"]:
            raise HTTPException(status_code=400, detail=f"Insufficient inventory for {product['name']}")
        
        line_total = product["price"] * item.quantity
        subtotal += line_total
        
        items.append({
            "product_id": item.product_id,
            "name": product["name"],
            "price": product["price"],
            "quantity": item.quantity,
            "line_total": line_total
        })
    
    # Calculate taxes
    tax = calculate_tax(subtotal)
    total = subtotal + tax
    
    # Check bounds (max ₹1,00,000)
    max_amount = int(os.getenv("MAX_TRANSACTION_AMOUNT", "100000"))
    if total > max_amount:
        raise HTTPException(status_code=400, detail=f"Total ₹{total} exceeds limit ₹{max_amount}")
    
    # Create checkout session
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=10)
    
    checkout = {
        "checkout_id": checkout_id,
        "merchant_id": os.getenv("MERCHANT_ID", "merchant_123456"),
        "buyer_agent_id": request.buyer_agent_id,
        "items": items,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "currency": "INR",
        "status": "pending",
        "created_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "buyer_context": request.buyer_context or {},
        "audit_trail_entries": []
    }
    
    checkouts_db[checkout_id] = checkout
    
    # Log creation
    log_entry = log_audit(checkout_id, "checkout_created", {
        "buyer_agent_id": request.buyer_agent_id,
        "total": total,
        "item_count": len(items)
    })
    checkout["audit_trail_entries"].append(log_entry)
    
    return CheckoutSession(
        **checkout,
        audit_trail=checkout["audit_trail_entries"]
    )

@app.get("/checkouts/{checkout_id}", response_model=CheckoutSession)
async def get_checkout(checkout_id: str):
    """
    Get checkout session with full audit trail
    """
    if checkout_id not in checkouts_db:
        raise HTTPException(status_code=404, detail="Checkout not found")
    
    checkout = checkouts_db[checkout_id]
    
    return CheckoutSession(
        **checkout,
        audit_trail=checkout["audit_trail_entries"]
    )

@app.post("/checkouts/{checkout_id}/complete")
async def complete_checkout(checkout_id: str, request: CompleteCheckoutRequest):
    """
    Complete checkout with SPT validation
    Calls PSP adapter to process payment via Razorpay
    """
    if checkout_id not in checkouts_db:
        raise HTTPException(status_code=404, detail="Checkout not found")
    
    checkout = checkouts_db[checkout_id]
    
    # Check expiry
    expires_at = datetime.fromisoformat(checkout["expires_at"])
    if datetime.utcnow() > expires_at:
        checkout["status"] = "expired"
        log_audit(checkout_id, "checkout_expired", {})
        raise HTTPException(status_code=400, detail="Checkout session expired")
    
    # Log SPT received
    log_entry = log_audit(checkout_id, "spt_received", {
        "spt_token": request.shared_payment_token[:20] + "***"  # masked
    })
    checkout["audit_trail_entries"].append(log_entry)
    
    # Call PSP adapter to create charge
    import requests
    psp_url = os.getenv("PSP_URL", "http://localhost:8001")
    
    try:
        charge_response = requests.post(
            f"{psp_url}/v1/charges",
            json={
                "spt": request.shared_payment_token,
                "amount": checkout["total"],
                "currency": "INR",
                "checkout_id": checkout_id,
                "merchant_id": checkout["merchant_id"],
                "buyer_agent_id": checkout["buyer_agent_id"]
            },
            timeout=5
        )
        
        if charge_response.status_code != 200:
            error_data = charge_response.json()
            log_audit(checkout_id, "payment_failed", error_data)
            raise HTTPException(status_code=400, detail=error_data.get("detail", "Payment failed"))
        
        charge_data = charge_response.json()
        
        # Update checkout status
        checkout["status"] = "completed"
        checkout["razorpay_order_id"] = charge_data.get("order_id")
        
        log_entry = log_audit(checkout_id, "payment_completed", {
            "razorpay_order_id": charge_data.get("order_id"),
            "amount": checkout["total"]
        })
        checkout["audit_trail_entries"].append(log_entry)
        
        # Decrement inventory
        for item in checkout["items"]:
            products_db[item["product_id"]]["inventory"] -= item["quantity"]
        
        return {
            "success": True,
            "checkout_id": checkout_id,
            "razorpay_order_id": charge_data.get("order_id"),
            "total": checkout["total"],
            "status": "completed"
        }
        
    except requests.RequestException as e:
        log_audit(checkout_id, "psp_error", {"error": str(e)})
        raise HTTPException(status_code=500, detail=f"PSP error: {str(e)}")

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "RazorACP Merchant API",
        "products_count": len(products_db),
        "checkouts_count": len(checkouts_db)
    }

@app.get("/stats")
async def get_stats():
    """Get session statistics"""
    completed = sum(1 for c in checkouts_db.values() if c["status"] == "completed")
    total_revenue = sum(c["total"] for c in checkouts_db.values() if c["status"] == "completed")
    
    return {
        "total_checkouts": len(checkouts_db),
        "completed_orders": completed,
        "total_revenue": total_revenue,
        "audit_entries": len(audit_trail)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
