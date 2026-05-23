# System Overview — JADE 4.6.0 Architecture

## Overview

JADE (Java Agent DEvelopment Framework) is a FIPA-compliant multi-agent middleware that provides a complete platform for developing, deploying, and managing agent-based distributed systems. The architecture follows a **container-based distributed model** where agents execute within containers that can span multiple JVMs and machines.

## Technology Stack

| Layer | Technology | Version |
|-------|------------|---------|
| **Language** | Java | 1.5 |
| **Build System** | Apache Ant | Any |
| **Parser Generation** | JavaCC | Target: 1.4 |
| **Remote Communication** | RMI, JICP, HTTP | N/A |
| **External Dependency** | Apache Commons Codec | 1.3 |

### Target Platforms (Historical)
- **J2SE** (primary): Standard desktop/server Java
- **J2ME/CDC**: Connected Device Configuration (embedded)
- **MIDP**: Mobile Information Device Profile (via LEAP add-on)

## System Architecture

### Container Model

JADE uses a **federated container architecture**:

```
+------------------------------------------+
|          MAIN CONTAINER                   |
|  +--------+  +--------+  +------------+  |
|  |  AMS   |  |   DF   |  |  Services  |  |
|  +--------+  +--------+  +------------+  |
|                                          |
|  +----------------------------------+    |
|  |        Service Manager            |    |
|  +----------------------------------+    |
|                                          |
|  +--------+  +--------+  +--------+      |
|  | Agent1 |  | Agent2 |  | AgentN |      |
|  +--------+  +--------+  +--------+      |
+------------------------------------------+
           ^
           | JICP/RMI/HTTP
           v
+------------------------------------------+
|        PERIPHERAL CONTAINER 1            |
|  +--------+  +--------+  +--------+      |
|  | AgentA |  | AgentB |  | AgentC |      |
|  +--------+  +--------+  +--------+      |
|                                          |
|  +----------------------------------+    |
|  |        Service Finder             |    |
|  +----------------------------------+    |
+------------------------------------------+
           ^
           | JICP/RMI/HTTP
           v
+------------------------------------------+
|        PERIPHERAL CONTAINER 2            |
|  +--------+  +--------+  +--------+      |
|  | AgentX |  | AgentY |  | AgentZ |      |
|  +--------+  +--------+  +--------+      |
+------------------------------------------+
```

### Architectural Layers

```
┌──────────────────────────────────────────────────────────┐
│                   APPLICATION LAYER                       │
│  User-defined Agents (extend jade.core.Agent)            │
├──────────────────────────────────────────────────────────┤
│                   BEHAVIOUR LAYER                         │
│  SequentialBehaviour, ParallelBehaviour, FSMBehaviour    │
│  CyclicBehaviour, OneShotBehaviour, TickerBehaviour     │
├──────────────────────────────────────────────────────────┤
│                   DOMAIN LAYER                            │
│  AMS Agent, DF Agent, Introspection, Mobility, Persistence│
├──────────────────────────────────────────────────────────┤
│                  CONTENT LAYER                            │
│  ACL Messages, SL Codec, Ontology System, Bean Mapping   │
├──────────────────────────────────────────────────────────┤
│                   SERVICE LAYER                           │
│  Messaging, Mobility, Security, Replication, Notification  │
├──────────────────────────────────────────────────────────┤
│                   KERNEL LAYER                            │
│  Agent, Runtime, Container, Scheduler, Message Queue      │
├──────────────────────────────────────────────────────────┤
│                   TRANSPORT LAYER                         │
│  MTP (HTTP, IIOP), IMTP (JICP, RMI, LEAP)               │
└──────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Runtime (`jade.core.Runtime`)
The **singleton** that controls the JADE runtime system. Provides two modalities:
- **Multiple-Container Mode**: Several containers in one JVM (via `createAgentContainer()` / `createMainContainer()`)
- **Single-Container Mode**: One container per JVM (via `startUp()` / `shutDown()`)

### 2. Agent (`jade.core.Agent`)
The **base class** for all software agents. Key responsibilities:
- Message sending and receiving
- Behaviour scheduling
- Lifecycle management (start, suspend, resume, kill)
- Service access via ServiceHelper
- O2A (Object-to-Agent) interface

### 3. Container (`jade.core.AgentContainerImpl`)
Each JVM hosting agents runs one container. Types:
- **Main Container**: Hosts AMS, DF, and service managers. Coordinates the platform.
- **Peripheral Container**: Hosts regular agents. Connects to main container.

### 4. AMS (Agent Management System) — `jade.domain.ams`
Mandatory platform agent that:
- Manages platform agent lifecycle (create, kill, suspend, resume)
- Maintains agent state registry
- Handles platform shutdown requests

### 5. DF (Directory Facilitator) — `jade.domain.df`
Mandatory platform service that:
- Maintains a service registry (yellow pages)
- Supports service registration, deregistration, modification
- Provides service search with constraints

## Communication Architecture

### ACL Message Flow
```
Agent A                    Container A              Main Container             Container B              Agent B
   |                          |                         |                         |                       |
   |  send(ACLMessage)        |                         |                         |                       |
   |------------------------->|                         |                         |                       |
   |                          |  route(message)         |                         |                       |
   |                          |------------------------->|                         |                       |
   |                          |                         |  resolve(AID)           |                       |
   |                          |                         |------------------------>---------------------->|
   |                          |                         |                         |                       |
   |                          |                         |                         |  deliver(message)     |
   |                          |                         |                         |<----------------------|
   |                          |                         |                         |                       |
```

### Message Transport Protocol (MTP) Layer
JADE supports multiple transport protocols:
- **HTTP MTP** (`jade.mtp.http`): REST-like HTTP transport
- **IIOP MTP** (`jade.mtp.iiop`): CORBA-based IIOP (deprecated in Java 9+)
- **JICP** (`jade.imtp.leap.JICP`): JADE's native lightweight protocol
- **NIO JICP**: Non-blocking JICP variant

### Internal Message Transport (IMTP)
Inter-container communication uses IMTP abstractions:
- **RMI IMTP**: Legacy RMI-based communication
- **LEAP IMTP**: Lightweight multi-platform IMTP with JICP/HTTP/SSL transports

## Service Architecture

JADE uses a **service-oriented kernel** where core functionality is implemented as services:

| Service | Package | Purpose |
|---------|---------|---------|
| **Messaging** | `jade.core.messaging` | Message routing, delivery, encoding |
| **Mobility** | `jade.core.mobility` | Agent movement and cloning |
| **Replication** | `jade.core.replication` | Fault-tolerant agent replication |
| **Node Monitoring** | `jade.core.nodeMonitoring` | UDP-based failure detection |
| **Notification** | `jade.core.event` | JADE event broadcasting |
| **Security** | `jade.security` | Authentication, authorization |
| **SAM** | `jade.core.sam` | Self-healing agent middleware |
| **Fault Recovery** | `jade.core.faultRecovery` | Platform fault recovery |

### Service Discovery Pattern
Services are discovered through `ServiceFinder`:
```java
ServiceHelper helper = myAgent.getHelper(Service.SERVICE_NAME);
```

### Vertical and Horizontal Commands
Services communicate via:
- **Vertical Commands**: Container-to-kernel communication
- **Horizontal Commands**: Container-to-container communication

## Behaviour Model

Agents use a **behaviour tree** for concurrent task execution:

```
Agent
  └── Scheduler
        └── Behaviour Tree
              ├── SequentialBehaviour
              │     ├── Behaviour A
              │     └── Behaviour B
              ├── ParallelBehaviour (AND/OR/WHEN)
              │     ├── Behaviour C
              │     └── Behaviour D
              └── FSMBehaviour
                    ├── State1 --> State2
                    └── State2 --> Terminal
```

### Behaviour Types
| Type | Class | Description |
|------|-------|-------------|
| Simple | `SimpleBehaviour` | Single `action()` + `done()` |
| Cyclic | `CyclicBehaviour` | Loops forever |
| One-shot | `OneShotBehaviour` | Runs once |
| Ticker | `TickerBehaviour` | Repeats at interval |
| Waker | `WakerBehaviour` | Runs once after delay |
| Sequential | `SequentialBehaviour` | Runs children in order |
| Parallel | `ParallelBehaviour` | Runs children concurrently |
| FSM | `FSMBehaviour` | State machine |
| Loader | `LoaderBehaviour` | Loads behaviours dynamically |

## Content Representation

JADE uses a **layered content model**:

```
ACLMessage (FIPA ACL)
  └── Content (String or Serializable)
        └── ContentElement (Concept, Predicate, AgentAction)
              └── AbsObject (Abstract representation)
                    └── Concrete Java Bean
```

### Ontology System
Ontologies map Java beans to FIPA-SL content:
- `BasicOntology`: Primitives, AID, Date, etc.
- `FIPAManagementOntology`: AMS/DF actions
- `JADEManagementOntology`: JADE platform actions
- `MobilityOntology`: Agent movement
- `BeanOntology`: User-defined via annotations

## Deployment Models

### Single JVM
```
java jade.Boot -gui
```

### Multi-Container (Same Machine)
```
Main:  java jade.Boot -container -host localhost -port 1099
FE1:   java jade.MicroBoot -host localhost -port 1099
FE2:   java jade.MicroBoot -host localhost -port 1099
```

### Embedded Container
```java
Runtime runtime = Runtime.instance();
Profile profile = new ProfileImpl();
ContainerController cc = runtime.createAgentContainer(profile);
AgentController ac = cc.createNewAgent("MyAgent", "pkg.MyAgent", args);
ac.start();
```

## Key Architectural Decisions

1. **LEAP Collections**: `jade.util.leap.*` provides J2ME-compatible collections that do NOT extend `java.util.*`. This must be preserved — these types must NOT be parameterized during Java migration.

2. **Custom Serializable**: `jade.util.leap.Serializable` is J2ME-compatible and must be used instead of `java.io.Serializable` where J2ME support is needed.

3. **FIPA Compliance**: All agent communication must comply with FIPA 2000 ACL specifications.

4. **Asynchronous Messaging**: Agent communication is inherently asynchronous. Synchronous patterns (blocking calls) are provided as convenience wrappers.

5. **Service Extensibility**: New services can be added by extending `BaseService` and implementing the `Slice` interface.

---

*See [Components](./components.md) for detailed component documentation.*
