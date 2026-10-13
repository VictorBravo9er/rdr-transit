# AGENTS.md

> **UNIVERSAL OPERATIONAL DIRECTIVE & SYSTEM PROMPT FOR AI CODING AGENTS**  
> **Mandatory instructions for any AI assistant working on the RDR-Transit codebase.**

---

## 🚨 MANDATORY PRE-FLIGHT DIRECTIVE: READ DOCUMENTATION FIRST

**Stop and Read First:** Before browsing directory trees, inspecting raw source files in `src/`, `apps/`, or `tests/`, or attempting code edits, **you MUST first read and study the complete systems documentation:**

1. 📘 [**System Overview & Wire Protocols** (`docs/SYSTEM_DOCUMENTATION.md`)](file:///home/victor/antigravity/RDR-transit/docs/SYSTEM_DOCUMENTATION.md)
   * High-level architecture, network topology, and core safety tenets.
   * Layer 1: UDP `56780` beacon discovery format and broadcast socket mechanics.
   * Layer 2: TCP `17116` binary wire protocol with `<ib` 5-byte header framing and `PacketType` specification.
2. 💻 [**Source Code Reference** (`docs/SOURCE_CODE_REFERENCE.md`)](file:///home/victor/antigravity/RDR-transit/docs/SOURCE_CODE_REFERENCE.md)
   * Detailed breakdown of `src/rdr_transit/` modules, algorithms, and data structures.
   * Concurrency models: multi-threaded `BatchSender` streaming, `ReceiverServer` client threads, and Textual TUI workers.
   * Filesystem traversal guardrails, symlink skips, and Windows character sanitization in `utils/filesystem.py`.
3. 🎨 [**UI/UX Specification & Guide** (`docs/UI_UX_REFERENCE.md`)](file:///home/victor/antigravity/RDR-transit/docs/UI_UX_REFERENCE.md)
   * Comprehensive terminal interface blueprints, design systems, and color palettes.
   * Full keyboard navigation matrix and modal dialogs in Textual TUI.
   * End-to-end interaction flowcharts for file staging, transmission, and daemon reception.

### Rationale:
RDR-Transit implements a cross-platform, wire-compatible network protocol that communicates directly with heterogeneous devices. Modifying code without internalizing the protocol contracts, packet structures, and cross-platform sanitization invariants leads to broken byte framing, network stalls, or platform regressions.

---

## 🔒 Non-Negotiable System Invariants

Whenever proposing or executing modifications, uphold these invariants without exception:

1. **Protocol Framing Invariant (`<ib`)**:
   * Header format is strictly 5 bytes: little-endian signed 32-bit integer length followed by signed 8-bit integer packet type (`struct.Struct("<ib")` in Python).
   * **Never** change endianness, byte offsets, or header layout.
2. **Network Asynchrony & UI Thread Isolation**:
   * Sockets must **never** block UI execution threads.
   * In Textual (TUI): Execute transfers and network discovery via asynchronous workers (`@work(exclusive=True)`).
3. **Filesystem Safety & Path Sanitization**:
   * All network-received files must pass through `sanitize_destination_path()`.
   * Never permit directory traversal (`../`) to escape the target directory.
   * Replace forbidden Windows characters (`:`, `*`, `?`, `"`, `<`, `>`, `|`) with underscores (`_`).
   * Skip symbolic links during directory traversal to avoid circular recursion or arbitrary reads.
4. **Documentation Synchronization Invariant**:
   * Whenever creating or modifying source code in `src/`, assess whether the changes affect:
     - Binary packet structures, framing, or ports (`docs/SYSTEM_DOCUMENTATION.md`)
     - Modules, class APIs, or algorithms (`docs/SOURCE_CODE_REFERENCE.md`)
     - UI/UX blueprints, widgets, or keyboard navigation (`docs/UI_UX_REFERENCE.md`)
     - User-facing CLI commands, options, or setup (`README.md`)
   * If any of the above are affected, **you MUST update the relevant documentation files in the same turn/task**. Never leave source code changes undocumented.

---

## 🧭 Subsystem Quick-Reference Matrix

| Subsystem | Source Location | Documentation Reference |
| :--- | :--- | :--- |
| **Wire Protocol Framing** | `src/rdr_transit/protocol.py` | [`docs/SOURCE_CODE_REFERENCE.md#2`](file:///home/victor/antigravity/RDR-transit/docs/SOURCE_CODE_REFERENCE.md) |
| **UDP 56780 Discovery** | `src/rdr_transit/discovery.py` | [`docs/SOURCE_CODE_REFERENCE.md#3`](file:///home/victor/antigravity/RDR-transit/docs/SOURCE_CODE_REFERENCE.md) |
| **TCP 17116 Sender** | `src/rdr_transit/transfer/sender.py` | [`docs/SOURCE_CODE_REFERENCE.md#41`](file:///home/victor/antigravity/RDR-transit/docs/SOURCE_CODE_REFERENCE.md) |
| **TCP 17116 Receiver** | `src/rdr_transit/transfer/receiver.py` | [`docs/SOURCE_CODE_REFERENCE.md#42`](file:///home/victor/antigravity/RDR-transit/docs/SOURCE_CODE_REFERENCE.md) |
| **Path Sanitization & Crawl** | `src/rdr_transit/utils/filesystem.py` | [`docs/SOURCE_CODE_REFERENCE.md#5`](file:///home/victor/antigravity/RDR-transit/docs/SOURCE_CODE_REFERENCE.md) |
| **Terminal UI (Textual)** | `src/rdr_transit/tui/app.py` | [`docs/UI_UX_REFERENCE.md#2`](file:///home/victor/antigravity/RDR-transit/docs/UI_UX_REFERENCE.md) |
| **CLI & Commands** | `src/rdr_transit/cli.py` | [`docs/SOURCE_CODE_REFERENCE.md#73`](file:///home/victor/antigravity/RDR-transit/docs/SOURCE_CODE_REFERENCE.md) |

---

## 🛠️ Step-by-Step Agent Workflow

```
1. STUDY DOCS       👉 Read relevant docs in docs/ before reading raw code
2. TARGET CODE      👉 Locate exact subsystem using the Matrix above
3. SURGICAL EDIT    👉 Apply minimal, clean changes respecting system invariants
4. TEST & VERIFY    👉 Run `uv run pytest` to ensure 100% test suite pass rate
5. SYNC DOCS        👉 Update corresponding docs/ and README.md if code edits require it
```

### Verification Command:
```bash
uv run pytest
```
Always verify that all 18+ tests continue to pass after any code changes.
