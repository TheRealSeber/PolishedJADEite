# Structural Diagrams — JADE 4.6.0

## Package Structure Diagram

```
jade
│
├── core/                          [Kernel]
│   ├── Agent                       [Base class]
│   ├── Runtime                     [Singleton]
│   ├── Profile                     [Configuration]
│   ├── AID                         [Identifier]
│   ├── Scheduler                   [Behaviour executor]
│   ├── AgentContainer              [Interface]
│   ├── MainContainer               [Interface]
│   ├── Service                     [Base class]
│   ├── ServiceHelper               [Interface]
│   ├── ServiceFinder               [Interface]
│   ├── Command                     [Base class]
│   ├── Sink                        [Interface]
│   ├── Filter                      [Base class]
│   ├── AgentToolkit               [Kernel facade]
│   │
│   ├── behaviours/                [Behaviour hierarchy]
│   │   ├── Behaviour               [Abstract base]
│   │   ├── SimpleBehaviour         [Single-step]
│   │   ├── CyclicBehaviour         [Infinite loop]
│   │   ├── OneShotBehaviour        [One-time]
│   │   ├── TickerBehaviour         [Periodic]
│   │   ├── WakerBehaviour         [Delayed]
│   │   ├── CompositeBehaviour      [Composition base]
│   │   ├── SequentialBehaviour     [Series]
│   │   ├── ParallelBehaviour       [Concurrent]
│   │   ├── FSMBehaviour            [State machine]
│   │   └── LoaderBehaviour        [Dynamic]
│   │
│   ├── event/                     [Event system]
│   ├── messaging/                  [Messaging service]
│   ├── mobility/                   [Mobility service]
│   ├── management/                 [Agent management]
│   ├── nodeMonitoring/              [Failure detection]
│   ├── replication/                [Fault tolerance]
│   ├── faultRecovery/              [Recovery]
│   └── sam/                        [Self-healing]
│
├── lang/                          [Communication]
│   └── acl/
│       ├── ACLMessage              [Message]
│       ├── MessageTemplate         [Matching]
│       └── ISO8601                 [Date format]
│
├── content/                       [Content representation]
│   ├── ContentManager              [Encoding/decoding]
│   ├── abs/                       [Abstract elements]
│   ├── lang/
│   │   ├── Codec                  [Interface]
│   │   └── sl/                    [Semantic Language]
│   ├── onto/                      [Ontology system]
│   │   ├── Ontology               [Base]
│   │   ├── BasicOntology         [Primitives]
│   │   └── BeanOntology          [Bean mapping]
│   ├── schema/                    [Schema system]
│   └── frame/                     [Frame representation]
│
├── domain/                        [FIPA agents]
│   ├── ams                       [Agent Management]
│   ├── df                         [Directory Facilitator]
│   ├── FIPAAgentManagement/       [FIPA ontology]
│   ├── JADEAgentManagement/        [JADE ontology]
│   ├── introspection/             [Introspection]
│   ├── mobility/                  [Mobility ontology]
│   └── DFGUIManagement/           [DF GUI]
│
├── proto/                         [FIPA protocols]
│   ├── Initiator                  [Base]
│   ├── ContractNetInitiator
│   ├── AchieveREInitiator
│   ├── ProposeInitiator
│   ├── SubscriptionInitiator
│   ├── TwoPhInitiator
│   └── states/                   [Protocol states]
│
├── mtp/                           [Message Transport]
│   ├── MTP                        [Interface]
│   ├── http/                      [HTTP MTP]
│   └── iop/                       [IIOP MTP]
│
├── imtp/                          [Inter-container]
│   ├── rmi/                       [RMI IMTP]
│   └── leap/                      [LEAP IMTP]
│       ├── JICP/                  [JICP transport]
│       ├── nio/                   [NIO transport]
│       ├── http/                  [HTTP transport]
│       └── sms/                   [SMS transport]
│
├── wrapper/                       [Embedding API]
│   ├── PlatformController
│   ├── ContainerController
│   ├── AgentController
│   └── gateway/
│
├── gui/                           [GUI components]
│   ├── AgentTree
│   ├── AclGui
│   └── AIDGui
│
├── tools/                         [Admin tools]
│   ├── rma/                       [Remote Monitor]
│   ├── sniffer/                   [Message sniffer]
│   ├── introspector/              [Introspection tool]
│   └── dfgui/                     [DF GUI]
│
├── security/                       [Security]
│   ├── Credentials
│   └── JADEPrincipal
│
└── util/                          [Utilities]
    ├── Logger
    ├── Event
    ├── InputQueue
    └── leap/                      [J2ME collections]
```

## Class Diagram: Agent Core

```
                    ┌─────────────────────┐
                    │  <<interface>>      │
                    │    Runnable         │
                    └─────────┬───────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────┐
│                    jade.core.Agent                   │
│                      <<abstract>>                    │
├──────────────────────────────────────────────────────┤
│ - state : int                                       │
│ - myQueue : MessageQueue                            │
│ - myScheduler : Scheduler                           │
│ - behaviours : List                                │
├──────────────────────────────────────────────────────┤
│ + setup() : void                                    │
│ + takeDown() : void                                │
│ + send(ACLMessage) : void                         │
│ + receive(MessageTemplate) : ACLMessage            │
│ + addBehaviour(Behaviour) : void                    │
│ + removeBehaviour(Behaviour) : boolean              │
│ + doMove(Location) : void                         │
│ + doClone(Location, String) : void                │
│ + doSuspend() : void                              │
│ + doResume() : void                               │
│ + doKill() : void                                 │
│ + getHelper(String) : ServiceHelper               │
└──────────────────────────────────────────────────────┘
         │
         │ extends
         ▼
┌─────────────────────┐
│  jade.domain.ams    │
│   (AMS Agent)       │
└─────────────────────┘

┌─────────────────────┐
│    jade.domain.df   │
│    (DF Agent)       │
└─────────────────────┘

┌─────────────────────┐
│ jade.tools.rma.rma │
│   (RMA Agent)       │
└─────────────────────┘
```

## Class Diagram: Behaviour Hierarchy

```
┌─────────────────────────────────────────────┐
│ jade.core.behaviours.Behaviour              │
│          <<abstract>>                        │
├─────────────────────────────────────────────┤
│ # myAgent : Agent                           │
│ # ds : DataStore                            │
├─────────────────────────────────────────────┤
│ + action() : void                          │
│ + done() : boolean                         │
│ + reset() : void                           │
│ + block() : void                           │
│ + block(long) : void                       │
└──────────────────┬──────────────────────────┘
                   │
       ┌───────────┴───────────┐
       │                       │
       ▼                       ▼
┌──────────────────┐  ┌──────────────────────┐
│ SimpleBehaviour  │  │ CompositeBehaviour  │
│  <<abstract>>   │  │   <<abstract>>      │
├──────────────────┤  ├──────────────────────┤
│                  │  │ + addSubBehaviour() │
│                  │  │ + removeSubBehaviour│
└────────┬─────────┘  └──────────┬─────────┘
         │                         │
    ┌────┴────┐         ┌─────────┼─────────┐
    ▼         ▼         ▼         ▼         ▼
┌───────┐ ┌───────┐ ┌────────┐ ┌────────┐ ┌──────┐
│ Cyclic │ │OneShot│ │Sequen- │ │Parallel │ │ FSM  │
│       │ │      │ │tial    │ │        │ │      │
└───────┘ └───────┘ └────────┘ └────────┘ └──────┘

                    ┌───────────────┐
                    │ TickerBehaviour│
                    └───────────────┘

                    ┌───────────────┐
                    │ WakerBehaviour │
                    └───────────────┘
```

## Class Diagram: Messaging

```
┌─────────────────────────────────────────┐
│ jade.lang.acl.ACLMessage                │
├─────────────────────────────────────────┤
│ - performative : int                    │
│ - sender : AID                          │
│ - receivers : List                      │
│ - content : String                      │
│ - language : String                     │
│ - ontology : String                    │
│ - protocol : String                    │
│ - conversationId : String               │
├─────────────────────────────────────────┤
│ + setPerformative(int) : void           │
│ + getPerformative() : int              │
│ + send(ACLMessage) : void             │
│ + receive(MessageTemplate) : ACLMessage│
└─────────────────────────────────────────┘
         │
         │ uses
         ▼
┌─────────────────────────────────────────┐
│ jade.lang.acl.MessageTemplate           │
├─────────────────────────────────────────┤
│ + match(ACLMessage) : boolean          │
├─────────────────────────────────────────┤
│ + MatchPerformative(int) : Template    │
│ + MatchSender(AID) : Template          │
│ + MatchProtocol(String) : Template     │
│ + and(Template, Template) : Template   │
│ + or(Template, Template) : Template    │
│ + not(Template) : Template             │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ jade.domain.FIPAAgentManagement.Envelope│
├─────────────────────────────────────────┤
│ - to : String                           │
│ - from : String                         │
│ - intendedReceivers : List             │
│ - received : ReceivedObject             │
└─────────────────────────────────────────┘
```

## Class Diagram: Ontology System

```
┌───────────────────────────────────────┐
│ jade.content.onto.Ontology            │
│          <<abstract>>                  │
├───────────────────────────────────────┤
│ - name : String                       │
│ - elements : Hashtable               │
│ - classes : Hashtable                │
├───────────────────────────────────────┤
│ + getName() : String                 │
│ + toObject(AbsObject) : Object      │
│ + fromObject(Object) : AbsObject     │
│ + validate(AbsObject) : void        │
│ + getSchema(String) : ObjectSchema   │
│ + add(ConceptSchema, Class) : void  │
└──────────────────┬────────────────────┘
                   │
         ┌─────────┼─────────┐
         ▼                   ▼
┌──────────────────┐  ┌──────────────────┐
│ BasicOntology    │  │ FIPAManagement   │
│ (singleton)      │  │ Ontology         │
└──────────────────┘  └──────────────────┘

┌───────────────────────────────────────┐
│ jade.content.ContentManager           │
├───────────────────────────────────────┤
│ - ontologies : Map                    │
│ - codecs : Map                       │
├───────────────────────────────────────┤
│ + fillContent(ACLMessage, Element)   │
│ + extractContent(ACLMessage) : Element│
│ + registerLanguage(Codec, String)     │
│ + registerOntology(Ontology)          │
└───────────────────────────────────────┘
```

## Class Diagram: MTP Architecture

```
┌─────────────────────┐     ┌─────────────────────┐
│ jade.mtp.MTP       │     │ jade.mtp.MTPDescriptor│
│ <<interface>>      │     └─────────────────────┘
├─────────────────────┤
│ + init(Properties) │
│ + deliver(msg,addr) │
│ + handle(msg, addr)│
└─────────────────────┘
         ▲
         │ implements
┌────────┴────────┐
│                   │
▼                   ▼
┌──────────────┐  ┌──────────────┐
│ HTTP MTP      │  │ IIOP MTP      │
│ (jade.mtp.http)│  │ (DEPRECATED)  │
└──────────────┘  └──────────────┘

┌───────────────────────────────────────────┐
│ jade.imtp.leap.LEAPIMTPManager           │
│        (Inter-container transport)        │
├───────────────────────────────────────────┤
│ + connect(profile) : void               │
│ + sendCommand(cmd) : void                │
│ + receiveCommand() : Command            │
└───────────────────────────────────────────┘
         │
         ├──► JICP Transport
         ├──► HTTP Transport
         ├──► HTTPS Transport
         └──► NIO Transport
```

## Class Diagram: Container Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     jade.core.Runtime                      │
│                        (singleton)                         │
├─────────────────────────────────────────────────────────────┤
│ + instance() : Runtime                                    │
│ + createMainContainer(Profile) : ContainerController      │
│ + createAgentContainer(Profile) : ContainerController     │
│ + startUp(Profile) : void                                │
│ + shutDown() : void                                      │
└─────────────────────────────────────────────────────────────┘
         │
         │ creates
         ▼
┌─────────────────────┐     ┌─────────────────────┐
│ MainContainerImpl   │────▶│  ServiceManager      │
│                     │     │  (AMS, DF, etc.)    │
└──────────┬──────────┘     └─────────────────────┘
           │
           │ IMTP
           ▼
┌─────────────────────┐
│ AgentContainerImpl   │
│                     │
│ + createAgent()     │
│ + getAgent(name)    │
└──────────┬──────────┘
           │
           │ IMTP
           ▼
┌─────────────────────┐
│ FrontEndContainer    │
│ (LEAP/Mobile)       │
└─────────────────────┘

┌─────────────────────┐
│ BackEndContainer     │
│ (coordinates FE)    │
└─────────────────────┘
```

---

*See [Behavioral Diagrams](../diagrams/behavioral/) for interaction diagrams.*
