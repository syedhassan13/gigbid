# ADR 0002: One marketplace port, adapters behind our own MCP server
Status: accepted

Decision: the graph talks to `MarketplacePort`, which talks only to the Marketplace MCP server. The server owns
auth, rate limits, idempotency, dry-run and audit, and selects the GigSim or Upwork-live adapter per user account.
Consequences: live mode is a config/account change, and the viva "kill the marketplace server" scenario is a
single failure point with one degraded-mode path.
