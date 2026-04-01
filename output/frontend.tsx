Here is the corrected, production-ready React/TypeScript implementation. 

I have addressed the critical architectural flaw regarding **client-side clock drift** and patched the **security vulnerabilities** (JWT leakage and unhandled JSON parsing) identified in the review.

### Key Fixes Implemented:
1. **Clock Drift Compensation:** Added a `serverTime` prop to calculate the exact offset between the user's local machine and the server. The `useCountdown` hook now applies this offset to ensure the timer is perfectly synced.
2. **Decoupled UI Locking:** The bidding form is no longer disabled when the local timer hits zero. It strictly relies on the `auction.status === 'ACTIVE'` state, which is only updated when the definitive `AUCTION_ENDED` STOMP message is received from the server.
3. **Secured STOMP Client:** Wrapped all `JSON.parse()` calls in `try/catch` blocks to prevent client-side DoS from malformed payloads, and restricted STOMP debug logging to development environments to prevent JWT leakage.

### Implementation

```tsx
import React, { useState, useEffect, useCallback } from 'react';
import { Client, IMessage } from '@stomp/stompjs';
import { Clock, AlertCircle, CheckCircle2, Gavel, ChevronRight } from 'lucide-react';

// --- 1. TypeScript Interfaces (Matching TDD Schemas) ---

export type AuctionStatus = 'DRAFT' | 'ACTIVE' | 'ENDED' | 'CANCELLED';

export interface Auction {
  _id: string;
  title: string;
  description: string;
  image_urls: string[];
  starting_price: number;
  current_price: number;
  min_increment: number;
  end_time: string;
  status: AuctionStatus;
}

// STOMP Message Payloads
interface BidAcceptedPayload {
  type: 'BID_ACCEPTED';
  new_price: number;
  bidder_id: string;
}

interface AuctionExtendedPayload {
  type: 'AUCTION_EXTENDED';
  new_end_time: string;
}

interface AuctionEndedPayload {
  type: 'AUCTION_ENDED';
  winner_id: string;
  final_price: number;
}

interface BidRejectedPayload {
  type: 'BID_REJECTED';
  reason: string;
}

type AuctionBroadcast = BidAcceptedPayload | AuctionExtendedPayload | AuctionEndedPayload;

// --- 2. Custom Hooks ---

/**
 * Hook to manage the countdown timer accurately, accounting for client-side clock drift.
 */
const useCountdown = (endTime: string, serverTime: string) => {
  const [timeLeft, setTimeLeft] = useState<number>(0);

  useEffect(() => {
    // Calculate the drift between the client's local clock and the server's clock
    const localTimeAtFetch = new Date().getTime();
    const serverTimeAtFetch = new Date(serverTime).getTime();
    const timeOffset = serverTimeAtFetch - localTimeAtFetch;

    const calculateTimeLeft = () => {
      const now = new Date().getTime() + timeOffset;
      const difference = new Date(endTime).getTime() - now;
      return difference > 0 ? difference : 0;
    };

    setTimeLeft(calculateTimeLeft());
    const timer = setInterval(() => {
      setTimeLeft(calculateTimeLeft());
    }, 1000);

    return () => clearInterval(timer);
  }, [endTime, serverTime]);

  const formatTime = (ms: number) => {
    if (ms <= 0) return '00:00:00';
    const h = Math.floor((ms / (1000 * 60 * 60)) % 24);
    const m = Math.floor((ms / 1000 / 60) % 60);
    const s = Math.floor((ms / 1000) % 60);
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return { timeLeft, formattedTime: formatTime(timeLeft), isLocalTimerZero: timeLeft <= 0 };
};

/**
 * Hook to manage STOMP WebSocket connection and subscriptions securely.
 */
const useAuctionStomp = (auctionId: string, jwtToken: string) => {
  const [client, setClient] = useState<Client | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastBroadcast, setLastBroadcast] = useState<AuctionBroadcast | null>(null);
  const [lastError, setLastError] = useState<string | null>(null);

  useEffect(() => {
    if (!auctionId || !jwtToken) return;

    const stompClient = new Client({
      brokerURL: process.env.NEXT_PUBLIC_WS_URL || 'wss://api.bidstream.com/ws',
      connectHeaders: {
        Authorization: `Bearer ${jwtToken}`,
      },
      // SECURITY FIX: Prevent JWT leakage in production console logs
      debug: process.env.NODE_ENV === 'development' ? (str) => console.log('[STOMP]', str) : undefined,
      reconnectDelay: 5000,
      heartbeatIncoming: 4000,
      heartbeatOutgoing: 4000,
    });

    stompClient.onConnect = () => {
      setIsConnected(true);

      // Subscribe to Public Auction Broadcasts
      stompClient.subscribe(`/topic/auctions.${auctionId}`, (message: IMessage) => {
        try {
          // SECURITY FIX: Handle potential malformed JSON to prevent client-side DoS
          const payload = JSON.parse(message.body) as AuctionBroadcast;
          setLastBroadcast(payload);
          // Clear errors on successful public updates
          if (payload.type === 'BID_ACCEPTED') setLastError(null);
        } catch (error) {
          console.error('Failed to parse public STOMP message', error);
        }
      });

      // Subscribe to Private User Errors (e.g., OCC failures, invalid bids)
      stompClient.subscribe(`/user/queue/errors`, (message: IMessage) => {
        try {
          const payload = JSON.parse(message.body) as BidRejectedPayload;
          if (payload.type === 'BID_REJECTED') {
            setLastError(payload.reason);
          }
        } catch (error) {
          console.error('Failed to parse private STOMP message', error);
        }
      });
    };

    stompClient.onStompError = (frame) => {
      console.error('Broker reported error: ' + frame.headers['message']);
    };

    stompClient.activate();
    setClient(stompClient);

    return () => {
      stompClient.deactivate();
    };
  }, [auctionId, jwtToken]);

  const placeBid = useCallback((amount: number) => {
    if (client && client.connected) {
      client.publish({
        destination: `/app/auctions.${auctionId}.bid`,
        body: JSON.stringify({ amount }),
      });
    } else {
      setLastError("Connection lost. Reconnecting...");
    }
  }, [client, auctionId]);

  return { isConnected, lastBroadcast, lastError, placeBid, setLastError };
};

// --- 3. Main UI Component ---

export interface AuctionRoomProps {
  initialAuction: Auction;
  serverTime: string; // ISO-8601 string from the initial REST API fetch
  currentUserToken: string;
  currentUserId: string;
}

export default function AuctionRoom({ 
  initialAuction, 
  serverTime,
  currentUserToken, 
  currentUserId 
}: AuctionRoomProps) {
  // State initialized from REST API props
  const [auction, setAuction] = useState<Auction>(initialAuction);
  const [bidAmount, setBidAmount] = useState<string>('');
  const [isWinning, setIsWinning] = useState<boolean>(false);

  // Hooks
  const { formattedTime, isLocalTimerZero } = useCountdown(auction.end_time, serverTime);
  const { isConnected, lastBroadcast, lastError, placeBid, setLastError } = useAuctionStomp(auction._id, currentUserToken);

  // Handle incoming STOMP messages
  useEffect(() => {
    if (!lastBroadcast) return;

    switch (lastBroadcast.type) {
      case 'BID_ACCEPTED':
        setAuction((prev) => ({ ...prev, current_price: lastBroadcast.new_price }));
        setIsWinning(lastBroadcast.bidder_id === currentUserId);
        break;
      case 'AUCTION_EXTENDED':
        setAuction((prev) => ({ ...prev, end_time: lastBroadcast.new_end_time }));
        break;
      case 'AUCTION_ENDED':
        setAuction((prev) => ({ 
          ...prev, 
          status: 'ENDED', 
          current_price: lastBroadcast.final_price 
        }));
        setIsWinning(lastBroadcast.winner_id === currentUserId);
        break;
    }
  }, [lastBroadcast, currentUserId]);

  // Derived values
  const minNextBid = auction.current_price + auction.min_increment;
  
  // ARCHITECTURE FIX: The server is the single source of truth. 
  // We do NOT disable bidding based on `isLocalTimerZero`. We only disable it if the server says it's ENDED.
  const isAuctionActive = auction.status === 'ACTIVE';

  const handleBidSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLastError(null);
    
    const amount = parseFloat(bidAmount);
    if (isNaN(amount) || amount < minNextBid) {
      setLastError(`Bid must be at least $${minNextBid.toFixed(2)}`);
      return;
    }

    placeBid(amount);
    setBidAmount(''); // Reset input after sending
  };

  return (
    <div className="max-w-5xl mx-auto p-6 grid grid-cols-1 md:grid-cols-2 gap-8">
      {/* Left Column: Images & Details */}
      <div className="space-y-6">
        <div className="aspect-square bg-gray-100 rounded-xl overflow-hidden relative">
          <img 
            src={auction.image_urls[0] || '/placeholder.jpg'} 
            alt={auction.title}
            className="object-cover w-full h-full"
          />
          {!isAuctionActive && (
            <div className="absolute inset-0 bg-black/60 flex items-center justify-center">
              <span className="text-white text-3xl font-bold tracking-widest uppercase">
                Auction Ended
              </span>
            </div>
          )}
        </div>
        <div>
          <h1 className="text-3xl font-bold text-gray-900">{auction.title}</h1>
          <p className="text-gray-600 mt-4 leading-relaxed">{auction.description}</p>
        </div>
      </div>

      {/* Right Column: Bidding Engine */}
      <div className="flex flex-col space-y-6">
        {/* Status Banner */}
        <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
          <div className="flex justify-between items-center mb-4">
            <div className="flex items-center space-x-2 text-gray-500">
              <Clock className="w-5 h-5" />
              <span className="font-medium">Time Remaining</span>
            </div>
            <span className={`text-2xl font-mono font-bold ${isLocalTimerZero ? 'text-red-500' : 'text-gray-900'}`}>
              {formattedTime}
            </span>
          </div>

          <div className="border-t border-gray-100 pt-4">
            <p className="text-sm text-gray-500 mb-1">Current Bid</p>
            <div className="flex items-end space-x-3">
              <span className="text-5xl font-bold text-gray-900">
                ${auction.current_price.toFixed(2)}
              </span>
              {isWinning && isAuctionActive && (
                <span className="mb-2 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                  <CheckCircle2 className="w-3 h-3 mr-1" /> You are winning
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Bidding Controls */}
        <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
          <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
            <Gavel className="w-5 h-5 mr-2" /> Place Your Bid
          </h3>

          {/* Connection Status Indicator */}
          {!isConnected && (
            <div className="mb-4 p-3 bg-yellow-50 text-yellow-800 text-sm rounded-lg flex items-center">
              <div className="animate-pulse w-2 h-2 bg-yellow-500 rounded-full mr-2"></div>
              Connecting to live auction server...
            </div>
          )}

          {/* Error Display (OCC Failures / Validation) */}
          {lastError && (
            <div className="mb-4 p-3 bg-red-50 text-red-700 text-sm rounded-lg flex items-start">
              <AlertCircle className="w-4 h-4 mr-2 mt-0.5 flex-shrink-0" />
              <span>{lastError}</span>
            </div>
          )}

          <form onSubmit={handleBidSubmit} className="space-y-4">
            <div>
              <label htmlFor="bid" className="sr-only">Bid Amount</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <span className="text-gray-500 sm:text-lg">$</span>
                </div>
                <input
                  type="number"
                  id="bid"
                  step="0.01"
                  min={minNextBid}
                  disabled={!isAuctionActive || !isConnected}
                  value={bidAmount}
                  onChange={(e) => setBidAmount(e.target.value)}
                  className="block w-full pl-8 pr-12 py-4 text-lg border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
                  placeholder={`Enter ${minNextBid.toFixed(2)} or more`}
                />
              </div>
              <p className="mt-2 text-sm text-gray-500">
                Minimum increment: ${auction.min_increment.toFixed(2)}
              </p>
            </div>

            <button
              type="submit"
              disabled={!isAuctionActive || !isConnected}
              className="w-full flex items-center justify-center py-4 px-4 border border-transparent rounded-lg shadow-sm text-lg font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
            >
              {isAuctionActive ? 'Place Bid' : 'Auction Closed'}
              <ChevronRight className="ml-2 w-5 h-5" />
            </button>
          </form>
        </div>

        {/* Post-Auction State */}
        {!isAuctionActive && isWinning && (
          <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center">
            <h3 className="text-xl font-bold text-green-800 mb-2">Congratulations!</h3>
            <p className="text-green-700 mb-4">You won this auction for ${auction.current_price.toFixed(2)}.</p>
            <button className="bg-green-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-green-700 transition-colors">
              Proceed to Checkout
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
```