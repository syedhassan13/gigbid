# ADR 0001: Hand-written LangGraph StateGraphs, one thread per job / conversation
Status: accepted

Context: the brief needs parallel analysis, bounded critique loops, human interrupts, durability and replay.
Decision: two compiled `StateGraph`s (bid, conversation) with typed state and reducers, `Send` fan-out to three
analysis nodes, `interrupt()` approval gates, and a Postgres checkpointer. Prebuilt agents are used only as
baselines (R&D C).
Consequences: more code than a ReAct agent, but every decision is a node with a typed hand-off, which can be
traced, tested and replayed.
