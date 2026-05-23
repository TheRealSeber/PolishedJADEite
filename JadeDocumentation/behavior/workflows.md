> ⚠️ **Early Access**: Behavior documentation is in early access. Please review critically.

# Workflows — JADE 4.6.0

## Workflow 1: Agent Lifecycle

### Entry Point: jade.core.Runtime.startUp() / jade.core.Boot.main()

**Primary Class**: `jade.core.Runtime`

```
User launches JADE platform
        │
        ▼
Runtime.instance()
        │
        ├──► Single-Container Mode: startUp(profile)
        │         │
        │         ▼
        │    ProfileImpl created
        │         │
        │         ▼
        │    createMainContainer()
        │         │
        │         ▼
        │    MainContainerImpl created
        │         │
        │         ▼
        │    AMS created and started
        │         │
        │         ▼
        │    DF created and started
        │         │
        │         ▼
        │    Services initialized
        │         │
        │         ▼
        │    Agent instances created
        │         │
        │         ▼
        │    Scheduler started for each agent
        │
        └──► Multi-Container Mode: createAgentContainer(profile)
                  │
                  ▼
             ProfileImpl created
                  │
                  ▼
             AgentContainerImpl created
                  │
                  ▼
             IMTP connection to main container
                  │
                  ▼
             Services initialized (remote)
                  │
                  ▼
             Agent instances created
```

## Workflow 2: Agent Creation and Startup

### Entry Point: jade.wrapper.ContainerController.createNewAgent()

**Primary Class**: `jade.wrapper.AgentControllerImpl`

```
External code calls createNewAgent(nickname, className, args)
        │
        ▼
ContainerController creates AgentControllerImpl
        │
        ▼
Agent instantiated via reflection: Class.forName(className)
        │
        ├──► Default constructor called
        │
        └──► Arguments converted to String[]
                  │
                  ▼
        Agent.setArguments(args)
                  │
                  ▼
        AgentController.start()
                  │
                  ▼
        Agent.start() called
                  │
                  ▼
        Agent.setup() — user-defined initialization
                  │
                  ├──► getArguments() retrieved
                  ├──► DF registration (optional)
                  ├──► Service helpers obtained
                  └──► Initial behaviours added
                  │
                  ▼
        Agent enters ACTIVE state
                  │
                  ▼
        Scheduler begins executing behaviours
```

## Workflow 3: ACL Message Send/Receive

### Entry Point: jade.core.Agent.send() / jade.core.Agent.receive()

```
Agent calls send(ACLMessage)
        │
        ▼
ACLMessage validated (sender set to agent's AID)
        │
        ▼
Message added to Scheduler's message queue
        │
        ▼
[ASYNC] Scheduler processes message queue
        │
        ├──► IF destination is local agent
        │         │
        │         ▼
        │    Message delivered to target agent's queue
        │
        └──► IF destination is remote
                  │
                  ▼
             MessagingService.routeMessage()
                  │
                  ▼
             OutgoingEncodingFilter encodes content
                  │
                  ▼
             MTP.deliver() — HTTP/IIOP/JICP
                  │
                  ▼
             Remote container receives
                  │
                  ▼
             IncomingEncodingFilter decodes
                  │
                  ▼
             Message delivered to local agent

Agent calls receive(MessageTemplate)
        │
        ▼
Scheduler checks message queue
        │
        ├──► IF matching message exists
        │         │
        │         ▼
        │    Message returned to agent
        │
        └──► IF no match
                  │
                  ▼
             Agent blocks (behaviour blocked)
                  │
                  ▼
             [ASYNC] When message arrives
                       │
                       ▼
                  Behaviour unblocked
                       │
                       ▼
                  receive() returns message on next action()
```

## Workflow 4: DF Service Registration and Search

### Entry Point: jade.domain.DFService.register()

**Primary Classes**: `jade.domain.df`, `jade.domain.DFDBKB`

```
Agent calls DFService.register(agent, dfd)
        │
        ▼
DFService sends ACLMessage to local DF agent
        │
        ▼
df.receive() — DF Behaviour
        │
        ▼
DFService.validate(dfd)
        │
        ├──► IF validation fails
        │         │
        │         ▼
        │    FAILURE response sent
        │
        └──► IF validation passes
                  │
                  ▼
             DFDBKB.register(dfd)
                  │
                  ▼
             HSQL database updated (or in-memory)
                  │
                  ▼
             Confirmation sent to requester
```

### DF Search Workflow

```
Agent calls DFService.search(agent, template, constraints)
        │
        ▼
DFService creates subscription message
        │
        ▼
DF receives and processes search request
        │
        ▼
DFDBKB.search(template)
        │
        ▼
Match evaluation:
        │
        ├──► Name match (exact or wildcard)
        ├──► Ownership match
        └──► Service match:
                  ├──► Type match
                  ├──► Language match (subset)
                  ├──► Ontology match (subset)
                  ├──► Protocol match (subset)
                  └──► Properties match
        │
        ▼
Results filtered by SearchConstraints
        │
        ├──► max-results
        ├──► max-depth (federation)
        └──► search-id
        │
        ▼
Results sent back to requester
```

## Workflow 5: FIPA Contract Net Protocol

### Entry Point: jade.proto.ContractNetInitiator

```
Initiator sends CFP to participants
        │
        ▼
Participants receive CFP
        │
        ▼
Participants decide (in behaviours):
        │
        ├──► PROPOSE with proposal
        ├──► REFUSE to not participate
        └──► NOT_UNDERSTOOD if cannot parse
        │
        ▼
Initiator collects all responses
        │
        ▼
Initiator evaluates proposals
        │
        ▼
For each accepted proposal:
        │
        ├──► ACCEPT_PROPOSAL sent
        └──► REJECT_PROPOSAL sent
        │
        ▼
Participants receive acceptances/rejections
        │
        ▼
Accepted participants send INFORM if done
        │
        ▼
Initiator receives INFORMs
        │
        ▼
Contract concluded
```

## Workflow 6: Agent Mobility

### Entry Point: jade.core.Agent.doMove()

**Primary Classes**: `jade.core.mobility.AgentMobilityService`, `jade.imtp.leap.BackEndContainer`

```
Agent calls doMove(destination)
        │
        ▼
AgentMobilityService.handleMove(agent, destination)
        │
        ▼
Source container prepares agent state:
        │
        ├──► Agent state serialized
        ├──► Behaviour state serialized
        ├──► Message queue serialized
        └──► O2A queue serialized
        │
        ▼
Agent state transferred via IMTP:
        │
        ├──► LEAP serialization
        └──► JICP/HTTP transport
        │
        ▼
Destination container:
        │
        ├──► Agent class loaded
        ├──► State deserialized
        └──► Agent resumed
        │
        ▼
Source agent deleted
```

## Workflow 7: Agent Replication

### Entry Point: jade.core.replication.AgentReplicationService

```
Main agent created
        │
        ▼
Replication service creates replica on backup container
        │
        ▼
State synchronization:
        │
        ├──► Initial state copy
        └──► Incremental updates
        │
        ▼
Failure detection (UDP heartbeat)
        │
        ▼
Primary failure detected
        │
        ▼
Replica promoted to primary
        │
        ▼
Clients redirected
```

## Workflow 8: Platform Shutdown

### Entry Point: jade.core.Runtime.shutDown()

```
User/system initiates shutdown
        │
        ▼
PlatformController.kill() or AMS receives shutdown request
        │
        ▼
AMS broadcasts SHUTDOWN_PLATFORM message
        │
        ▼
All agents receive shutdown notification
        │
        ▼
Each agent:
        │
        ├──► takeDown() called
        ├──► DF deregistration
        └──► Resource cleanup
        │
        ▼
Containers stopped
        │
        ▼
IMTP connections closed
        │
        ▼
Runtimes terminated
```

---

*See [Business Logic](./business-logic.md) for business rules and [Error Handling](./error-handling.md) for exception patterns.*
