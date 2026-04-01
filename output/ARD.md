Here is the Architecture Record Document (ARD) capturing the major architectural decisions outlined in the updated Technical Design Document. 

This document follows the standard Architecture Decision Record (ADR) format to provide context, outline the decisions made, and analyze the consequences (trade-offs) of each choice.

---

# Architecture Record Document (ARD)
**Product:** BidStream (Live Auction Platform)
**Date:** Current Date
**Author:** Lead Architect

---

## ARD-001: Migration to NoSQL (MongoDB) for Core Data Storage

**Status:** Accepted
**Context:** 
The live auction platform requires high write throughput during bidding wars and flexible data models for varying auction items. Initially, a relational SQL database was considered. However, the rigid schema and locking mechanisms of traditional SQL databases can become bottlenecks under massive concurrent write loads (e.g., thousands of bids per second on a single popular item).

**Decision:** 
We will use **MongoDB (NoSQL)** deployed as a Replica Set as the primary data store. 
*   Monetary values will strictly use the `Decimal128` BSON type to prevent floating-point inaccuracies.
*   The `bids` will be stored in a separate collection rather than embedded within the `auctions` document to prevent hitting MongoDB's 16MB document size limit during highly active auctions.

**Consequences:**
*   **Positive:** High write availability, flexible schema evolution, and horizontal scalability via sharding (if needed in the future).
*   **Negative:** Requires explicit application-level handling of relational integrity. Multi-document ACID transactions are required to keep `auctions` and `bids` collections in sync, which mandates a Replica Set deployment and adds slight latency compared to single-document updates.

---

## ARD-002: Adoption of STOMP over WebSockets for Real-Time Messaging

**Status:** Accepted
**Context:** 
Real-time bid broadcasting is the most critical feature of the platform. The previous design utilized Socket.io. While Socket.io is easy to implement, it uses a proprietary framing protocol and requires API servers to manage WebSocket connections directly. Scaling Socket.io requires a Redis Pub/Sub adapter, which tightly couples connection management to the Node.js application servers and limits horizontal scaling efficiency.

**Decision:** 
Replace Socket.io with **STOMP (Simple Text Oriented Messaging Protocol) over WebSockets**, backed by a dedicated Message Broker (e.g., RabbitMQ with the Web-Stomp plugin).
*   Clients will connect directly to the broker via the Load Balancer.
*   Routing will use standard STOMP semantics (`/topic/auctions.{id}` for public broadcasts, `/user/queue/errors` for private messages, `/app/auctions.{id}.bid` for incoming bids).

**Consequences:**
*   **Positive:** Offloads WebSocket connection management and pub/sub routing entirely from the Node.js API servers. The STOMP broker natively handles clustering, message routing, and massive concurrent connections, resulting in a highly scalable and decoupled architecture.
*   **Positive:** Standardized protocol allows for easier integration with various client and server technologies.
*   **Negative:** Increases infrastructure complexity (requires deploying and managing a RabbitMQ/ActiveMQ cluster). Frontend engineers must learn STOMP semantics instead of the familiar Socket.io API.

---

## ARD-003: Optimistic Concurrency Control (OCC) for Bid Processing

**Status:** Accepted
**Context:** 
In a NoSQL environment, handling the "Double Bid" race condition (where two users submit the exact same bid amount at the exact same millisecond) is critical. Pessimistic locking (locking the database row/document until a transaction completes) would severely degrade performance during high-velocity bidding.

**Decision:** 
Implement **Optimistic Concurrency Control (OCC)** using a `version` integer field on the `auctions` document, combined with MongoDB `ClientSession` transactions. 
*   When a bid is processed, the query will require the document's version to match the version read at the start of the transaction. 
*   If successful, the version is incremented (`$inc: { version: 1 }`). 
*   If the version has changed (meaning another bid was processed first), the database update will yield a `modifiedCount` of 0, and the transaction will be aborted.

**Consequences:**
*   **Positive:** Maximizes throughput and performance by avoiding database locks. Ensures strict data consistency and prevents "lost updates."
*   **Negative:** Requires the application to handle OCC failures gracefully. The system must explicitly catch the aborted transaction and send a `BID_REJECTED` STOMP message to the user who lost the race condition, prompting them to bid again.

---

## ARD-004: Redis BullMQ for Distributed Timer & Anti-Sniper Management

**Status:** Accepted
**Context:** 
Auctions have strict end times. Furthermore, the platform features an "Anti-Sniper" rule: if a bid is placed within the last 60 seconds, the auction timer is extended. Relying on in-memory Node.js timers (`setTimeout`) is unacceptable because if a server crashes or restarts, the timers are lost.

**Decision:** 
Use **Redis BullMQ** for scheduling and managing auction lifecycle events.
*   Upon auction creation, a delayed job is added to the queue to end the auction.
*   If the anti-sniper rule is triggered, the existing BullMQ job is removed and a new delayed job is scheduled with the updated end time.

**Consequences:**
*   **Positive:** Guarantees that auction end events are executed reliably, even if API servers crash. Provides a clean, distributed mechanism to cancel and reschedule timers dynamically.
*   **Negative:** Introduces Redis as a mandatory infrastructure dependency for core business logic (though Redis is already planned for caching, this increases its criticality).