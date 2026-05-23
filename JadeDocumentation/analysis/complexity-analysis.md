# Complexity Analysis — JADE 4.6.0

## Cyclomatic Complexity Hotspots

### High-Complexity Methods

Methods with elevated cyclomatic complexity (branching > 10):

#### jade.core.Agent
- `send(ACLMessage)` — Complex message routing, error handling
- `receive(MessageTemplate, long, long)` — Multiple blocking modes
- `addBehaviour(Behaviour)` — Thread management, synchronization
- `setup()` — Template method (user-defined)
- `getHelper(String)` — Service lookup, error handling

#### jade.lang.acl.ACLMessage
- `setContentObject(Serializable)` — Multiple content types
- `getContentObject()` — Deserialization branches
- `getAllUserDefinedSlots()` — Iteration with type checks

#### jade.domain.DFService
- `search(Agent, DFAgentDescription, SearchConstraints)` — Complex search logic
- `fillMatchSet()` — Fuzzy matching algorithms
- `matchServices()` — Multi-criteria matching

#### jade.core.messaging.MessagingService
- `dispatchInMessage(ACLMessage)` — Message routing logic
- `routeMessage(ACLMessage, AID)` — Complex routing with aliases
- `deliverMessage(ACLMessage, AID)` — Delivery with retry logic

#### jade.content.onto.Ontology
- `validate(AbsObject)` — Schema validation with recursion
- `mergeOntologies(Ontology[])` — Complex merging logic

### Complexity Distribution by Package

| Package | Avg Method Complexity | Hotspot Methods |
|---------|---------------------|-----------------|
| jade.core | High | Agent.send, receive, addBehaviour |
| jade.messaging | High | dispatchInMessage, routeMessage |
| jade.domain | Medium-High | DFService.search, matchServices |
| jade.content.onto | Medium-High | Ontology.validate, mergeOntologies |
| jade.lang.acl | Medium | ACLMessage encoding |
| jade.proto | Medium | Protocol state machines |
| jade.gui | Medium | Event handling |

## Cognitive Complexity

### Hardest Files to Understand

1. **jade.core.Agent.java** (~2,502 lines)
   - Mixes 10+ responsibility areas
   - Complex thread synchronization
   - State machine for lifecycle

2. **jade.core.messaging.MessagingService.java** (~large)
   - Multi-layer message routing
   - Alias resolution
   - MTP management

3. **jade.domain.df.java** (~1,200 lines)
   - Federation logic
   - Fuzzy matching
   - Subscription management

4. **jade.content.onto.Ontology.java** (~1,000+ lines)
   - Recursive schema validation
   - Multiple introspector types
   - Complex type mapping

5. **jade.proto.Initiator.java** (large)
   - Generic protocol state machine
   - Session management
   - DataStore key management

## Structural Complexity

### Inheritance Depth

| Class | Inheritance Depth | Root Class |
|-------|-----------------|-----------|
| `jade.domain.ams` | 1 | `Agent` |
| `jade.domain.df` | 1 | `Agent` |
| `jade.tools.rma.rma` | 1 | `Agent` |
| `jade.tools.sniffer.Sniffer` | 1 | `Agent` |
| `jade.core.behaviours.FSMBehaviour` | 2 | `CompositeBehaviour` |
| `jade.core.behaviours.SequentialBehaviour` | 1 | `CompositeBehaviour` |
| `jade.proto.ContractNetInitiator` | 2 | `Initiator` → `Behaviour` |

### Fan-Out (Method Calls per Method)

| Method | Estimated Fan-Out | Type |
|--------|-----------------|------|
| `Agent.send()` | 10+ | High |
| `Agent.addBehaviour()` | 8+ | High |
| `MessagingService.dispatchInMessage()` | 10+ | High |
| `DFService.register()` | 5+ | Medium |
| `Ontology.toObject()` | 5+ | Medium |

## State Machine Complexity

### Agent Lifecycle States
```
[INIT] → [ACTIVE] → [SUSPENDED] → [ACTIVE]
              ↓            ↓
          [WAITING] ←———————
              ↓
          [DELETED]
```

### FSMBehaviour State Machine
- Unlimited states
- Default transitions
- Multiple exit codes
- Guard conditions (remainWithin)

### Protocol State Machines
Each FIPA protocol has its own state machine:
- ContractNet: CFP → PROPOSE/PROPOSE_COLLECT → ACCEPT/REJECT → DONE
- AchieveRE: REQUEST → REFUSE/AGREE/NOT_UNDERSTOOD/INFORM/FAILURE → DONE
- Propose: PROPOSE → ACCEPT/REJECT/COUNTER_PROPOSE → DONE
- Subscription: SUBSCRIBE → AGREE/REFUSE → INFORM → DONE

## Conditional Logic Density

### Nested Conditionals (>5 levels)

**Agent.java**:
```
setup() / doMove() / lifecycle methods
├── if (state == X)
│   ├── if (destination != null)
│   │   ├── try { ... }
│   │   │   ├── if (helper != null)
│   │   │   │   └── synchronized (...)
```

**MessagingService.java**:
```
routeMessage()
├── if (local)
│   ├── Iterator
│   │   └── if (matches)
├── else
│   ├── if (MTP exists)
│   │   └── if (address valid)
│   │       └── try { deliver() }
```

## Algorithmic Complexity

### O(n) Operations
- `DFService.search()` — Linear scan of all registrations
- `MessageTemplate.match()` — Linear scan of template terms
- `Ontology.getSchema()` — HashMap lookup (O(1) average)

### O(n²) or Worse
- `DFDBKB.matchServices()` — Fuzzy matching with all registrations
- `Ontology.mergeOntologies()` — Recursive schema merging
- `LoaderBehaviour.load()` — Class loading with dependency resolution

## Maintainability Index

Based on Halstead metrics approximation:

| Package | Maintainability | Assessment |
|---------|----------------|------------|
| jade.util | Medium-High | Well-isolated utilities |
| jade.lang.acl | Medium | Stable, well-documented |
| jade.core.behaviours | Medium | Regular pattern, predictable |
| jade.core | **Low** | God class, high complexity |
| jade.domain | Medium-Low | Large but structured |
| jade.content.onto | Medium | Complex but necessary |
| jade.gui | Low-Medium | Event-driven, moderate |
| jade.tools | Medium | Repetitive tool patterns |

## Refactoring Priorities

### Priority 1: Immediate
- `jade.core.Agent` — Extract responsibilities

### Priority 2: Short-term
- `jade.core.messaging.MessagingService` — Extract routing logic
- `jade.domain.df` — Extract search engine

### Priority 3: Medium-term
- `jade.content.onto.Ontology` — Simplify introspector logic
- `jade.proto.Initiator` — Reduce generics complexity

---

*See [Dependency Analysis](./dependency-analysis.md) for coupling metrics.*
