Here is a complete, production-grade test suite for the FastAPI application using **PyTest**. 

This suite covers all endpoints, background worker tasks, external service integrations (S3, Stripe), security mechanisms (Rate Limiting, JWT Auth), and database interactions using a mocked MongoDB instance.

### 1. Test Dependencies & Config

**`requirements-test.txt`**
```text
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-mock==3.12.0
httpx==0.25.1
mongomock-motor==0.0.28
```

**`pytest.ini`**
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
addopts = -v --disable-warnings
```

---

### 2. Global Fixtures & Setup

**`tests/conftest.py`**
```python
import os
import pytest
import pytest_asyncio
from unittest.mock import patch

# Set environment variables BEFORE importing app modules to satisfy Pydantic Settings
os.environ["MONGODB_URL"] = "mongodb://localhost:27017"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["RABBITMQ_URL"] = "amqp://localhost:5672"
os.environ["JWT_SECRET"] = "super-secret-test-key"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_123"
os.environ["AWS_ACCESS_KEY_ID"] = "test-key"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test-secret"
os.environ["AWS_S3_BUCKET"] = "test-bucket"

from httpx import AsyncClient
from mongomock_motor import AsyncMongoMockClient
from app.main import app
from app.core.database import db_instance
from app.core.security import create_access_token
from bson import ObjectId

@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(autouse=True)
async def mock_env():
    """Mocks MongoDB and prevents real connections during FastAPI lifespan."""
    mock_client = AsyncMongoMockClient()
    
    with patch("app.core.database.Database.connect"), \
         patch("app.core.database.Database.disconnect"), \
         patch("app.core.broker.MessageBroker.connect"), \
         patch("app.core.broker.MessageBroker.disconnect"):
        
        db_instance.client = mock_client
        db_instance.db = mock_client.bidstream
        await db_instance.db.users.create_index("email", unique=True)
        yield db_instance.db

@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Resets SlowAPI rate limiter storage between tests to prevent cross-test failures."""
    from app.core.rate_limiter import limiter
    limiter._storage.reset()

@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client

@pytest.fixture
def test_user_id():
    return ObjectId()

@pytest_asyncio.fixture
async def test_user(mock_env, test_user_id):
    from app.core.security import get_password_hash
    from datetime import datetime, timezone
    user = {
        "_id": test_user_id,
        "email": "test@example.com",
        "password_hash": get_password_hash("password123"),
        "is_email_verified": True,
        "created_at": datetime.now(timezone.utc).replace(tzinfo=None)
    }
    await mock_env.users.insert_one(user)
    return user

@pytest.fixture
def auth_headers(test_user_id):
    token = create_access_token(subject=str(test_user_id))
    return {"Authorization": f"Bearer {token}"}
```

---

### 3. Authentication Tests

**`tests/test_auth.py`**
```python
import pytest
from bson import ObjectId

@pytest.mark.asyncio
async def test_register_success(async_client):
    response = await async_client.post("/api/auth/register", json={
        "email": "newuser@example.com",
        "password": "securepassword123"
    })
    assert response.status_code == 201
    assert "token" in response.json()
    assert "user_id" in response.json()

@pytest.mark.asyncio
async def test_register_duplicate_email(async_client, test_user):
    response = await async_client.post("/api/auth/register", json={
        "email": "test@example.com", # Already exists via fixture
        "password": "securepassword123"
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"

@pytest.mark.asyncio
async def test_login_success(async_client, test_user):
    response = await async_client.post("/api/auth/login", data={
        "username": "test@example.com",
        "password": "password123"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()

@pytest.mark.asyncio
async def test_login_invalid_credentials(async_client, test_user):
    response = await async_client.post("/api/auth/login", data={
        "username": "test@example.com",
        "password": "wrongpassword"
    })
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_verify_email_success(async_client, test_user, mock_env):
    # Reset verification for test
    await mock_env.users.update_one({"_id": test_user["_id"]}, {"$set": {"is_email_verified": False}})
    
    response = await async_client.post(f"/api/auth/verify-email?token={test_user['_id']}")
    assert response.status_code == 200
    
    updated_user = await mock_env.users.find_one({"_id": test_user["_id"]})
    assert updated_user["is_email_verified"] is True

@pytest.mark.asyncio
async def test_verify_email_invalid_token(async_client):
    response = await async_client.post("/api/auth/verify-email?token=invalid_token")
    assert response.status_code == 400
```

---

### 4. Auction Endpoints Tests

**`tests/test_auctions.py`**
```python
import pytest
from unittest.mock import patch
from bson.decimal128 import Decimal128

@pytest.mark.asyncio
@patch("app.api.endpoints.auctions.generate_presigned_url")
async def test_get_presigned_url(mock_generate, async_client, auth_headers):
    mock_generate.return_value = "https://s3.amazonaws.com/presigned"
    
    response = await async_client.post(
        "/api/auctions/presigned-url",
        json={"filename": "test.jpg", "content_type": "image/jpeg"},
        headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["upload_url"] == "https://s3.amazonaws.com/presigned"

@pytest.mark.asyncio
@patch("app.api.endpoints.auctions.schedule_auction_end")
async def test_create_auction(mock_schedule, async_client, auth_headers):
    auction_data = {
        "title": "Vintage Watch",
        "description": "A rare vintage watch.",
        "starting_price": "150.50",
        "min_increment": "5.00",
        "duration_hours": 24,
        "image_urls": ["https://example.com/image.jpg"]
    }
    response = await async_client.post("/api/auctions", json=auction_data, headers=auth_headers)
    
    assert response.status_code == 201
    assert "auction_id" in response.json()
    mock_schedule.assert_called_once()

@pytest.mark.asyncio
async def test_list_active_auctions(async_client, mock_env, test_user_id):
    await mock_env.auctions.insert_one({
        "seller_id": test_user_id,
        "title": "Test Auction",
        "description": "Test",
        "image_urls": [],
        "starting_price": Decimal128("10.00"),
        "current_price": Decimal128("10.00"),
        "min_increment": Decimal128("1.00"),
        "status": "ACTIVE",
        "end_time": "2099-01-01T00:00:00"
    })
    
    response = await async_client.get("/api/auctions?status=ACTIVE")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Test Auction"
    assert data[0]["starting_price"] == "10.00" # Validates Decimal string casting

@pytest.mark.asyncio
async def test_get_auction_not_found(async_client):
    response = await async_client.get("/api/auctions/507f1f77bcf86cd799439011")
    assert response.status_code == 404
```

---

### 5. Bidding & Rate Limiting Tests

**`tests/test_bids.py`**
```python
import pytest
from unittest.mock import patch
from bson import ObjectId

@pytest.mark.asyncio
@patch("app.main.place_bid")
async def test_place_bid_success(mock_place_bid, async_client, auth_headers):
    mock_place_bid.return_value = {"status": "success", "current_price": "150.00"}
    auction_id = str(ObjectId())
    
    response = await async_client.post(
        f"/api/auctions/{auction_id}/bid",
        json={"amount": "150.00"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    mock_place_bid.assert_called_once()

@pytest.mark.asyncio
async def test_place_bid_rate_limit(async_client, auth_headers):
    auction_id = str(ObjectId())
    
    with patch("app.main.place_bid", return_value={"status": "success"}):
        # SlowAPI limit is 5/second. Hit it 5 times successfully.
        for _ in range(5):
            res = await async_client.post(
                f"/api/auctions/{auction_id}/bid",
                json={"amount": "150.00"},
                headers=auth_headers
            )
            assert res.status_code == 200
            
        # 6th request should trigger HTTP 429 Too Many Requests
        res = await async_client.post(
            f"/api/auctions/{auction_id}/bid",
            json={"amount": "150.00"},
            headers=auth_headers
        )
        assert res.status_code == 429
```

---

### 6. Background Worker Tests

**`tests/test_worker.py`**
```python
import pytest
from unittest.mock import patch
from bson import ObjectId
from bson.decimal128 import Decimal128
from datetime import datetime, timedelta, timezone
from app.worker import end_auction_task

@pytest.mark.asyncio
@patch("app.worker.create_checkout_session")
@patch("app.core.broker.MessageBroker.publish_to_topic")
async def test_end_auction_with_winner(mock_publish, mock_checkout, mock_env, test_user):
    mock_checkout.return_value = "https://stripe.com/checkout/123"
    
    auction_id = ObjectId()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    await mock_env.auctions.insert_one({
        "_id": auction_id,
        "title": "Test Auction",
        "starting_price": Decimal128("10.00"),
        "end_time": now - timedelta(minutes=1),
        "status": "ACTIVE"
    })
    
    await mock_env.bids.insert_one({
        "auction_id": auction_id,
        "buyer_id": test_user["_id"],
        "amount": Decimal128("20.00")
    })
    
    await end_auction_task(None, str(auction_id))
    
    # Verify DB updates
    updated_auction = await mock_env.auctions.find_one({"_id": auction_id})
    assert updated_auction["status"] == "ENDED"
    assert updated_auction["checkout_url"] == "https://stripe.com/checkout/123"
    assert updated_auction["winner_id"] == test_user["_id"]
    
    # Verify Stripe & Broker called
    mock_checkout.assert_called_once_with("Test Auction", Decimal128("20.00").to_decimal(), test_user["email"])
    mock_publish.assert_called_once()
    
    args, _ = mock_publish.call_args
    assert args[0] == f"auctions.{auction_id}"
    assert args[1]["type"] == "AUCTION_ENDED"
    assert args[1]["winner_id"] == str(test_user["_id"])

@pytest.mark.asyncio
@patch("app.core.broker.MessageBroker.publish_to_topic")
async def test_end_auction_no_winner(mock_publish, mock_env):
    auction_id = ObjectId()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    
    await mock_env.auctions.insert_one({
        "_id": auction_id,
        "title": "Unsold Auction",
        "starting_price": Decimal128("10.00"),
        "end_time": now - timedelta(minutes=1),
        "status": "ACTIVE"
    })
    
    await end_auction_task(None, str(auction_id))
    
    updated_auction = await mock_env.auctions.find_one({"_id": auction_id})
    assert updated_auction["status"] == "ENDED"
    assert "winner_id" not in updated_auction
    
    mock_publish.assert_called_once()
    args, _ = mock_publish.call_args
    assert args[1]["winner_id"] is None
```

---

### 7. External Services Tests

**`tests/test_services.py`**
```python
import pytest
from unittest.mock import patch
from decimal import Decimal
from app.services.s3_service import generate_presigned_url
from app.services.stripe_service import create_checkout_session

@patch("boto3.client")
def test_generate_presigned_url(mock_boto_client):
    mock_s3 = mock_boto_client.return_value
    mock_s3.generate_presigned_url.return_value = "https://s3.url/presigned"
    
    url = generate_presigned_url("test.jpg", "image/jpeg")
    
    assert url == "https://s3.url/presigned"
    mock_s3.generate_presigned_url.assert_called_once()

@pytest.mark.asyncio
@patch("stripe.checkout.Session.create")
async def test_create_checkout_session(mock_stripe_create):
    mock_stripe_create.return_value.url = "https://stripe.url/checkout"
    
    url = await create_checkout_session("Test Item", Decimal("150.50"), "winner@example.com")
    
    assert url == "https://stripe.url/checkout"
    mock_stripe_create.assert_called_once()
    
    # Verify safe integer math for Stripe cents calculation
    call_args = mock_stripe_create.call_args[1]
    assert call_args["line_items"][0]["price_data"]["unit_amount"] == 15050
```