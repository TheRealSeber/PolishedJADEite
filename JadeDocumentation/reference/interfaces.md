# Interfaces — JADE 4.6.0

## Public API Interfaces

### Agent Lifecycle & Control

#### jade.core.Agent
```java
public abstract class Agent implements Runnable, Serializable {
    protected void setup();
    protected void takeDown();
    public void start();
    
    // Message handling
    public void send(ACLMessage msg);
    public ACLMessage receive(MessageTemplate template);
    public ACLMessage receive();
    
    // Behaviour management
    public void addBehaviour(Behaviour b);
    public void removeBehaviour(Behaviour b);
    public Behaviour getCurrentBehaviour();
    
    // Service access
    public ServiceHelper getHelper(String serviceName);
    
    // Lifecycle
    public AID getAID();
    public String getName();
    public String getHap();
    public void doMove(Location location);
    public void doClone(Location location, String newName);
    public void doSuspend();
    public void doResume();
    public void doKill();
    
    // O2A interface
    public void putO2AObject(Object obj, boolean blocking);
    public Object getO2AObject(boolean blocking);
    public int getO2ALength();
}
```

#### jade.wrapper.AgentController
```java
public interface AgentController {
    public String getName() throws StaleProxyException;
    public void start() throws StaleProxyException;
    public void suspend() throws StaleProxyException;
    public void resume() throws StaleProxyException;
    public void kill() throws StaleProxyException;
    public void move(Location location) throws StaleProxyException;
    public void clone(Location location, String newName) throws StaleProxyException;
    public void addToGroup(String groupName) throws StaleProxyException;
    public void removeFromGroup(String groupName) throws StaleProxyException;
    public void registerO2AInterface(Class interfaceClass);
    public Object getO2AInterface(Class interfaceClass);
    public State getState() throws StaleProxyException;
}
```

#### jade.wrapper.ContainerController
```java
public interface ContainerController {
    public AgentController createNewAgent(String nickname, String className, 
                                          Object[] args) throws StaleProxyException;
    public AgentController getAgent(String localName) throws StaleProxyException;
    public void killContainer() throws StaleProxyException;
    public Location getLocation();
    public String getContainerName();
    public PlatformController getPlatformController();
    public boolean isPrimary();
}
```

#### jade.wrapper.PlatformController
```java
public interface PlatformController {
    public void start() throws StaleProxyException;
    public void suspend() throws StaleProxyException;
    public void resume() throws StaleProxyException;
    public void kill() throws StaleProxyException;
    public ContainerController createAgentContainer(Profile p);
    public ContainerController getContainerController();
    public Location[] getContainerLocations();
    public void addPlatformListener(Listener listener) throws StaleProxyException;
    public void removePlatformListener(Listener listener) throws StaleProxyException;
    public String getPlatformName();
    public String getMasterContainerName();
    public void registerGateway(Listener gateway) throws StaleProxyException;
}
```

---

### Behaviour Interfaces

#### jade.core.behaviours.Behaviour
```java
public abstract class Behaviour implements Serializable {
    public abstract void action();
    public abstract boolean done();
    
    public void reset();
    public void block();
    public void block(long millis);
    public Agent getAgent();
    public void setAgent(Agent a);
    public String getBehaviourName();
    public void setDataStore(DataStore ds);
    public DataStore getDataStore();
}
```

#### jade.core.behaviours.CompositeBehaviour
```java
public abstract class CompositeBehaviour extends Behaviour {
    public void addSubBehaviour(Behaviour b);
    public void removeSubBehaviour(Behaviour b);
    public int getChildrenCount();
    public Enumeration getChildren();
    public Behaviour getCurrentBehaviour();
    protected void scheduleFirst();
    protected void scheduleNext(boolean currentDone);
    protected void scheduleLast();
}
```

#### jade.core.behaviours.FSMBehaviour
```java
public class FSMBehaviour extends CompositeBehaviour {
    public int registerFirstState(Behaviour state, String name);
    public int registerLastState(Behaviour state, String name);
    public int registerState(Behaviour state, String name);
    public void registerDefaultTransition(String from, String to);
    public void registerTransition(String from, String to, int exitCode);
    public void registerDefaultTransition(String from, String to, String[] remainWithin);
    public void deregisterState(String name);
    public Behaviour getState(String name);
    public String getLastTransition();
}
```

---

### Messaging Interfaces

#### jade.lang.acl.ACLMessage
```java
public class ACLMessage implements Cloneable, Serializable {
    // Constructors
    public ACLMessage(int performative);
    public ACLMessage();
    
    // Basic fields
    public void setPerformative(int perf);
    public int getPerformative();
    public void setSender(AID sender);
    public AID getSender();
    public void addReceiver(AID receiver);
    public void clearAllReceiver();
    public List getAllReceiver();
    public void setContent(String content);
    public String getContent();
    
    // Content encoding
    public void setContentObject(Serializable o) throws IOException;
    public Object getContentObject() throws UnreadableException;
    
    // Language, ontology, protocol
    public void setLanguage(String language);
    public String getLanguage();
    public void setOntology(String ontology);
    public String getOntology();
    public void setProtocol(String protocol);
    public String getProtocol();
    public void setConversationId(String id);
    public String getConversationId();
    public void setReplyWith(String replyWith);
    public String getReplyWith();
    public void setInReplyTo(String inReplyTo);
    public String getInReplyTo();
    public void setReplyByDate(Date date);
    public Date getReplyByDate();
    
    // Envelope
    public Envelope getEnvelope();
    public void setEnvelope(Envelope env);
}
```

#### jade.lang.acl.MessageTemplate
```java
public class MessageTemplate {
    public static MessageTemplate MatchPerformative(int perf);
    public static MessageTemplate MatchSender(AID aid);
    public static MessageTemplate MatchReceiver(AID aid);
    public static MessageTemplate MatchContent(String content);
    public static MessageTemplate MatchLanguage(String language);
    public static MessageTemplate MatchOntology(String ontology);
    public static MessageTemplate MatchProtocol(String protocol);
    public static MessageTemplate MatchConversationId(String convId);
    public static MessageTemplate MatchInReplyTo(String replyTo);
    public static MessageTemplate and(MessageTemplate t1, MessageTemplate t2);
    public static MessageTemplate or(MessageTemplate t1, MessageTemplate t2);
    public static MessageTemplate not(MessageTemplate t);
    public static MessageTemplate.MatchExpression newExpression();
    
    public boolean match(ACLMessage msg);
}
```

---

### Content & Ontology Interfaces

#### jade.content.ContentElement
```java
public interface ContentElement extends Serializable {
}
```

#### jade.content.abs.AbsObject
```java
public interface AbsObject extends Serializable {
    public String getTypeName();
    public void setTypeName(String typeName);
    public void set(String slotName, Object value);
    public Object get(String slotName);
    public Iterator getNames();
}
```

#### jade.content.onto.Ontology
```java
public class Ontology implements Serializable {
    public static Ontology getInstance();
    public String getName();
    public Object toObject(AbsObject abs) throws OntologyException;
    public AbsObject fromObject(Object obj) throws OntologyException;
    public void validate(AbsObject abs) throws OntologyException;
    public ObjectSchema getSchema(String typeName);
    public ObjectSchema getSchema(Class clazz);
}
```

#### jade.content.lang.Codec
```java
public interface Codec {
    public void encode(ContentElement content, OutputStream os) throws CodecException;
    public ContentElement decode(String content, Ontology onto) throws CodecException;
    public ContentElement decode(InputStream is, Ontology onto) throws CodecException;
}
```

---

### Service Interfaces

#### jade.core.Service
```java
public abstract class Service implements Service笑lice {
    public abstract String getName();
    public ServiceHelper getHelper(Agent a);
    protected void generateCommand(VerticalCommand cmd);
    
    public interface Slice extends Serializable {
        // Remote interface methods
    }
}
```

#### jade.core.ServiceHelper
```java
public interface ServiceHelper {
    public void init(Agent a);
}
```

#### jade.core.ServiceFinder
```java
public interface ServiceFinder {
    public Service getService(String name);
    public Service[] getServices();
}
```

---

### MTP Interfaces

#### jade.mtp.MTP
```java
public interface MTP {
    public void init(Properties p) throws MTPException;
    public void deliver(ACLMessage msg, String address) throws MTPException;
    public void handle(ACLMessage msg, InChannel.Address a);
    public void reset();
    public MTPDescriptor getDescriptor();
}
```

#### jade.mtp.MTPDescriptor
```java
public class MTPDescriptor implements Serializable {
    public MTPDescriptor(String name, String className, String[] addresses);
    public String getName();
    public String getClassName();
    public String[] getAddresses();
}
```

---

### Protocol Interfaces

#### jade.proto.ProtocolSession
```java
public interface ProtocolSession extends Serializable {
    public String getSessionId();
    public void setSessionId(String id);
    public int getState();
    public Object getDataStore();
    public void setDataStore(DataStore ds);
}
```

---

### Domain Interfaces

#### jade.domain.FIPAAgentManagement.DFAgentDescription
```java
public class DFAgentDescription implements Serializable {
    public static final String NAME = "df-agent-description";
    
    public void setName(AID name);
    public AID getName();
    public void addServices(ServiceDescription sd);
    public void removeService(ServiceDescription sd);
    public void clearAllServices();
    public Iterator getAllServices();
    public void setOwnership(String ownership);
    public String getOwnership();
    public void setInteractionOntology(String ontology);
    public String getInteractionOntology();
}
```

#### jade.domain.FIPAAgentManagement.ServiceDescription
```java
public class ServiceDescription implements Serializable {
    public static final String NAME = "service-description";
    
    public void setName(String name);
    public String getName();
    public void setType(String type);
    public String getType();
    public void addLanguages(String language);
    public void addOntologies(String ontology);
    public void addProtocols(String protocol);
    public void addProperties(Property p);
    public void setOwnership(String ownership);
    public String getOwnership();
}
```

---

## Internal Interfaces

### jade.core.Sink
```java
public interface Sink {
    public void consume(Command cmd);
}
```

### jade.core.Filter
```java
public abstract class Filter extends Sink {
    protected abstract boolean accept(Command cmd);
}
```

### jade.imtp.leap.ICP
```java
public interface ICP {
    public void init(Properties p) throws ICPException;
    public void handleDelivery(DeliverableDataInputStream in) throws ICPException;
    public void handleInvocation(DeliverableDataInputStream in, 
                                 DeliverableDataOutputStream out) throws ICPException;
    public void dispatchCommand(Command cmd);
    public void onC ConnectionDropped(Connection c);
    public String getAddress();
}
```

### jade.util.Listener
```java
public interface Listener {
    public void handleEvent(Event ev);
}
```

---

## Observer/Listenable Interfaces

### jade.core.event.AgentListener
```java
public interface AgentListener extends Listener {
    public void agentAccessed(AgentEvent ev);
    public void agentChangedAgentState(AgentEvent ev);
    public void agentBehaviourAdded(AgentEvent ev);
    public void agentBehaviourRemoved(AgentEvent ev);
    public void agentBehaviourStateChanged(AgentEvent ev);
}
```

### jade.core.event.MessageListener
```java
public interface MessageListener extends Listener {
    public void messageReceived(MessageEvent ev);
    public void messageSent(MessageEvent ev);
}
```

---

*See [API Reference](./api-reference.md) for detailed class documentation and [Data Models](./data-models.md) for data type definitions.*
