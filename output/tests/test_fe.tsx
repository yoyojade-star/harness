Here is a comprehensive, production-ready test suite using **Vitest** and **React Testing Library**. 

This suite specifically targets the critical fixes you implemented: **clock drift compensation**, **decoupled UI locking**, and **STOMP payload security**.

### Prerequisites
Ensure you have the required testing libraries installed:
```bash
npm install -D vitest @testing-library/react @testing-library/user-event @testing-library/jest-dom jsdom
```

### Test Suite (`AuctionRoom.test.tsx`)

```tsx
import React from 'react';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import AuctionRoom, { Auction, AuctionRoomProps } from './AuctionRoom';
import { Client } from '@stomp/stompjs';

// --- 1. Mocking @stomp/stompjs ---
let mockStompClientInstance: any;

vi.mock('@stomp/stompjs', () => {
  return {
    Client: vi.fn().mockImplementation(function (this: any) {
      mockStompClientInstance = this;
      this.connected = false;
      this.publish = vi.fn();
      this.subscribe = vi.fn();
      this.deactivate = vi.fn();
      this.activate = vi.fn(() => {
        this.connected = true;
        // Simulate successful connection callback
        if (this.onConnect) this.onConnect();
      });
    }),
  };
});

// --- 2. Test Data Setup ---
const mockAuction: Auction = {
  _id: 'auction-123',
  title: 'Vintage Rolex Submariner',
  description: 'Rare 1980s timepiece.',
  image_urls: ['/rolex.jpg'],
  starting_price: 5000,
  current_price: 5500,
  min_increment: 100,
  end_time: '2023-10-10T12:00:00.000Z',
  status: 'ACTIVE',
};

const defaultProps: AuctionRoomProps = {
  initialAuction: mockAuction,
  serverTime: '2023-10-10T11:00:00.000Z',
  currentUserToken: 'fake-jwt-token',
  currentUserId: 'user-1',
};

// Helper to simulate incoming STOMP messages
const simulateStompMessage = (destination: string, payload: any) => {
  const subscribeCall = mockStompClientInstance.subscribe.mock.calls.find(
    (call: any) => call[0] === destination
  );
  if (subscribeCall) {
    const callback = subscribeCall[1];
    act(() => {
      callback({ body: typeof payload === 'string' ? payload : JSON.stringify(payload) });
    });
  }
};

describe('AuctionRoom Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Set system time to 10:00 AM (1 hour behind the server time)
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2023-10-10T10:00:00.000Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // --- TEST 1: Clock Drift Compensation ---
  it('calculates time remaining accurately by compensating for client-server clock drift', () => {
    render(<AuctionRoom {...defaultProps} />);
    
    // Local time: 10:00 AM
    // Server time: 11:00 AM (Offset: +1 hour)
    // End time: 12:00 PM
    // Actual time left should be 1 hour (12:00 PM - 11:00 AM), NOT 2 hours.
    expect(screen.getByText('01:00:00')).toBeInTheDocument();
  });

  // --- TEST 2: Decoupled UI Locking ---
  it('allows bidding even if local timer hits zero, provided server status is ACTIVE', () => {
    // Set local time so that the calculated time left is 0
    vi.setSystemTime(new Date('2023-10-10T11:00:00.000Z')); // +1hr offset = 12:00 PM (End Time)
    
    render(<AuctionRoom {...defaultProps} />);
    
    // Timer should show zero
    expect(screen.getByText('00:00:00')).toBeInTheDocument();
    
    // BUT the button should STILL be enabled because status is 'ACTIVE'
    const bidButton = screen.getByRole('button', { name: /place bid/i });
    expect(bidButton).not.toBeDisabled();
  });

  // --- TEST 3: Bid Validation ---
  it('prevents submission and shows error if bid is below minimum increment', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<AuctionRoom {...defaultProps} />);

    const input = screen.getByPlaceholderText(/enter 5600.00 or more/i);
    const submitBtn = screen.getByRole('button', { name: /place bid/i });

    await user.type(input, '5550'); // Min is 5600
    await user.click(submitBtn);

    expect(screen.getByText('Bid must be at least $5600.00')).toBeInTheDocument();
    expect(mockStompClientInstance.publish).not.toHaveBeenCalled();
  });

  // --- TEST 4: Successful Bid Submission ---
  it('publishes bid to STOMP broker when validation passes', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    render(<AuctionRoom {...defaultProps} />);

    const input = screen.getByPlaceholderText(/enter 5600.00 or more/i);
    const submitBtn = screen.getByRole('button', { name: /place bid/i });

    await user.type(input, '6000');
    await user.click(submitBtn);

    expect(mockStompClientInstance.publish).toHaveBeenCalledWith({
      destination: `/app/auctions.${mockAuction._id}.bid`,
      body: JSON.stringify({ amount: 6000 }),
    });
    
    // Input should clear after submission
    expect(input).toHaveValue(null);
  });

  // --- TEST 5: Handling Incoming STOMP Messages (BID_ACCEPTED) ---
  it('updates current price and winning status on BID_ACCEPTED broadcast', () => {
    render(<AuctionRoom {...defaultProps} />);

    simulateStompMessage(`/topic/auctions.${mockAuction._id}`, {
      type: 'BID_ACCEPTED',
      new_price: 6500,
      bidder_id: 'user-1', // Matches currentUserId
    });

    expect(screen.getByText('$6500.00')).toBeInTheDocument();
    expect(screen.getByText('You are winning')).toBeInTheDocument();
  });

  // --- TEST 6: Handling Incoming STOMP Messages (AUCTION_ENDED) ---
  it('locks UI and shows winner state on AUCTION_ENDED broadcast', () => {
    render(<AuctionRoom {...defaultProps} />);

    simulateStompMessage(`/topic/auctions.${mockAuction._id}`, {
      type: 'AUCTION_ENDED',
      final_price: 7000,
      winner_id: 'user-1',
    });

    // UI should lock
    const bidButton = screen.getByRole('button', { name: /auction closed/i });
    expect(bidButton).toBeDisabled();
    
    const input = screen.getByRole('spinbutton', { name: /bid amount/i });
    expect(input).toBeDisabled();

    // Winner state should show
    expect(screen.getByText('Congratulations!')).toBeInTheDocument();
    expect(screen.getByText('You won this auction for $7000.00.')).toBeInTheDocument();
  });

  // --- TEST 7: Handling Private STOMP Errors (OCC Failures) ---
  it('displays private error messages from the server', () => {
    render(<AuctionRoom {...defaultProps} />);

    simulateStompMessage(`/user/queue/errors`, {
      type: 'BID_REJECTED',
      reason: 'Optimistic locking failure: Price has already updated.',
    });

    expect(screen.getByText('Optimistic locking failure: Price has already updated.')).toBeInTheDocument();
  });

  // --- TEST 8: Security - Malformed JSON Resilience ---
  it('does not crash when receiving malformed JSON payloads (DoS prevention)', () => {
    render(<AuctionRoom {...defaultProps} />);

    // Spy on console.error to keep test output clean, but verify it was called
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    // Send invalid JSON string
    expect(() => {
      simulateStompMessage(`/topic/auctions.${mockAuction._id}`, "INVALID_JSON_STRING {");
    }).not.toThrow();

    expect(consoleSpy).toHaveBeenCalledWith(
      'Failed to parse public STOMP message',
      expect.any(SyntaxError)
    );

    consoleSpy.mockRestore();
  });

  // --- TEST 9: Connection State Handling ---
  it('disables bidding and shows warning when STOMP is disconnected', () => {
    // Override mock to simulate disconnected state
    mockStompClientInstance.connected = false;
    mockStompClientInstance.activate = vi.fn(); // Prevent onConnect from firing

    render(<AuctionRoom {...defaultProps} />);

    expect(screen.getByText('Connecting to live auction server...')).toBeInTheDocument();
    
    const bidButton = screen.getByRole('button', { name: /place bid/i });
    expect(bidButton).toBeDisabled();
  });
});
```

### Vitest Configuration (`vitest.config.ts`)
If you don't already have it, here is the standard configuration required to run this test suite:

```typescript
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './setupTests.ts',
  },
});
```

### Setup File (`setupTests.ts`)
```typescript
import '@testing-library/jest-dom';
```

### Why this Test Suite is robust:
1. **Time Travel & Drift Simulation:** Uses `vi.useFakeTimers()` and `vi.setSystemTime()` to strictly control the local clock, proving that the `serverTime` offset math works perfectly.
2. **Decoupled State Verification:** Explicitly tests that the UI does *not* lock when the local timer hits zero, but *does* lock when the `AUCTION_ENDED` STOMP message arrives.
3. **Security Validation:** The malformed JSON test ensures that the `try/catch` block successfully catches `SyntaxError` exceptions, preventing a malicious actor from crashing the client by broadcasting garbage data over the WebSocket.
4. **Mocked WebSocket Lifecycle:** Accurately simulates the asynchronous nature of `@stomp/stompjs` connections, subscriptions, and message callbacks without requiring an actual broker.