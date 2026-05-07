# Data Models — JADE 4.6.0

## Core Data Types

### jade.core.AID — Agent Identifier

Represents a globally unique agent identifier per FIPA specifications.

```java
public class AID implements Comparable, Serializable {
    // Format: localName@hap (Home Agent Platform)
    // Example: "buyer@FIPA-Platform"
    
    private String name;              // Full GUID
    private int hashCode;             // Cached hash
    
    // Addresses for multi-transport
    private List addresses;          // jade.util.leap.List
    
    // Federation support
    private List resolvers;          // jade.util.leap.List
    
    // User-defined properties
    private Properties properties;   // jade.util.leap.Properties
}
```

**Key Methods**:
| Method | Returns | Description |
|--------|---------|-------------|
| `getName()` | String | Full GUID |
| `getLocalName()` | String | Local part only |
| `getHap()` | String | Platform name |
| `isValid()` | boolean | Validates AID structure |
| `addAddresses(String)` | void | Add transport address |
| `getAllAddresses()` | Iterator | All addresses |

---

### jade.core.Location — Mobility Location

```java
public interface Location extends Serializable {
    public String getName();
    public String getAddress();
    public String getProtocol();
}
```

**Implementations**:
- `jade.core.DefaultLocation` — Generic location
- `jade.core.ContainerID` — Container location
- `jade.imtp.leap.JICP.JICPAddress` — JICP address
- `jade.imtp.leap.http.HTTPAddress` — HTTP address

---

### jade.core.ContainerID — Container Identifier

```java
public class ContainerID extends Container implements Serializable {
    private String name;
    private String address;
    private String protocol;
    private String main-container;
}
```

---

## Message Data Types

### jade.lang.acl.ACLMessage — ACL Message

```java
public class ACLMessage implements Cloneable, Serializable {
    // Performative (message intent)
    private int performative;        // INFORM, REQUEST, CFP, etc.
    
    // Parties
    private AID sender;
    private List receivers;           // jade.util.leap.List
    private List replyTo;            // jade.util.leap.List
    
    // Content
    private String content;          // Primary content
    private byte[] byteContent;      // Binary content
    private Object userContent;      // Serializable user content
    
    // Encoding
    private String language;         // Content language (e.g., "SLCodec")
    private String encoding;        // Character encoding
    private String ontology;        // Content ontology
    private String protocol;         // Interaction protocol
    
    // Conversation management
    private String conversationId;
    private String inReplyTo;
    private String replyWith;
    private Date replyBy;            // Reply deadline
    
    // Meta
    private Date creationDate;
    private Properties properties;   // jade.util.leap.Properties
    
    // Envelope
    private Envelope envelope;       // jade.domain.FIPAAgentManagement.Envelope
}
```

**Performative Constants**:
```java
public interface ACLMessage {
    int ACCEPT_PROPOSAL = 20;
    int AGREE = 23;
    int CANCEL = 24;
    int CFP = 0;
    int CONFIRM = 21;
    int DISCONFIRM = 22;
    int FAILURE = 12;
    int INFORM = 6;
    int INFORM_IF = 19;
    int INFORM_REF = 18;
    int NOT_UNDERSTOOD = 14;
    int PROPOSE = 8;
    int QUERY_IF = 15;
    int QUERY_REF = 16;
    int REFUSE = 10;
    int REJECT_PROPOSAL = 11;
    int REQUEST = 1;
    int REQUEST_WHEN = 26;
    int SUBSCRIBE = 17;
    int PROXY = 27;
    int PROPAGATE = 28;
}
```

---

### jade.domain.FIPAAgentManagement.Envelope — ACL Envelope

```java
public class Envelope implements Serializable {
    private String to;                // Recipient IDs
    private String from;              // Sender ID
    private List comments;            // Comments
    private String aclRepresentation;
    private Date payloadLength;
    private String payloadEncoding;
    private Date date;
    private List intendedReceivers;  // AIDs
    private List transportBehaviour;
    private ReceivedObject received;
}
```

---

## Domain Data Models

### DFAgentDescription — Service Registration

```java
public class DFAgentDescription implements Serializable {
    public static final String NAME = "df-agent-description";
    
    private AID name;                // Agent this describes
    private List services;           // jade.util.leap.List of ServiceDescription
    private String ownership;        // Owner name
    private String interactionOntology;
}
```

### ServiceDescription — Individual Service

```java
public class ServiceDescription implements Serializable {
    public static final String NAME = "service-description";
    
    private String name;             // Service name
    private String type;             // Service type
    private List languages;           // jade.util.leap.List
    private List ontologies;         // jade.util.leap.List
    private List protocols;          // jade.util.leap.List
    private List properties;         // jade.util.leap.List of Property
    private String ownership;
}
```

### AMSAgentDescription — Agent Information

```java
public class AMSAgentDescription implements Serializable {
    public static final String NAME = "ams-agent-description";
    
    private AID name;
    private String ownership;
    private String state;            // "active", "suspended", "waiting", "deleted"
    private List addresses;          // Transport addresses
    private List resolvers;         // Federation
}
```

---

## Content Language Data Types

### jade.content.abs.* — Abstract Content Elements

```java
// Base interface
public interface AbsObject extends Serializable {
    String getTypeName();
    void setTypeName(String typeName);
    void set(String slotName, Object value);
    Object get(String slotName);
    Iterator getNames();
}

// Concrete types
public class AbsConcept extends AbsObjectImpl implements Concept {}
public class AbsPredicate extends AbsObjectImpl implements Predicate {}
public class AbsAgentAction extends AbsObjectImpl implements AgentAction {}
public class AbsVariable extends AbsObjectImpl implements Variable {}
public class AbsPrimitive extends AbsObject implements Term {}
public class AbsAggregate extends AbsObjectImpl implements Term {}
public class AbsContentElementList extends AbsObjectImpl 
    implements ContentElementList {}
public class AbsIRE extends AbsObjectImpl implements IRE {}
```

---

## Ontology Schemas

### jade.content.schema.ObjectSchema

```java
public class ObjectSchema implements Serializable {
    private String typeName;
    
    public void add(String slotName, ObjectSchema s);
    public void add(String slotName, ObjectSchema s, int cardMin, int cardMax);
    public void add(String slotName, ObjectSchema s, Object defaultValue);
    public void addFacet(String slotName, Facet f);
    public ObjectSchema getSchema(String slotName);
    public int getCardinalityMin(String slotName);
    public int getCardinalityMax(String slotName);
    public boolean isMandatory(String slotName);
    public ObjectSchema getSuperSchema();
    public boolean isPlural(String slotName);
}
```

**Schema Subtypes**:
| Schema | Type | Content Type |
|--------|------|--------------|
| `ConceptSchema` | Concept | `jade.content.Concept` |
| `PredicateSchema` | Predicate | `jade.content.Predicate` |
| `AgentActionSchema` | Action | `jade.content.AgentAction` |
| `PrimitiveSchema` | Primitive | String, Long, Boolean, etc. |
| `AggregateSchema` | Aggregate | `jade.util.leap.List` |
| `VariableSchema` | Variable | Symbolic variable |

---

## Behaviour Data Types

### jade.core.behaviours.DataStore

```java
public class DataStore implements Serializable {
    private HashMap data = new HashMap();  // java.util.HashMap
    
    public void put(Object key, Object value);
    public Object get(Object key);
    public Object remove(Object key);
    public boolean containsKey(Object key);
    public void clear();
    public Set keySet();
}
```

---

## Service-Related Data Types

### jade.core.ServiceDescriptor

```java
public class ServiceDescriptor implements Serializable {
    private String name;
    private String className;
    private Service service;
    private Properties props;
}
```

### jade.core.GenericCommand — Kernel Command

```java
public class GenericCommand implements Command, Serializable {
    private String name;
    private String destination;
    private Object[] params;
    
    public Object getParamAt(int index);
    public void setParamAt(int index, Object value);
}
```

---

## Wrapper API Data Types

### jade.wrapper.State — Agent/Container State

```java
public interface State {
    public String getName();
    public int getCode();
}

// Agent states
public class AgentState implements State {
    public static final int INIT = 0;
    public static final int WAITING = 1;
    public static final int ACTIVE = 2;
    public static final int SUSPENDED = 3;
    public static final int DELETED = 4;
}

// Platform states
public class PlatformState implements State {
    public static final int INIT = 0;
    public static final int STARTED = 1;
    public static final int SUSPENDED = 2;
    public static final int KILLED = 3;
}
```

### jade.wrapper.PlatformEvent — Platform Events

```java
public class PlatformEvent extends EventObject {
    // Event types
    public static final int DEAD = 0;
    public static final int BORN = 1;
    public static final int SUSPENDED = 2;
    public static final int RESUMED = 3;
    public static final int READY = 4;
    public static final int SHUTDOWN = 5;
    
    public int getType();
    public ContainerController getContainer();
    public AgentController getAgent();
}
```

---

## Introspection Data Types

### jade.domain.introspection.Event — Introspection Events

```java
// Base event
public class Event implements Serializable {
    private long when;
    private String platformName;
}

// Agent lifecycle events
public class BornAgent extends Event {}
public class DeadAgent extends Event {}
public class SuspendedAgent extends Event {}
public class ResumedAgent extends Event {}
public class FrozenAgent extends Event {}
public class ThawedAgent extends Event {}
public class MovedAgent extends Event {}

// Behaviour events
public class AddedBehaviour extends Event {}
public class RemovedBehaviour extends Event {}
public class ChangedBehaviourState extends Event {}

// Message events
public class SentMessage extends Event {}
public class ReceivedMessage extends Event {}
public class PostedMessage extends Event {}
public class RoutedMessage extends Event {}

// Platform events
public class AddedContainer extends Event {}
public class RemovedContainer extends Event {}
public class AddedMTP extends Event {}
public class RemovedMTP extends Event {}
public class PlatformDescription extends Event {}
```

---

## LEAP Collection Types

**Note**: `jade.util.leap.*` types are J2ME-compatible and must NOT be replaced with `java.util.*` equivalents.

| LEAP Type | J2SE Equivalent | Notes |
|-----------|-----------------|-------|
| `jade.util.leap.List` | `java.util.List` | Interface |
| `jade.util.leap.ArrayList` | `java.util.ArrayList` | Implementation |
| `jade.util.leap.LinkedList` | `java.util.LinkedList` | Implementation |
| `jade.util.leap.HashMap` | `java.util.HashMap` | Implementation |
| `jade.util.leap.HashSet` | `java.util.HashSet` | Implementation |
| `jade.util.leap.Map` | `java.util.Map` | Interface |
| `jade.util.leap.Set` | `java.util.Set` | Interface |
| `jade.util.leap.Iterator` | `java.util.Iterator` | Interface |
| `jade.util.leap.Properties` | `java.util.Properties` | Extends java.util |
| `jade.util.leap.Serializable` | `java.io.Serializable` | Interface |
| `jade.util.leap.Comparable` | `java.lang.Comparable` | Interface |

---

## Enumeration Types

### jade.core.AgentState

```java
public class AgentState {
    public static final int INIT = 0;
    public static final int WAITING = 1;
    public static final int ACTIVE = 2;
    public static final int SUSPENDED = 3;
    public static final int DELETED = 4;
    
    public String getName();
    public int getCode();
    public static AgentState getInstance(int code);
}
```

### jade.domain.FIPANames

```java
public class FIPANames {
    public static class InteractionProtocol {
        public static final String FIPA_REQUEST = "fipa-request";
        public static final String FIPA_QUERY = "fipa-query";
        public static final String FIPA_REQUEST_WHEN = "fipa-request-when";
        public static final String FIPA_SUBSCRIBE = "fipa-subscribe";
        public static final String FIPA_CONTRACT_NET = "fipa-contract-net";
        public static final String FIPA_ITERATED_CONTRACT_NET = "fipa-iterated-contract-net";
        public static final String FIPA_PROPOSE = "fipa-propose";
        public static final String FIPA_RECRUIT = "fipa-recruit";
        public static final String FIPA_ENGLISH_AUCTION = "fipa-auction";
        public static final String FIPA_DUTCH_AUCTION = "fipa-dutch-auction";
    }
}
```

---

*See [Program Structure](./program-structure.md) for complete package organization.*
