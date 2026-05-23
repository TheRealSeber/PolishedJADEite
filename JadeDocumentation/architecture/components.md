# Components — JADE 4.6.0

## Core Kernel Components

### jade.core.Runtime
**Type**: Singleton class
**File**: `JADE-4.6.0/src/jade/src/jade/core/Runtime.java` (~344 lines)

The central runtime controller for the JADE platform. Manages container lifecycle and provides platform-wide coordination.

**Key Responsibilities**:
- Singleton pattern for platform-wide access
- Multiple vs. single container mode management
- Thread group management for agent threads
- Container termination coordination

**Key Methods**:
| Method | Description |
|--------|-------------|
| `instance()` | Returns singleton Runtime instance |
| `createMainContainer(Profile)` | Creates main container in multiple mode |
| `createAgentContainer(Profile)` | Creates peripheral container |
| `startUp(Profile)` | Starts single-container mode |
| `shutDown()` | Terminates the platform |
| `invokeOnCurrentThread(Runnable)` | Executes agent code on current thread |

---

### jade.core.Agent
**Type**: Base class (extends `jade.util.leap.Serializable`)
**File**: `JADE-4.6.0/src/jade/src/jade/core/Agent.java` (~2,502 lines)

The fundamental abstraction for all software agents. Every user-defined agent extends this class.

**Key Responsibilities**:
- Agent lifecycle management
- Message handling and dispatch
- Behaviour scheduling
- Service discovery and access
- O2A (Object-to-Agent) interface
- Agenttoolkit delegation

**Key Methods**:
| Method | Description |
|--------|-------------|
| `setup()` | Called once at agent startup — override for initialization |
| `takeDown()` | Called before agent termination — override for cleanup |
| `send(ACLMessage)` | Send an ACL message |
| `receive(MessageTemplate)` | Receive a message matching template |
| `addBehaviour(Behaviour)` | Add a behaviour to the agent's pool |
| `removeBehaviour(Behaviour)` | Remove a behaviour |
| `getHelper(String)` | Get a service helper |
| `doMove(Location)` | Request agent mobility |
| `doClone(Location, String)` | Clone agent to new location |

---

### jade.core.AID
**Type**: Data class (implements `Comparable`, `jade.util.leap.Serializable`)
**File**: `JADE-4.6.0/src/jade/src/jade/core/AID.java` (~562 lines)

Represents a globally unique agent identifier following FIPA specifications.

**Key Fields**:
| Field | Type | Description |
|-------|------|-------------|
| `name` | String | Global agent name (GUID format: localName@platformName) |
| `addresses` | List | Transport addresses (HTTP, HTTPS, etc.) |
| `resolvers` | List | Resolving AIDs (for federation) |

**Key Methods**:
| Method | Description |
|--------|-------------|
| `getLocalName()` | Extract local name from full GUID |
| `getHap()` | Get home agent platform name |
| `addAddresses(String)` | Add transport address |
| `isValid()` | Validate AID structure |

---

### jade.core.Profile / jade.core.ProfileImpl
**Type**: Abstract class / Concrete implementation
**File**: `JADE-4.6.0/src/jade/src/jade/core/Profile.java` (~622 lines)

Encapsulates container configuration including connection to main container and local settings.

**Key Constants**:
| Constant | Description |
|----------|-------------|
| `MAIN` | Boolean: is this the main container? |
| `HOST` | Hostname of main container |
| `PORT` | Port of main container |
| `PROTOCOL` | Protocol for connection (RMI, LEAP) |
| `IMTP` | IMTP manager class name |

---

### jade.core.Scheduler
**Type**: Internal class (implements `Serializable`)
**File**: `JADE-4.6.0/src/jade/src/jade/core/Scheduler.java` (~??? lines)

Manages the behaviour execution loop for an agent. Invoked by the Agent's run method.

---

### jade.core.behaviours.Behaviour
**Type**: Abstract base class (implements `Serializable`)
**File**: `JADE-4.6.0/src/jade/src/jade/core/behaviours/Behaviour.java` (~??? lines)

Abstract base for all agent behaviours. Each behaviour has a `done()` method that returns true when the behaviour has completed, and an `action()` method that is called on each execution cycle.

**Subclasses**:
| Class | Purpose |
|-------|---------|
| `SimpleBehaviour` | Single-step behaviour |
| `CyclicBehaviour` | Repeating behaviour (never done) |
| `OneShotBehaviour` | One-time behaviour |
| `TickerBehaviour` | Periodic behaviour |
| `WakerBehaviour` | Delayed one-time behaviour |
| `SequentialBehaviour` | Series of child behaviours |
| `ParallelBehaviour` | Concurrent child behaviours |
| `FSMBehaviour` | State machine behaviour |
| `LoaderBehaviour` | Dynamic behaviour loading |

---

## Container Components

### jade.core.AgentContainerImpl
**Type**: Implementation class
**File**: `JADE-4.6.0/src/jade/src/jade/core/AgentContainerImpl.java`

Implementation of `AgentContainer` interface. Manages all agents running within a single JVM.

### jade.core.MainContainerImpl
**Type**: Implementation class (extends `AgentContainerImpl`)
**File**: `JADE-4.6.0/src/jade/src/jade/core/MainContainerImpl.java`

Specialized container for the main platform container. Hosts AMS, DF, and service managers.

### jade.core.FrontEndContainer
**Type**: Implementation class
**File**: `JADE-4.6.0/src/jade/src/jade/core/FrontEndContainer.java`

Lightweight container for LEAP/ME environments. Delegates to a back-end container.

### jade.core.BackEndContainer
**Type**: Implementation class
**File**: `JADE-4.6.0/src/jade/src/jade/core/BackEndContainer.java`

Back-end container that hosts agents and communicates with front-end containers.

---

## Domain Components (FIPA Agents)

### jade.domain.ams
**Type**: Agent class
**File**: `JADE-4.6.0/src/jade/src/jade/domain/ams.java`

The Agent Management System — mandatory platform agent. Manages platform-wide agent lifecycle.

**Responsibilities**:
- Agent registration and deregistration
- Agent lifecycle control (suspend, resume, kill)
- Platform shutdown coordination
- AMS subscription for agent events

### jade.domain.df
**Type**: Agent class
**File**: `JADE-4.6.0/src/jade/src/jade/domain/df.java`

The Directory Facilitator — mandatory platform service. Provides yellow pages functionality.

**Responsibilities**:
- Service registration (DFAgentDescription + ServiceDescription)
- Service search with constraints
- Federation support (parent/child DFs)
- DF subscription for registry changes

---

## Messaging Components

### jade.lang.acl.ACLMessage
**Type**: Data class
**File**: `JADE-4.6.0/src/jade/src/jade/lang/acl/ACLMessage.java` (~1,322 lines)

Implements the FIPA ACL message standard. All agent-to-agent communication uses ACLMessage.

**Key Fields**:
| Field | Type | Description |
|-------|------|-------------|
| `performative` | int | Message type (REQUEST, INFORM, QUERY_IF, etc.) |
| `sender` | AID | Sending agent |
| `receivers` | List | Receiving agents |
| `content` | String | Message content |
| `language` | String | Content language |
| `ontology` | String | Content ontology |
| `protocol` | String | Interaction protocol |
| `conversation-id` | String | Conversation identifier |

**Performatives**: INFORM, REQUEST, QUERY_IF, PROPOSE, ACCEPT_PROPOSAL, REJECT_PROPOSAL, CFP, SUBSCRIBE, NOTIFY, CONFIRM, DISCONFIRM, AGREE, CANCEL, FAILURE, REFUSE

### jade.lang.acl.MessageTemplate
**Type**: Class with nested interfaces
**File**: `JADE-4.6.0/src/jade/src/jade/lang/acl/MessageTemplate.java`

Pattern matching for selecting messages from the queue.

**Factory Methods**:
| Method | Description |
|--------|-------------|
| `MatchPerformative(int)` | Match by performative |
| `MatchSender(AID)` | Match by sender |
| `MatchReceiver(AID)` | Match by receiver |
| `MatchProtocol(String)` | Match by protocol |
| `MatchLanguage(String)` | Match by language |
| `and(MessageTemplate, MessageTemplate)` | Combine with AND |
| `or(MessageTemplate, MessageTemplate)` | Combine with OR |
| `not(MessageTemplate)` | Negate template |

### jade.lang.acl.ISO8601
**Type**: Utility class
**File**: `JADE-4.6.0/src/jade/src/jade/lang/acl/ISO8601.java`

Date/time formatting per FIPA specifications.

---

## Protocol Components

### jade.proto.ContractNetInitiator / ContractNetResponder
**Type**: Behaviour class
**File**: `JADE-4.6.0/src/jade/src/jade/proto/ContractNetInitiator.java`

FIPA Contract Net Interaction Protocol implementation.

### jade.proto.AchieveREInitiator / AchieveREResponder
**Type**: Behaviour class
**File**: `JADE-4.6.0/src/jade/src/jade/proto/AchieveREInitiator.java`

FIPA Request/Result exchange protocol.

### jade.proto.ProposeInitiator / ProposeResponder
**Type**: Behaviour class
**File**: `JADE-4.6.0/src/jade/src/jade/proto/ProposeInitiator.java`

FIPA Propose interaction protocol.

### jade.proto.SubscriptionInitiator / SubscriptionResponder
**Type**: Behaviour class
**File**: `JADE-4.6.0/src/jade/src/jade/proto/SubscriptionResponder.java`

Subscription-based notification protocol.

### jade.proto.TwoPhInitiator / TwoPhResponder
**Type**: Behaviour class
**File**: `JADE-4.6.0/src/jade/src/jade/proto/TwoPhInitiator.java`

Two-phase commit protocol.

---

## Content/Ontology Components

### jade.content.ContentManager
**Type**: Service class
**File**: `JADE-4.6.0/src/jade/src/jade/content/ContentManager.java`

Manages content encoding/decoding using ontologies and codecs.

### jade.content.onto.Ontology
**Type**: Abstract class
**File**: `JADE-4.6.0/src/jade/src/jade/content/onto/Ontology.java`

Base class for content ontologies. Maps Java beans to FIPA-SL representations.

### jade.content.onto.BasicOntology
**Type**: Singleton class
**File**: `JADE-4.6.0/src/jade/src/jade/content/onto/BasicOntology.java`

Built-in ontology for primitive types, AID, and Date.

### jade.content.lang.sl.SLCodec
**Type**: Codec class
**File**: `JADE-4.6.0/src/jade/src/jade/content/lang/sl/SLCodec.java`

Codec for FIPA Semantic Language (SL-0, SL-1, SL-2).

---

## Transport Components

### jade.mtp.MTP
**Type**: Interface
**File**: `JADE-4.6.0/src/jade/src/jade/mtp/MTP.java`

Base interface for all Message Transport Protocols.

### jade.mtp.http.MessageTransportProtocol
**Type**: MTP implementation
**File**: `JADE-4.6.0/src/jade/src/jade/mtp/http/MessageTransportProtocol.java`

HTTP-based MTP implementation.

### jade.mtp.iiop.MessageTransportProtocol
**Type**: MTP implementation
**File**: `JADE-4.6.0/src/jade/src/jade/mtp/iiop/MessageTransportProtocol.java`

IIOP/CORBA-based MTP (DEPRECATED — removed in Java 9+).

### jade.imtp.leap.LEAPIMTPManager
**Type**: IMTP implementation
**File**: `JADE-4.6.0/src/jade/src/jade/imtp/leap/LEAPIMTPManager.java`

Lightweight, multi-platform IMTP with JICP, HTTP, and SMS transports.

---

## Wrapper/Embedding API

### jade.wrapper.PlatformController / PlatformControllerImpl
**Type**: Interface + Implementation
**File**: `JADE-4.6.0/src/jade/src/jade/wrapper/PlatformController.java`

API for embedding and controlling JADE from external applications.

### jade.wrapper.ContainerController / AgentContainer
**Type**: Interface
**File**: `JADE-4.6.0/src/jade/src/jade/wrapper/ContainerController.java`

API for controlling an individual container.

### jade.wrapper.AgentController / AgentControllerImpl
**Type**: Interface
**File**: `JADE-4.6.0/src/jade/src/jade/wrapper/AgentController.java`

API for controlling individual agents from external code.

### jade.wrapper.gateway.JadeGateway
**Type**: Utility class
**File**: `JADE-4.6.0/src/jade/src/jade/wrapper/gateway/JadeGateway.java`

Gateway for non-Java applications to interact with JADE agents.

---

## Tool Components

### jade.tools.rma.rma
**Type**: Agent class (GUI)
**File**: `JADE-4.6.0/src/jade/src/jade/tools/rma/rma.java`

Remote Monitoring Agent — GUI for platform administration.

**Capabilities**: Start/kill agents, install/uninstall MTPs, manage containers, view DF descriptions.

### jade.tools.sniffer.Sniffer
**Type**: Agent class (GUI)
**File**: `JADE-4.6.0/src/jade/src/jade/tools/sniffer/Sniffer.java`

Message sniffing tool — visualizes ACL messages between agents.

### jade.tools.introspector.Introspector
**Type**: Agent class (GUI)
**File**: `JADE-4.6.0/src/jade/src/jade/tools/introspector/Introspector.java`

Agent introspection tool — shows agent state, behaviours, message queue.

### jade.tools.dfgui.DFGUI
**Type**: Agent class (GUI)
**File**: `JADE-4.6.0/src/jade/src/jade/tools/dfgui/DFGUI.java`

DF GUI tool — visualizes and manages service registrations.

---

## Service Components

### jade.core.messaging.MessagingService
**Type**: Service class
**File**: `JADE-4.6.0/src/jade/src/jade/core/messaging/MessagingService.java`

Core messaging service managing message routing and delivery.

### jade.core.mobility.AgentMobilityService
**Type**: Service class
**File**: `JADE-4.6.0/src/jade/src/jade/core/mobility/AgentMobilityService.java`

Agent mobility service enabling movement and cloning.

### jade.core.replication.AgentReplicationService
**Type**: Service class
**File**: `JADE-4.6.0/src/jade/src/jade/core/replication/AgentReplicationService.java`

Fault tolerance through agent replication.

### jade.core.event.NotificationService
**Type**: Service class
**File**: `JADE-4.6.0/src/jade/src/jade/core/event/NotificationService.java`

Event notification for platform and agent events.

---

*See [Dependencies](./dependencies.md) for component relationships and [Patterns](./patterns.md) for architectural patterns.*
