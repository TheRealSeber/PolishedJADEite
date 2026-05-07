# API Reference — JADE 4.6.0 Key Classes

## jade.core.Agent — Primary Agent API

### Lifecycle Methods

```java
// Called once when agent starts. Override to perform initialization.
protected void setup();

// Called once before agent terminates. Override to perform cleanup.
protected void takeDown();

// Get agent's unique AID
public final AID getAID();

// Get agent name (local part of AID)
public final String getName();

// Get home agent platform name
public final String getHap();
```

### Message Handling

```java
// Send an ACL message
public void send(ACLMessage msg);

// Receive a message matching the template (blocking)
public ACLMessage receive(MessageTemplate template);

// Receive any message (non-blocking, returns null if empty)
public ACLMessage receive();

// Send message and wait for reply
public void receive(MessageTemplate template, long millis, long nanos);
```

### Behaviour Management

```java
// Add a behaviour to the agent's behaviour pool
public void addBehaviour(Behaviour b);

// Remove a behaviour from the pool
public boolean removeBehaviour(Behaviour b);

// Get the currently executing behaviour
public Behaviour getCurrentBehaviour();

// Get all behaviours
public Iterator getAllBehaviours();
```

### Service Access

```java
// Get a service helper by service name
public ServiceHelper getHelper(String serviceName) throws ServiceException;
```

### Agent Lifecycle Control

```java
// Request agent mobility
public void doMove(Location location);
public void doClone(Location location, String newName);

// Lifecycle control (called on self)
public void doSuspend();
public void doResume();
public void doKill();
```

### O2A (Object-to-Agent) Interface

```java
// Put an object into the O2A queue
public void putO2AObject(Object obj, boolean blocking);

// Get an object from the O2A queue
public Object getO2AObject(boolean blocking);

// Get queue length
public int getO2ALength();
```

---

## jade.lang.acl.ACLMessage — Message Construction

### Constructor

```java
// Create with specific performative
public ACLMessage(int performative);

// Create with no performative (deprecated)
public ACLMessage();
```

### Sending a Message

```java
ACLMessage msg = new ACLMessage(ACLMessage.INFORM);
msg.addReceiver(new AID("receiver@platform", AID.ISLOCALNAME));
msg.setContent("Hello, world!");
msg.setLanguage("English");
myAgent.send(msg);
```

### Receiving with Template

```java
// Match by performative
MessageTemplate mt = MessageTemplate.MatchPerformative(ACLMessage.INFORM);

// Match by sender
MessageTemplate mt = MessageTemplate.MatchSender(senderAID);

// Match by conversation ID
MessageTemplate mt = MessageTemplate.MatchConversationId("conv-123");

// Combine with AND
MessageTemplate mt = MessageTemplate.and(
    MessageTemplate.MatchPerformative(ACLMessage.REQUEST),
    MessageTemplate.MatchProtocol(FIPANames.InteractionProtocol.FIPA_REQUEST)
);

// Block waiting for message
ACLMessage reply = myAgent.receive(mt);
if (reply != null) {
    // Process reply
}
```

---

## jade.domain.df — Directory Facilitator

### Registration

```java
// Create description
DFAgentDescription dfd = new DFAgentDescription();
dfd.setName(getAID());

ServiceDescription sd = new ServiceDescription();
sd.setName("book-selling");
sd.setType("book-trading");
sd.addLanguages("English");
sd.addOntologies("book-trading-ontology");
dfd.addServices(sd);

// Register
try {
    DFService.register(myAgent, dfd);
} catch (FIPAException e) {
    // Handle error
}

// Deregister
DFService.deregister(myAgent, dfd);

// Modify
DFService.modify(myAgent, dfd);
```

### Search

```java
// Search for agents
DFAgentDescription template = new DFAgentDescription();
ServiceDescription sd = new ServiceDescription();
sd.setType("book-trading");
template.addServices(sd);

SearchConstraints constraints = new SearchConstraints();
constraints.setMaxResults(new Long(10));

try {
    DFAgentDescription[] results = DFService.search(myAgent, template, constraints);
    for (DFAgentDescription result : results) {
        AID seller = result.getName();
        // ...
    }
} catch (FIPAException e) {
    // Handle error
}
```

---

## jade.proto — FIPA Protocols

### Contract Net Initiator

```java
ACLMessage cfp = new ACLMessage(ACLMessage.CFP);
cfp.addReceiver(sellerAID);
cfp.setContentObject(book);
cfp.setProtocol(FIPANames.InteractionProtocol.FIPA_CONTRACT_NET);
cfp.setReplyByDate(new Date(System.currentTimeMillis() + 10000));

addBehaviour(new ContractNetInitiator(this, cfp) {
    protected void handleAllResponses(Vector responses, Vector acceptances) {
        // Process all proposals
        for (Object response : responses) {
            ACLMessage propose = (ACLMessage) response;
            // Evaluate proposal
            ACLMessage acceptance = new ACLMessage(ACLMessage.ACCEPT_PROPOSAL);
            acceptance.addReceiver(propose.getSender());
            acceptances.add(acceptance);
        }
    }
    
    protected void handleInform(ACLMessage inform) {
        // Contract agreed
    }
});
```

### Subscribe Protocol

```java
DFAgentDescription template = new DFAgentDescription();
// ... configure template

addBehaviour(new SubscriptionResponder(this, 
    DFService.createSubscriptionMessage(getAID(), dfd, template, null)) {
    
    protected ACLMessage handleSubscription(ACLMessage subscription) {
        DFAgentDescription dfd = (DFAgentDescription) 
            getContentManager().extractContent(subscription);
        // Register subscription
        return null; // No response needed
    }
    
    protected void handleInform(ACLMessage inform) {
        DFAgentDescription dfd = (DFAgentDescription) 
            getContentManager().extractContent(inform);
        // Process update
    }
});
```

---

## jade.core.behaviours — Behaviour Classes

### Cyclic Behaviour (Infinite Loop)

```java
addBehaviour(new CyclicBehaviour() {
    public void action() {
        MessageTemplate mt = MessageTemplate.MatchPerformative(ACLMessage.INFORM);
        ACLMessage msg = myAgent.receive(mt);
        if (msg != null) {
            // Process message
        } else {
            block(); // No message, wait
        }
    }
});
```

### One-Shot Behaviour (Single Execution)

```java
addBehaviour(new OneShotBehaviour() {
    public void action() {
        System.out.println("I run once!");
    }
});
```

### Ticker Behaviour (Periodic)

```java
addBehaviour(new TickerBehaviour(myAgent, 1000) { // 1000ms interval
    protected void onTick() {
        System.out.println("Tick at: " + System.currentTimeMillis());
    }
});
```

### Waker Behaviour (Delayed)

```java
addBehaviour(new WakerBehaviour(myAgent, 5000) { // 5 second delay
    protected void onWake() {
        System.out.println("Waking up!");
    }
});
```

### Sequential Behaviour (Ordered)

```java
SequentialBehaviour seq = new SequentialBehaviour();
seq.addSubBehaviour(new OneShotBehaviour() { public void action() { /* step 1 */ } });
seq.addSubBehaviour(new OneShotBehaviour() { public void action() { /* step 2 */ } });
seq.addSubBehaviour(new OneShotBehaviour() { public void action() { /* step 3 */ } });
addBehaviour(seq);
```

### Parallel Behaviour (Concurrent)

```java
ParallelBehaviour par = new ParallelBehaviour(ParallelBehaviour.WHEN_ANY);
par.addSubBehaviour(new CyclicBehaviour() { public void action() { /* task 1 */ } });
par.addSubBehaviour(new CyclicBehaviour() { public void action() { /* task 2 */ } });
addBehaviour(par);
```

### FSM Behaviour (State Machine)

```java
FSMBehaviour fsm = new FSMBehaviour();

fsm.registerFirstState(new OneShotBehaviour() {
    public int onEnd() { return 1; } // Transition to state 2
}, "STATE1");

fsm.registerLastState(new OneShotBehaviour() {
    public void action() { /* final state */ }
}, "STATE2");

fsm.registerTransition("STATE1", "STATE2", 1);
addBehaviour(fsm);
```

---

## jade.content.onto — Ontology System

### Defining an Ontology

```java
public class BookTradingOntology extends Ontology {
    public static final String NAME = "book-trading";
    public static final BookTradingOntology INSTANCE = new BookTradingOntology();
    
    private BookTradingOntology() {
        super(NAME, new Ontology[]{BasicOntology.INSTANCE, SerializableOntology.INSTANCE});
        
        // Register concepts
        add(new ConceptSchema(BUY_BOOK), BuyBook.class);
        add(new ConceptSchema(SELL_BOOK), SellBook.class);
        add(new ConceptSchema(BOOK), Book.class);
    }
}

// Concept class
public class BuyBook implements AgentAction {
    private Book book;
    private AID buyer;
    
    public void setBook(Book b) { book = b; }
    public Book getBook() { return book; }
    public void setBuyer(AID a) { buyer = a; }
    public AID getBuyer() { return buyer; }
}
```

### Using an Ontology

```java
// Encode content
ContentManager cm = getContentManager();
cm.registerLanguage(new SLCodec(), FIPANames.ContentLanguage.FIPA_SL0);
cm.registerOntology(BookTradingOntology.INSTANCE);

ACLMessage msg = new ACLMessage(ACLMessage.REQUEST);
msg.setLanguage(FIPANames.ContentLanguage.FIPA_SL0);
msg.setOntology(BookTradingOntology.NAME);

BuyBook action = new BuyBook();
action.setBook(book);
action.setBuyer(getAID());

cm.fillContent(msg, action); // Encode action into message
send(msg);

// Decode content
ACLMessage reply = receive();
cm.fillReceiver(msg);
BuyBook result = (BuyBook) cm.extractContent(reply);
```

---

## jade.wrapper — Embedding API

### Starting JADE from Java

```java
// Get runtime
Runtime runtime = Runtime.instance();

// Create profile
Profile profile = new ProfileImpl();
profile.setParameter(Profile.MAIN, "true");
profile.setParameter(Profile.HOST, "localhost");
profile.setParameter(Profile.PORT, "1099");

// Create container
ContainerController cc = runtime.createAgentContainer(profile);

// Start platform
PlatformController platform = cc.getPlatformController();
platform.start();

// Create agent
AgentController ac = cc.createNewAgent("buyer", "examples.BookBuyerAgent", args);
ac.start();

// Shutdown
platform.kill();
```

---

*See [Program Structure](./program-structure.md) for complete file listing.*
