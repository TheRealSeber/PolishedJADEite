> ⚠️ **Early Access**: Behavior documentation is in early access. Please review critically.

# Decision Logic — JADE 4.6.0

## Agent Lifecycle Decisions

### Decision: Agent State Transitions

**Location**: `jade.core.Agent` and `jade.domain.ams`

```
Agent State Machine:
        │
        ▼
    [INIT]
        │
        ▼ start()
        │
    [ACTIVE]◄────────────────┐
        │                    │
        │ suspend()           │ resume()
        ▼                    │
  [SUSPENDED]────────────────┤
        │                    │
        │ kill()             │
        ▼                    │
    [DELETED]                │
                              │
                              │
Additional States:             │
        │                     │
        ▼                     │
    [WAITING]────────────────┘
        │
        │ block() called
        ▼
    (blocked)
        │
        │ message received
        ▼
    [WAITING] ─► [ACTIVE]
```

### Decision: Message Processing Branching

**Location**: `jade.core.behaviours.Behaviour.action()`

```
receive() called
        │
        ▼
Message queue check
        │
        ├──► Message available? ──► YES ──► Process message
        │                                      │
        │                                      ▼
        │                              Return message
        │
        └──► Message available? ──► NO  ──► block()
                                               │
                                               ▼
                                       Wait for message
                                               │
                                               ▼
                                       Unblock on message
```

## Messaging Decisions

### Decision: Message Routing

**Location**: `jade.core.messaging.MessagingService.dispatchInMessage()`

```
Incoming message received
        │
        ▼
Destination AID analysis
        │
        ├──► Is GUID? ──► YES ──► Extract local name
        │                         │
        │                         ▼
        │                   Lookup in LADT
        │
        └──► Is HAP? ──► YES ──► Route to HAP platform
                              │
                              ▼
                        MTP.deliver()
```

### Decision: Local Delivery vs. Remote

**Location**: `jade.core.messaging.MessagingService.routeMessage()`

```
Message needs routing
        │
        ▼
Target AID analysis
        │
        ├──► Is local? ──► YES ──► Deliver to local queue
        │
        └──► Is local? ──► NO  ──► Route to remote container
                                       │
                                       ▼
                                 Check MTP availability
                                       │
                                       ├──► MTP found ──► deliver()
                                       └──► MTP not found ──► FAILURE
```

### Decision: Message Template Matching

**Location**: `jade.lang.acl.MessageTemplate.match()`

```
ACLMessage received
        │
        ▼
Check performative (if specified)
        │
        ├──► Match ──► Continue
        └──► No match ──► Return false
        │
        ▼
Check sender (if specified)
        │
        ├──► Match ──► Continue
        └──► No match ──► Return false
        │
        ▼
... (repeat for all template fields)
        │
        ▼
All conditions met? ──► Return true/false
```

## DF Decisions

### Decision: Service Match Evaluation

**Location**: `jade.domain.DFDBKB.matchServices()`

```
Search template received
        │
        ▼
For each registered description:
        │
        ▼
Name Match?
        │
        ├──► Wildcard? ──► PASS
        ├──► Exact match? ──► PASS
        └──► No match ──► FAIL ──► Skip
        │
        ▼
Ownership Match? (if specified)
        │
        ├──► Match? ──► PASS
        └──► No match ──► FAIL
        │
        ▼
Service Constraints:
        │
        ▼
Type Match?
        │
        ├──► Wildcard? ──► PASS
        ├──► Exact match? ──► PASS
        └──► No match ──► FAIL
        │
        ▼
Languages (subset rule)?
        │
        ├──► Template ⊆ Registered? ──► PASS
        └──► Not subset ──► FAIL
        │
        ▼
Ontologies (subset rule)?
        │
        ├──► Template ⊆ Registered? ──► PASS
        └──► Not subset ──► FAIL
        │
        ▼
Protocols (subset rule)?
        │
        ├──► Template ⊆ Registered? ──► PASS
        └──► Not subset ──► FAIL
        │
        ▼
Properties Match?
        │
        ├──► All template props in registered? ──► PASS
        └──► Missing prop ──► FAIL
        │
        ▼
All pass? ──► Include in results
```

### Decision: DF Registration Validation

**Location**: `jade.domain.DFService.validate()`

```
DFAgentDescription received
        │
        ▼
Name present?
        │
        ├──► YES ──► Continue
        └──► NO  ──► FAIL
        │
        ▼
Name is valid AID?
        │
        ├──► YES ──► Continue
        └──► NO  ──► FAIL
        │
        ▼
For each ServiceDescription:
        │
        ▼
Name present?
        │
        ├──► YES ──► Continue
        └──► NO  ──► FAIL
        │
        ▼
Type present?
        │
        ├──► YES ──► Continue
        └──► NO  ──► WARN (allowed)
        │
        ▼
All services valid? ──► Register
```

## Protocol Decisions

### Decision: Contract Net Response

**Location**: `jade.proto.ContractNetResponder`

```
CFP received
        │
        ▼
handleCfp() called
        │
        ▼
Agent evaluates CFP:
        │
        ├──► CAN participate ──► PROPOSE
        ├──► REFUSE to participate ──► REFUSE
        └──► Cannot understand ──► NOT_UNDERSTOOD
        │
        ▼
After PROPOSE:
        │
        ▼
ACCEPT_PROPOSAL received?
        │
        ├──► YES ──► handleAcceptProposal() ──► INFORM/DONE
        │
        └──► REJECT_PROPOSAL received?
                    │
                    ├──► YES ──► Done
                    └──► NO  ──► Wait for more
```

### Decision: Achieve RE Response

**Location**: `jade.proto.AchieveREResponder`

```
REQUEST received
        │
        ▼
handleRequest() called
        │
        ▼
Agent decides:
        │
        ├──► REFUSE ──► REFUSE response
        ├──► AGREE ──► AGREE, then perform action, then INFORM/FAILURE
        ├──► NOT_UNDERSTOOD ──► NOT_UNDERSTOOD response
        └──► INFORM immediately ──► INFORM response
```

## Behaviour Decisions

### Decision: Behaviour Scheduling

**Location**: `jade.core.Scheduler`

```
Scheduler tick
        │
        ▼
Any behaviour ready?
        │
        ├──► YES ──► Get next ready behaviour
        │              │
        │              ▼
        │         Execute behaviour.action()
        │              │
        │              ▼
        │         behaviour.done()?
        │              │
        │              ├──► YES ──► Remove behaviour
        │              └──► NO  ──► Return to ready pool
        │
        └──► NO  ──► All behaviours blocked
                   │
                   ▼
              Wait for event
```

### Decision: FSM State Transition

**Location**: `jade.core.behaviours.FSMBehaviour`

```
Current state behaviour completes
        │
        ▼
onEnd() returns exit code
        │
        ▼
Look up transition for exit code
        │
        ├──► Transition found ──► Move to next state
        │
        └──► No transition ──► Check default transition
                               │
                               ├──► Default found ──► Move to next state
                               └──► No default ──► Terminate FSM
```

## Content/Ontology Decisions

### Decision: Content Encoding Selection

**Location**: `jade.content.ContentManager`

```
Content to encode
        │
        ▼
Determine content type:
        │
        ├──► ContentElement ──► Use registered Codec
        ├──► String ──► Use StringCodec
        └──► byte[] ──► Use ByteArrayCodec
        │
        ▼
Ontology registered for type?
        │
        ├──► YES ──► Apply ontology mapping
        └──► NO  ──► Use raw encoding
        │
        ▼
Encode using Codec
```

### Decision: Content Decoding

**Location**: `jade.content.ContentManager`

```
Encoded string received
        │
        ▼
Determine encoding language
        │
        ▼
Codec registered for language?
        │
        ├──► YES ──► Use registered codec
        └──► NO  ──► Exception
        │
        ▼
Decode to AbsObject
        │
        ▼
Ontology registered?
        │
        ├──► YES ──► Map to concrete type
        └──► NO  ──► Return AbsObject
```

## Container Decisions

### Decision: Main vs. Peripheral Container

**Location**: `jade.core.Profile`

```
Profile.MAIN property?
        │
        ├──► true ──► Create MainContainerImpl
        │              │
        │              ▼
        │         Initialize ServiceManager
        │              │
        │              ▼
        │         Start AMS
        │              │
        │              ▼
        │         Start DF
        │
        └──► false ──► Create AgentContainerImpl
                        │
                        ▼
                   Connect via IMTP
                        │
                        ▼
                   Register with main container
```

### Decision: IMTP Selection

**Location**: `jade.core.ProfileImpl`

```
Profile.IMTP property?
        │
        ├──► RMI ──► Use RMIIMTPManager
        │
        ├──► LEAP ──► Use LEAPIMTPManager
        │             │
        │             ▼
        │        Protocol from profile:
        │             │
        │             ├──► JICP ──► JICP connections
        │             ├──► HTTP ──► HTTP connections
        │             └──► HTTPS ─► SSL connections
        │
        └──► Default ──► Use LEAP with JICP
```

---

*See [Business Logic](./business-logic.md) for business rules and [Error Handling](./error-handling.md) for exception handling.*
