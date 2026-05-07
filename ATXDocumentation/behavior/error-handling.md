> ⚠️ **Early Access**: Behavior documentation is in early access. Please review critically.

# Error Handling — JADE 4.6.0

## Exception Hierarchy

```
java.lang.Exception
    │
    ├── jade.domain.FIPAException              (FIPA-standard errors)
    │     ├── jade.domain.FIPAException        (base)
    │     ├── RefuseException
    │     ├── NotUnderstoodException
    │     ├── FailureException
    │     └── Unauthorised
    │
    ├── jade.core.ServiceException            (service errors)
    ├── jade.core.ProfileException            (configuration errors)
    ├── jade.core.IMTPException              (IMTP errors)
    ├── jade.core.NotFoundException          (not found)
    ├── jade.core.NameClashException         (name conflicts)
    ├── jade.mtp.MTPException               (MTP errors)
    ├── jade.content.ContentException         (content encoding errors)
    ├── jade.content.onto.OntologyException  (ontology errors)
    │
    └── jade.wrapper.StaleProxyException     (proxy errors)
          └── jade.wrapper.ControllerException
                └── jade.wrapper.O2AException
```

## FIPA Exception Patterns

### jade.domain.FIPAException

Base exception for all FIPA-defined errors. Carries an ACL message.

```java
public class FIPAException extends Exception {
    private ACLMessage msg;
    
    public FIPAException();
    public FIPAException(ACLMessage msg);
    public FIPAException(String s);
    public FIPAException(String s, ACLMessage msg);
    public ACLMessage getACLMessage();
}
```

### Specific FIPA Exceptions

| Exception | FIPA Meaning | Used When |
|-----------|-------------|-----------|
| `RefuseException` | Agent refuses to perform action | Agent cannot/will not perform |
| `NotUnderstoodException` | Cannot understand request | Malformed content |
| `FailureException` | Action failed | Execution error |
| `Unauthorised` | Not authorized | Permission denied |

### Handling FIPA Exceptions

```java
try {
    DFService.register(myAgent, dfd);
} catch (FIPAException fe) {
    ACLMessage reply = fe.getACLMessage();
    if (reply != null) {
        int perf = reply.getPerformative();
        // Handle specific failure
    }
}
```

## Agent Error Handling

### jade.core.Agent.handleFailure()

```java
// Called when agent receives FAILURE performative
protected void handleFailure(ACLMessage failure) {
    AID responder = failure.getSender();
    // Log failure, retry, or compensate
}
```

### jade.core.Agent.handleNotUnderstood()

```java
// Called when agent receives NOT_UNDERSTOOD performative
protected void handleNotUnderstood(ACLMessage notUnderstood) {
    // Message was not understood by receiver
    // Consider resending with clarification
}
```

## Messaging Error Handling

### Delivery Failure

```java
// When MTP fails to deliver
jade.mtp.MTPException
    │
    ├──► Address resolution failed
    ├──► Connection refused
    ├──► Timeout
    └──► Protocol error
```

### Message Queue Errors

```java
// jade.core.InternalMessageQueue
// jade.core.ExtendedMessageQueue

// Exceptions typically wrapped in RuntimeException
// Queue overflow: messages dropped (see Profile settings)
```

## Protocol Error Handling

### Contract Net Error Handling

```java
addBehaviour(new ContractNetInitiator(this, cfp) {
    protected void handleAllResponses(Vector responses, Vector acceptances) {
        for (Object response : responses) {
            ACLMessage msg = (ACLMessage) response;
            if (msg.getPerformative() == ACLMessage.FAILURE) {
                // Handle participant failure
            }
        }
    }
    
    protected void handleFailure(ACLMessage failure) {
        // Some participants failed to respond
    }
    
    protected void handleOutOfSequence(ACLMessage msg) {
        // Unexpected message received
    }
});
```

### Subscription Error Handling

```java
addBehaviour(new SubscriptionResponder(this, subscriptionMsg) {
    protected ACLMessage handleCancel(ACLMessage cancel) {
        // Subscription cancelled
        // Clean up resources
        return null;
    }
    
    protected void handleInform(ACLMessage inform) {
        try {
            // Process update
        } catch (Exception e) {
            // Handle error
        }
    }
});
```

## DF Error Handling

### Registration Errors

```java
try {
    DFService.register(myAgent, dfd);
} catch (FIPAException fe) {
    ACLMessage msg = fe.getACLMessage();
    if (msg.getPerformative() == ACLMessage.FAILURE) {
        // Registration failed
        // Common causes:
        // - Already registered (AlreadyRegistered)
        // - Invalid description
        // - AMS refused
    }
}
```

### Search Errors

```java
try {
    DFAgentDescription[] results = DFService.search(
        myAgent, template, constraints);
} catch (FIPAException fe) {
    // Search failed
}
```

## Service Error Handling

### jade.core.ServiceException

```java
try {
    ServiceHelper helper = myAgent.getHelper("service-name");
} catch (ServiceException se) {
    // Service not found or unavailable
}
```

### Service Lookup Errors

```java
// jade.core.ServiceFinder
Service service = ServiceFinder.find(this, "service-name");
if (service == null) {
    // Service not available
}
```

## Serialization Error Handling

### jade.imtp.leap.Serialization Exceptions

```java
// jade.imtp.leap.LEAPSerializationException
try {
    // Serialize agent state
} catch (LEAPSerializationException e) {
    // Serialization failed
    // Causes:
    // - Non-serializable object
    // - Circular reference
    // - Version mismatch
}
```

### jade.content.ContentException

```java
// jade.content.ContentException
try {
    cm.fillContent(msg, action);
} catch (ContentException e) {
    // Content encoding failed
    // Causes:
    // - Missing ontology
    // - Missing codec
    // - Invalid content structure
}
```

### jade.content.onto.OntologyException

```java
// jade.content.onto.OntologyException
try {
    cm.extractContent(reply);
} catch (OntologyException e) {
    // Ontology mapping failed
    // Causes:
    // - Unknown schema
    // - Type mismatch
    // - Missing required slots
}
```

## Container Error Handling

### jade.wrapper.StaleProxyException

```java
try {
    agentController.kill();
} catch (StaleProxyException e) {
    // Agent/container no longer valid
    // Proxy is stale
}
```

### jade.core.IMTPException

```java
// jade.core.IMTPException
try {
    // Remote call
} catch (IMTPException e) {
    // Inter-container communication failed
    // Causes:
    // - Network error
    // - Container down
    // - Serialization error
}
```

## Logging Error Handling

### jade.util.Logger

```java
import jade.util.Logger;

Logger myLogger = Logger.getMyLogger(getClass().getName());

myLogger.log(Logger.WARNING, "Warning message");
myLogger.log(Logger.SEVERE, "Error message", exception);
myLogger.log(Logger.INFO, "Info message");
```

### Logger Log Levels

| Level | Value | Usage |
|--------|-------|-------|
| SEVERE | 1000 | Critical errors |
| WARNING | 900 | Warnings |
| INFO | 800 | Informational |
| CONFIG | 700 | Configuration |
| FINE | 500 | Debug |
| FINER | 400 | Detailed debug |
| FINEST | 300 | Trace |

## Timeout Handling

### Message Timeout

```java
// Set reply deadline
ACLMessage request = new ACLMessage(ACLMessage.REQUEST);
request.setReplyByDate(new Date(System.currentTimeMillis() + 10000)); // 10s

// Timeout handled by protocol behaviour
// Results in FIPAException with timeout
```

### Behaviour Timeout

```java
// WakerBehaviour for one-time delays
addBehaviour(new WakerBehaviour(this, 5000) {
    protected void onWake() {
        // Execute after 5 seconds
    }
    
    protected void handleElapsedTimeout() {
        // Alternative: called if agent killed before wake
    }
});
```

## Recovery Patterns

### Fault Recovery Service

```java
// jade.core.faultRecovery package
// Provides automatic recovery from:
// - Container crashes
// - Network failures
// - Message delivery failures
```

### Retry Pattern

```java
int maxRetries = 3;
int retryDelay = 1000;

for (int i = 0; i < maxRetries; i++) {
    try {
        DFService.register(myAgent, dfd);
        break; // Success
    } catch (FIPAException e) {
        if (i < maxRetries - 1) {
            Thread.sleep(retryDelay);
        } else {
            throw e;
        }
    }
}
```

---

*See [Workflows](./workflows.md) for process flows and [Business Logic](./business-logic.md) for business rules.*
