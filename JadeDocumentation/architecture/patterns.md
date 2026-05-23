# Patterns — JADE 4.6.0

## Architectural Patterns

### 1. Service-Oriented Architecture (SOA)

JADE's kernel is organized as a collection of services, each implementing specific functionality.

**Implementation**: `jade.core.Service` base class with `Service.Slice` interface.

```
Agent
  └── ServiceFinder
        ├── MessagingService (Slice)
        ├── MobilityService (Slice)
        ├── ReplicationService (Slice)
        └── NotificationService (Slice)
```

**Pattern Elements**:
- `Service` abstract class provides service lifecycle management
- `Service.Slice` interface defines the service's remote interface
- `ServiceHelper` provides typed access from agents to services
- `ServiceFinder` provides dynamic service discovery

---

### 2. Microservices/Federated Container Architecture

The platform is organized as a federated set of containers, similar to a microservices architecture.

**Components**:
- Main Container: Hosts AMS, DF, service managers (central coordinator)
- Peripheral Containers: Host regular agents (stateless workers)
- IMTP Layer: Handles inter-container communication (service mesh)

**Communication**: Services call each other via:
- **Vertical Commands**: Local service-to-kernel calls
- **Horizontal Commands**: Inter-container calls via stubs/skeletons

---

### 3. Observer Pattern (Event System)

JADE uses the Observer pattern extensively for event propagation.

**Event Hierarchy**:
```
JADEEvent (base)
  ├── AgentEvent (agent lifecycle)
  ├── ContainerEvent (container lifecycle)
  ├── MessageEvent (message sent/received)
  ├── PlatformEvent (platform-wide events)
  └── MTPEvent (MTP events)
```

**Listener Hierarchy**:
```
AgentListener
  ├── AgentAdapter (convenience adapter)
  └── jade.core.event.NotificationProxy

ContainerListener
  └── ContainerAdapter

MessageListener
  └── MessageAdapter
```

---

### 4. Singleton Pattern

Used for globally accessible components.

**Examples**:
- `jade.core.Runtime` — Single instance controlling platform
- `jade.content.onto.BasicOntology` — Singleton ontology instance
- `jade.content.onto.SerializableOntology` — Singleton
- `jade.util.Logger` — Singleton logger factory
- `jade.domain.FIPANames` — Constants class (effectively singleton)

---

### 5. Factory Pattern

**Examples**:
- `ServiceFinder.getService()` — Creates/retrieves service instances
- `ProfileImpl.getInstance()` — Profile factory
- `BeanOntologyBuilder` — Builds ontologies from Java beans
- `jade.content.frame.FrameException` — Exception factory (creates typed exceptions)
- `ObjectSchemaImpl.getSchema()` — Schema factory

---

### 6. Proxy / Remote Proxy Pattern

Inter-container communication uses stubs and skeletons.

**Pattern**:
- `NodeStub` / `NodeSkel` — Node communication
- `FrontEndStub` / `FrontEndSkel` — FE/BE communication
- `BackEndStub` / `BackEndSkel` — BE/FE communication
- `ServiceManagerRMIImpl` / `ServiceManagerRMI` — RMI stubs
- `SliceProxy` — Dynamic proxy for service slices

---

### 7. Strategy Pattern

**Examples**:
- `Behaviour` hierarchy — Different scheduling strategies
- `MessageTemplate.MatchExpression` — Different message matching strategies
- `MTPDescriptor` — Pluggable MTP strategies
- `ICP` (jade.imtp.leap.ICP) — Inter-container protocol strategies

---

### 8. Template Method Pattern

**Examples**:
- `Behaviour.action()` / `Behaviour.done()` — Template method: `schedule()` calls `action()` repeatedly until `done()` returns true
- `CompositeBehaviour` — Template for combining behaviours
- `FSMBehaviour` — Template for state machine execution
- `Ontology.validate()` — Template for content validation

---

### 9. Decorator Pattern

**Examples**:
- `jade.core.behaviours.WrapperBehaviour` — Wraps a behaviour with additional logic
- `jade.imtp.leap.nio.NIOJICPConnectionWrapper` — Decorates connections with NIO

---

### 10. Builder Pattern

**Examples**:
- `BeanOntologyBuilder` — Builds ontology from annotated classes
- `ProfileImpl` — Builds configuration profiles

---

### 11. Null Object Pattern

**Examples**:
- `jade.util.leap.EmptyIterator` — Null object for empty collections
- `jade.content.onto.basic.TrueProposition` / `FalseProposition` — Null objects for boolean predicates

---

### 12. Command Pattern

Used throughout the kernel for command processing.

**Implementation**:
- `jade.core.Command` — Base command class
- `jade.core.GenericCommand` — Generic command implementation
- `jade.core.VerticalCommand` — Kernel-bound commands
- `jade.core.HorizontalCommand` — Container-bound commands
- `jade.core.Sink` — Command sinks (processors)

---

### 13. Mediator Pattern

**Examples**:
- `jade.imtp.leap.CommandDispatcher` — Mediates inter-container commands
- `jade.imtp.leap.nio.NIOMediator` — Mediates NIO connections
- `jade.core.CommandProcessor` — Mediates command flow through filters/sinks

---

### 14. State Machine Pattern

**Implementation**: `jade.core.behaviours.FSMBehaviour`

**States**:
- Each child behaviour represents a state
- Transitions defined via `registerTransition(stateName, nextState)`
- Terminal states handled specially

---

### 15. Registry Pattern

**Examples**:
- AMS as agent registry
- DF as service registry
- `ContainerTable` as container registry
- `Profile` as configuration registry

---

## Design Patterns in Detail

### Behaviour Pattern Hierarchy

```
                    Behaviour (abstract)
                          |
        +-----------------+-----------------+
        |                 |                 |
   SimpleBehaviour   CompositeBehaviour   LoaderBehaviour
        |                 |
        |     +-----------+-----------+-------+
        |     |           |           |       |
        |  Sequential  Parallel     FSM    SerialBehaviour
        |                            |
     CyclicBehaviour              (FSM transitions)
        |
   OneShotBehaviour
        |
   +-----+-----+
   |           |
TickerBehaviour  WakerBehaviour
```

### Message Routing Pattern

```
ACLMessage.send()
       |
       v
MessageQueue (per-agent)
       |
       v
OutBox (per-container)
       |
       v
OutgoingEncodingFilter
       |
       v
MessagingService routing
       |
       +---> Local delivery
       |
       +---> MTP.deliver() (remote)
              |
              +---> HTTP MTP
              +---> IIOP MTP
              +---> JICP MTP
```

### Ontology Mapping Pattern

```
Java Bean (POJO with annotations)
       |
       v
BeanOntologyBuilder
       |
       v
Ontology instance
       |
       +---> ConceptSchema / PredicateSchema / AgentActionSchema
       |
       v
ContentManager.encode()
       |
       v
SL Codec (SL0 / SL1 / SL2)
       |
       v
ACLMessage content (String)
```

### Container Lifecycle Pattern

```
Runtime.startUp() / createAgentContainer()
       |
       v
Profile configuration
       |
       v
ContainerController creation
       |
       +-- MainContainer:
       |    ├── ServiceManager initialization
       |    ├── PlatformManager initialization
       |    ├── AMS creation
       |    └── DF creation
       |
       +-- PeripheralContainer:
            ├── IMTPManager connection
            ├── ServiceFinder initialization
            └── Agent registration
```

---

## Anti-Patterns Detected

### 1. God Class — Agent.java (~2,502 lines)

`Agent.java` is extremely large and handles too many concerns:
- Lifecycle management
- Message handling
- Behaviour scheduling
- Service discovery
- O2A interface
- Security
- Mobility

**Recommendation**: Extract specific responsibilities into helper classes or services.

### 2. Primitive Obsession — AID.java

`AID.java` uses string manipulation extensively for GUID parsing and construction instead of structured types.

### 3. Parallel Inheritance — jade.util.leap vs java.util

Duplicate collection hierarchy specifically for J2ME compatibility adds complexity and maintenance burden.

### 4. Complex Cross-Cutting Concerns — Agent.java Threading

`Agent.java` has complex synchronization and thread management spread throughout rather than isolated in a dedicated scheduler abstraction.

### 5. Deprecated Protocol Implementations

`jade.proto.AchieveREResponder` and `jade.proto.ContractNetResponder` have partially deprecated APIs where only some methods are deprecated while others remain.

---

## FIPA Compliance Patterns

### ACL Message Pattern
All agent communication follows FIPA ACL structure with standardized performatives, content encoding, and envelope wrapping.

### Interaction Protocol Pattern
Each FIPA protocol (ContractNet, AchieveRE, etc.) follows a consistent pattern:
1. Initiator behaviour sends initial message(s)
2. Protocol state machine handles responses
3. Result collected in DataStore with standardized keys

### Ontology Pattern
All ontologies follow the same structure:
1. Extend `Ontology`
2. Implement vocabulary constants
3. Register concept/action/predicate schemas
4. Use `BCReflectiveIntrospector` for bean mapping

---

*See [Business Logic](../behavior/business-logic.md) for how these patterns compose into workflows.*
