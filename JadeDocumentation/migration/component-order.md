# Component Order — JADE 4.6.0 Migration

## Recommended Migration Order

Components should be migrated in dependency order, from least-dependent to most-dependent. This ensures each component's dependencies are already modernized before the component itself is touched.

### Phase 1: Utilities and Infrastructure

**Migrate First** (No dependencies on other JADE components)

| Priority | Package | Files | Dependencies | Notes |
|----------|---------|-------|-------------|-------|
| 1.1 | `jade.util.leap` | ~20 | None | **DO NOT parameterize** — J2ME compatibility |
| 1.2 | `jade.util` | ~35 | `jade.util.leap` | Logger, Event, properties |
| 1.3 | `jade.lang.acl` | ~15 | `jade.util.leap`, `jade.domain` | Parser generated files |
| 1.4 | `jade.FIPA` | IDL | None | FIPA specification files |

### Phase 2: Core Data Types

| Priority | Package | Files | Dependencies | Notes |
|----------|---------|-------|-------------|-------|
| 2.1 | `jade.core` (data) | ~15 | `jade.util.leap` | AID, Location, ContainerID |
| 2.2 | `jade.domain.FIPAAgentManagement` | ~30 | `jade.core` | FIPA ontology |
| 2.3 | `jade.domain.JADEAgentManagement` | ~15 | `jade.core` | JADE ontology |
| 2.4 | `jade.domain.introspection` | ~25 | `jade.core` | Introspection ontology |

### Phase 3: Content System

| Priority | Package | Files | Dependencies | Notes |
|----------|---------|-------|-------------|-------|
| 3.1 | `jade.content.lang.sl` | ~30 | `jade.util.leap` | SL codec, parsers (generated) |
| 3.2 | `jade.content.schema` | ~15 | `jade.util.leap` | Schema system |
| 3.3 | `jade.content.abs` | ~20 | `jade.util.leap` | Abstract content |
| 3.4 | `jade.content.frame` | ~5 | `jade.util.leap` | Frame encoding |
| 3.5 | `jade.content.onto` | ~25 | `jade.content.*` | Ontology system |
| 3.6 | `jade.content` | ~10 | `jade.content.*` | Content manager |

### Phase 4: Core Kernel

| Priority | Package | Files | Dependencies | Notes |
|----------|---------|-------|-------------|-------|
| 4.1 | `jade.core.event` | ~15 | `jade.core` | Event system |
| 4.2 | `jade.core.behaviours` | ~20 | `jade.core`, `jade.util.leap` | Behaviour hierarchy |
| 4.3 | `jade.core` (kernel) | ~25 | `jade.util.leap`, `jade.lang.acl` | Runtime, Agent, Scheduler |
| 4.4 | `jade.domain` | ~10 | `jade.core`, `jade.content` | AMS, DF agents |
| 4.5 | `jade.proto.states` | ~20 | `jade.core` | Protocol states |
| 4.6 | `jade.proto` | ~25 | `jade.core`, `jade.proto.states` | Protocol initiators/responders |

### Phase 5: Transport Layer

| Priority | Package | Files | Dependencies | Notes |
|----------|---------|-------|-------------|-------|
| 5.1 | `jade.imtp.rmi` | ~10 | `jade.core` | RMI IMTP |
| 5.2 | `jade.imtp.leap.nio` | ~20 | `jade.core`, `commons-codec` | NIO transport |
| 5.3 | `jade.imtp.leap.JICP` | ~25 | `jade.core`, `commons-codec` | JICP protocol |
| 5.4 | `jade.imtp.leap.http` | ~15 | `jade.core`, `commons-codec` | HTTP transport |
| 5.5 | `jade.imtp.leap.sms` | ~5 | `jade.core` | SMS transport |
| 5.6 | `jade.imtp.leap` | ~15 | `jade.imtp.leap.*` | LEAP IMTP manager |
| 5.7 | `jade.mtp.http` | ~15 | `jade.core` | HTTP MTP |
| 5.8 | `jade.mtp.iiop` | ~1 | `jade.core` | **EXCLUDE for Java 11+** |

### Phase 6: Services

| Priority | Package | Files | Dependencies | Notes |
|----------|---------|-------|-------------|-------|
| 6.1 | `jade.core.messaging` | ~20 | `jade.core`, `jade.imtp` | Messaging service |
| 6.2 | `jade.core.mobility` | ~6 | `jade.core` | Mobility service |
| 6.3 | `jade.core.management` | ~10 | `jade.core` | Agent management |
| 6.4 | `jade.core.nodeMonitoring` | ~5 | `jade.core` | UDP monitoring |
| 6.5 | `jade.core.replication` | ~10 | `jade.core` | Replication service |
| 6.6 | `jade.core.faultRecovery` | ~5 | `jade.core` | Fault recovery |
| 6.7 | `jade.core.sam` | ~5 | `jade.core` | SAM service |

### Phase 7: High-Level APIs

| Priority | Package | Files | Dependencies | Notes |
|----------|---------|-------|-------------|-------|
| 7.1 | `jade.wrapper` | ~15 | `jade.core`, `jade.domain` | Embedding API |
| 7.2 | `jade.security` | ~10 | `jade.core` | Security |

### Phase 8: Tools and GUI

**Migrate Last** (Depend on everything)

| Priority | Package | Files | Dependencies | Notes |
|----------|---------|-------|-------------|-------|
| 8.1 | `jade.gui` | ~35 | `jade.core`, `jade.lang.acl` | GUI components |
| 8.2 | `jade.tools.rma` | ~40 | `jade.gui`, `jade.core` | RMA tool |
| 8.3 | `jade.tools.sniffer` | ~40 | `jade.gui`, `jade.core` | Sniffer tool |
| 8.4 | `jade.tools.introspector` | ~20 | `jade.gui`, `jade.core` | Introspector |
| 8.5 | `jade.tools.dfgui` | ~30 | `jade.gui`, `jade.domain` | DF GUI |
| 8.6 | `jade.tools.logging` | ~20 | `jade.gui`, `jade.core` | Logging tool |
| 8.7 | `jade.tools.testagent` | ~5 | `jade.gui` | Test agent |
| 8.8 | `jade.tools.SocketProxyAgent` | ~5 | `jade.core` | Socket proxy |
| 8.9 | `jade.tools.applet` | ~5 | `jade.gui` | Applet tools |

## Dependency Graph for Migration

```
jade.util.leap ──────────────────────────────────────────────┐
    │                                                       │
    ▼                                                       │
jade.util ──────────────────────────────────────────────────┼───┐
    │                                                       │   │
    ▼                                                       │   │
jade.lang.acl ──────────────────────────────────────────────┼───┤
    │                                                       │   │
    ├───────────────────────────────────────────────────────┘   │
    │                                                           │
    ▼                                                           │
jade.core (data types) ──────────────────────────────────────────┼───┐
    │                                                           │   │
    ├───────────────────────────────────────────────────────┘   │   │
    ▼                                                           │   │
jade.domain.FIPAAgentManagement ────────────────────────────────┼───┤
    │                                                           │   │
    ▼                                                           │   │
jade.domain.introspection ──────────────────────────────────────┼───┤
    │                                                           │   │
    ├───────────────────────────────────────────────────────┘   │   │
    ▼                                                           │   │
jade.content.* (all subpackages) ────────────────────────────────┼───┤
    │                                                           │   │
    ├───────────────────────────────────────────────────────┘   │   │
    ▼                                                           │   │
jade.core.behaviours ──────────────────────────────────────────┼───┤
    │                                                           │   │
    ├───────────────────────────────────────────────────────┘   │   │
    ▼                                                           │   │
jade.core (kernel) ──────────────────────────────────────────────┼───┤
    │                                                           │   │
    ├───────────────────────────────────────────────────────┘   │   │
    ▼                                                           │   │
jade.domain (AMS/DF) ────────────────────────────────────────────┼───┤
    │                                                           │   │
    ├───────────────────────────────────────────────────────┘   │   │
    ▼                                                           │   │
jade.proto ────────────────────────────────────────────────────────┼───┤
    │                                                           │   │
    ├───────────────────────────────────────────────────────┘   │   │
    ▼                                                           │   │
jade.imtp (all) ────────────────────────────────────────────────┼───┤
    │                                                           │   │
    ├───────────────────────────────────────────────────────┘   │   │
    ▼                                                           │   │
jade.mtp (HTTP only for Java 11+) ────────────────────────────────┼───┤
    │                                                           │   │
    ├───────────────────────────────────────────────────────┘   │   │
    ▼                                                           │   │
jade.core.messaging ──────────────────────────────────────────────┼───┤
    │                                                           │   │
    ├───────────────────────────────────────────────────────┘   │   │
    ▼                                                           │   │
jade.core (services) ──────────────────────────────────────────────┼───┤
    │                                                           │   │
    ├───────────────────────────────────────────────────────┘   │   │
    ▼                                                           │   │
jade.wrapper ────────────────────────────────────────────────────┼───┤
    │                                                           │   │
    ├───────────────────────────────────────────────────────┘   │   │
    ▼                                                           │   │
jade.gui ────────────────────────────────────────────────────────┼───┤
    │                                                           │   │
    ├───────────────────────────────────────────────────────┘   │   │
    ▼                                                           ▼   │
jade.tools (all) ◄───────────────────────────────────────────────┘
```

## Special Handling Required

### Critical: Never Parameterize
- `jade.util.leap.*` — J2ME compatibility required
- `jade.util.leap.Serializable` — J2ME interface

### Critical: Exclude for Java 11+
- `jade.mtp.iiop` — CORBA removed in Java 9+
- Any code using `javax.rmi.*` or `org.omg.*`

### Build System Updates
1. Update `build.xml` source/target version at each step
2. Update `commons-codec` version when migrating to Java 11+
3. Add JavaCC regeneration step for modern JavaCC version

---

*See [Test Specifications](./test-specifications.md) for validation tests at each phase.*
