> ⚠️ **Early Access**: Behavior documentation is in early access. Please review critically.

# Business Logic — JADE 4.6.0

## Core Agent Business Logic

### Agent Initialization (jade.core.Agent)

Every JADE agent extends `jade.core.Agent`. The business logic is defined in `setup()` and `takeDown()`.

**jade.core.Agent.setup() — Agent Initialization Pattern**

Rules for user-defined agents:
- Register services via `getHelper()`
- Create initial behaviours via `addBehaviour()`
- Register with DF via `DFService.register()` if providing services
- Initialize state from constructor arguments

```java
protected void setup() {
    // Get arguments passed at creation
    Object[] args = getArguments();
    
    // Get services
    ServiceHelper helper = getHelper(Service.SERVICE_NAME);
    
    // Register with DF
    DFAgentDescription dfd = new DFAgentDescription();
    dfd.setName(getAID());
    ServiceDescription sd = new ServiceDescription();
    // ... configure and register
    
    // Add behaviours
    addBehaviour(new CyclicBehaviour() { ... });
}
```

### Agent Message Processing (jade.core.Agent.receive)

Business rule: Agents process ACL messages asynchronously via behaviours. The `receive()` method with `block()` pattern:

```java
// Rule: Agents should NOT poll in busy loops
// Correct: block() when no message available
addBehaviour(new CyclicBehaviour() {
    public void action() {
        ACLMessage msg = myAgent.receive(MessageTemplate.MatchPerformative(ACLMessage.INFORM));
        if (msg != null) {
            // Process message
        } else {
            block(); // Wait for message
        }
    }
});
```

### Agent Termination (jade.core.Agent.takeDown)

Business rules for cleanup:
- Deregister from DF before termination
- Clean up resources (files, connections)
- Remove from groups/containers

## Directory Facilitator Business Rules (jade.domain.df)

### DF Registration Rules

**jade.domain.df — Service Registration Rules**

1. **Unique Service Name**: Each service description within an agent must have a unique name
2. **Service Type**: Service type is used for categorization, not enforced uniqueness
3. **Language Constraints**: Language must be an ISO standard language code
4. **Ownership**: Owner identifies who registered the service

```java
// Rule: One agent can register multiple services
DFAgentDescription dfd = new DFAgentDescription();
dfd.setName(getAID());
dfd.setOwnership("seller-company");

// Rule: Multiple services per description
ServiceDescription sd1 = new ServiceDescription();
sd1.setName("book-selling");
sd1.setType("trading");

ServiceDescription sd2 = new ServiceDescription();
sd2.setName("book-bidding");
sd2.setType("trading");

dfd.addServices(sd1);
dfd.addServices(sd2);
```

### DF Search Rules

**jade.domain.df — Search Rules**

1. **Wildcard Search**: Use `null` for fields you want to match any value
2. **Fuzzy Matching**: By default, search uses substring matching for text fields
3. **Multi-Constraint**: All non-null constraints must match
4. **Pagination**: `SearchConstraints.max-results` limits results

```java
// Rule: Null in any field = wildcard for that field
DFAgentDescription template = new DFAgentDescription();
ServiceDescription sd = new ServiceDescription();
sd.setType("trading"); // Only match type, ignore name
template.addServices(sd);
// Rule: Name is wildcard, ownership is wildcard
```

## AMS Business Rules (jade.domain.ams)

### AMS Agent Lifecycle Rules

**jade.domain.ams — Agent State Transitions**

1. **Registered**: Agent exists on platform (initial state)
2. **Active**: Agent is running and processing
3. **Suspended**: Agent is paused, queue preserved
4. **Waiting**: Agent is blocked waiting for message
5. **Deleted**: Agent has been removed

State transitions controlled by AMS:
- create → registered
- start → active
- suspend → suspended
- resume → active
- kill → deleted

### AMS Lifecycle Actions

```java
// Rule: AMS manages platform-wide agent lifecycle
// Agents can request their own lifecycle changes
public void doKill() {
    // Sends KILL_AGENT to AMS
}

public void doSuspend() {
    // Sends SUSPEND_AGENT to AMS
}

public void doResume() {
    // Sends RESUME_AGENT to AMS
}
```

## FIPA Protocol Business Rules

### Contract Net Protocol Rules (jade.proto.ContractNetInitiator)

**jade.proto.ContractNetInitiator — Business Rules**

1. **CFP Must Have Content**: The call-for-proposal must have a defined content
2. **Deadline**: Use `setReplyByDate()` to set a deadline
3. **All Responses Mode**: By default, waits for all responses before processing
4. **Best Proposal Selection**: Application logic determines which proposal to accept

```java
// Rule: ContractNet is for multi-party negotiation
ACLMessage cfp = new ACLMessage(ACLMessage.CFP);
cfp.addReceiver(participantAID);
cfp.setContentObject(procurementRequest);
cfp.setReplyByDate(new Date(System.currentTimeMillis() + 60000));
// Rule: Multiple participants invited to bid
```

### Request Protocol Rules (jade.proto.AchieveREInitiator)

**jade.proto.AchieveREInitiator — Business Rules**

1. **Single Target**: Request protocol is for single-agent requests
2. **Failure Handling**: Must handle FAILURE responses
3. **Timeout**: Set deadline for responses

### Subscription Protocol Rules (jade.proto.SubscriptionResponder)

**jade.proto.SubscriptionResponder — Business Rules**

1. **Persistent Subscription**: Subscription remains active until explicitly cancelled
2. **Notification on Change**: Inform is sent only when subscribed data changes
3. **Agreement Required**: Agent must agree to subscription before receiving informs

## Content/Ontology Business Rules

### Ontology Usage Rules (jade.content.onto)

**jade.content.onto.Ontology — Content Encoding Rules**

1. **Ontology Registration**: Both sender and receiver must register the same ontology
2. **Language Registration**: SLCodec must be registered for SL-based ontologies
3. **ContentElement vs AbsObject**: Encode ContentElement objects, decode to AbsObject first, then to concrete type

```java
// Rule: Both parties must have matching ontologies
ContentManager cm = getContentManager();
cm.registerLanguage(new SLCodec(), FIPANames.ContentLanguage.FIPA_SL0);
cm.registerOntology(MyOntology.INSTANCE);

// Rule: Encode before send
cm.fillContent(msg, myAction);
send(msg);

// Rule: Decode after receive
ACLMessage reply = receive();
cm.fillReceiver(reply);
MyAction result = (MyAction) cm.extractContent(reply);
```

## Container Management Rules

### Container Initialization Rules (jade.core.AgentContainerImpl)

**jade.core.AgentContainerImpl — Business Rules**

1. **One Container Per JVM**: Standard deployment model
2. **Main Container Required**: At least one main container per platform
3. **Container Naming**: Each container must have a unique name within the platform

### Agent Creation Rules

```java
// Rule: Agent names must be unique within container
// Rule: Agent class must be on classpath
// Rule: Arguments must be serializable if container is distributed
AgentController ac = container.createNewAgent(
    "unique-agent-name",
    "com.example.MyAgent",
    new Object[] { arg1, arg2 }
);
ac.start();
```

## Security Business Rules (jade.security)

### Authentication Rules

**jade.security — Security Rules**

1. **Principal Required**: Every agent has a principal for identification
2. **Credentials for Actions**: Sensitive actions require credentials
3. **SDSI Naming**: Security Domain/Security Identity for federation

## Exception Handling Rules

### FIPAException Handling (jade.domain.FIPAException)

**jade.domain.FIPAException — Business Rules**

1. **Communication Errors**: FAILURE responses result in FIPAException
2. **Timeout Handling**: Timeout results in FIPAException
3. **Not Understood**: NOT_UNDERSTOOD responses result in FIPAException

```java
try {
    DFService.register(myAgent, dfd);
} catch (FIPAException fe) {
    // Handle communication failure
    // Check ACLMessage performative if wrapping an ACLMessage
}
```

## Message Template Matching Rules (jade.lang.acl.MessageTemplate)

**jade.lang.acl.MessageTemplate — Matching Rules**

1. **AND Combination**: All templates must match
2. **OR Combination**: Any template matching
3. **NOT Combination**: Negates match result
4. **Partial Match**: Template can match subset of message fields

```java
// Rule: AND means all conditions must be met
MessageTemplate mt = MessageTemplate.and(
    MessageTemplate.MatchPerformative(ACLMessage.REQUEST),
    MessageTemplate.MatchProtocol("my-protocol"),
    MessageTemplate.MatchLanguage("SLCodec")
);
```

---

*See [Workflows](./workflows.md) for process flows and [Decision Logic](./decision-logic.md) for decision trees.*
