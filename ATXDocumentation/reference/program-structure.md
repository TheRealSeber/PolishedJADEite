# Program Structure — JADE 4.6.0

## Package Hierarchy

```
jade
├── core                                    [38 files]
│   ├── Agent.java                          (~2502 lines) — Agent base class
│   ├── Runtime.java                        (~344 lines) — Runtime singleton
│   ├── Profile.java                        (~622 lines) — Configuration abstraction
│   ├── AID.java                            (~562 lines) — Agent identifier
│   ├── Scheduler.java                      — Behaviour scheduler
│   ├── AgentContainerImpl.java             — Container implementation
│   ├── MainContainerImpl.java              — Main container
│   ├── AgentState.java                     — Agent state enum
│   ├── Location.java                       — Mobility location
│   ├── ContainerID.java                    — Container identifier
│   ├── Service.java                        — Service base class
│   ├── BaseService.java                    — Service implementation base
│   ├── CommandProcessor.java               — Command processing
│   ├── Filter.java                         — Message/content filtering
│   ├── Sink.java                           — Command sinking
│   ├── GenericCommand.java                 — Command implementation
│   ├── VerticalCommand.java                — Kernel-bound commands
│   ├── HorizontalCommand.java              — Container-bound commands
│   ├── Node.java                           — Platform node abstraction
│   ├── BackEnd.java                        — BE/FE architecture
│   ├── FrontEnd.java                       — FE container
│   ├── BackEndWrapper.java                 — BE wrapper
│   ├── ServiceDescriptor.java              — Service descriptor
│   ├── ServiceHelper.java                  — Service helper interface
│   ├── ServiceFinder.java                  — Service discovery
│   ├── AgentToolkit.java                   — Kernel operations facade
│   ├── GADT.java                           — Global agent directory
│   ├── LADT.java                           — Local agent directory
│   ├── Command.java                        — Base command
│   ├── CaseInsensitiveString.java          — Case-insensitive string
│   ├── Channel.java                        — Communication channel
│   ├── CallbackInvokator.java              — Callback invocation
│   ├── VersionManager.java                 — Version management
│   ├── BootHelper.java                     — Boot utilities
│   ├── BootProfileImpl.java                — Boot profile
│   ├── Boot.java                           — Boot entry
│   ├── MicroBoot.java                      — LEAP boot
│   ├── MicroRuntime.java                   — LEAP runtime
│   └── [other supporting classes]
│
├── core/behaviours                         [20 files]
│   ├── Behaviour.java                      — Base behaviour (~450 lines)
│   ├── SimpleBehaviour.java                — Single-step behaviour
│   ├── CyclicBehaviour.java                — Infinite loop behaviour
│   ├── OneShotBehaviour.java               — One-time behaviour
│   ├── TickerBehaviour.java                — Periodic behaviour
│   ├── WakerBehaviour.java                 — Delayed behaviour
│   ├── SequentialBehaviour.java            — Sequential composition
│   ├── ParallelBehaviour.java              — Parallel composition
│   ├── FSMBehaviour.java                   — State machine
│   ├── CompositeBehaviour.java             — Composition base
│   ├── SerialBehaviour.java                — Serial composition
│   ├── LoaderBehaviour.java                — Dynamic loading
│   ├── WrapperBehaviour.java               — Behaviour wrapper
│   ├── SenderBehaviour.java                — Message sending
│   ├── ReceiverBehaviour.java              — Message receiving
│   ├── ThreadedBehaviourFactory.java       — Thread factory
│   ├── BehaviourList.java                  — Behaviour collection
│   ├── DataStore.java                      — Behaviour data store
│   ├── BaseInitiator.java                  — Protocol initiator base
│   ├── ActionExecutor.java                 — Action execution
│   └── OutcomeManager.java                 — Outcome management
│
├── core/event                              [15 files]
│   ├── NotificationService.java            — Event notification service
│   ├── NotificationHelper.java             — Notification helper
│   ├── NotificationSlice.java              — Notification slice
│   ├── NotificationProxy.java              — Notification proxy
│   ├── JADEEvent.java                      — Base event
│   ├── AgentEvent.java                     — Agent events
│   ├── ContainerEvent.java                 — Container events
│   ├── PlatformEvent.java                  — Platform events
│   ├── MessageEvent.java                   — Message events
│   ├── MTPEvent.java                       — MTP events
│   ├── AgentListener.java                   — Agent listener interface
│   ├── ContainerListener.java              — Container listener interface
│   ├── PlatformListener.java               — Platform listener interface
│   ├── MessageListener.java                — Message listener interface
│   ├── MTPListener.java                    — MTP listener interface
│   └── *Adapter.java                       — Adapter implementations
│
├── core/messaging                          [20+ files]
│   ├── MessagingService.java               — Core messaging
│   ├── MessagingProxy.java                 — Messaging proxy
│   ├── MessagingSlice.java                 — Messaging slice
│   ├── GenericMessage.java                 — Generic message
│   ├── OutBox.java                         — Outgoing message queue
│   ├── OutgoingEncodingFilter.java         — Content encoding
│   ├── IncomingEncodingFilter.java         — Content decoding
│   ├── MOMMessagingService.java            — MOM integration
│   └── [other messaging components]
│
├── core/mobility                           [5 files]
│   ├── AgentMobilityService.java          — Mobility service
│   ├── AgentMobilityHelper.java            — Mobility helper
│   ├── AgentMobilitySlice.java             — Mobility slice
│   ├── AgentMobilityProxy.java             — Mobility proxy
│   └── MobileAgentClassLoader.java          — Class loading
│   └── Movable.java                        — Mobility interface
│
├── core/management                         [10+ files]
│   └── AgentManagementService.java         — Agent lifecycle management
│
├── core/nodeMonitoring                     [5 files]
│   ├── UDPNodeMonitoringService.java       — UDP monitoring
│   ├── UDPMonitorServer.java               — UDP server
│   └── NodeFailureMonitor.java             — Failure detection
│
├── core/replication                        [10+ files]
│   ├── AgentReplicationService.java        — Replication service
│   ├── GlobalReplicationInfo.java          — Replication info
│   └── [replication components]
│
├── core/sam                                [5 files]
│   ├── SAMInfo.java                        — SAM info
│   ├── AverageMeasure.java                 — SAM metrics
│   └── [SAM components]
│
├── core/faultRecovery                      [5 files]
│   └── FaultRecoveryService.java           — Fault recovery
│
├── lang/acl                                [15 files]
│   ├── ACLMessage.java                     (~1322 lines) — ACL message
│   ├── MessageTemplate.java                — Message matching
│   ├── ISO8601.java                        — Date formatting
│   ├── ACLCodec.java                       — Codec interface
│   ├── StringACLCodec.java                 — String encoding
│   ├── LEAPACLCodec.java                   — LEAP encoding
│   ├── ConversationList.java               — Conversation tracking
│   ├── ACLParser.java                      — Generated parser
│   ├── ACLParserTokenManager.java          — Generated token manager
│   ├── ACLParserConstants.java             — Generated constants
│   └── [parser support classes]
│
├── content                                 [25+ files]
│   ├── ContentManager.java                 — Content management
│   ├── ContentElement.java                 — Base content element
│   ├── Term.java                           — FIPA term
│   ├── Concept.java                         — FIPA concept
│   ├── Predicate.java                       — FIPA predicate
│   ├── AgentAction.java                     — FIPA action
│   ├── ContentElementList.java             — Content list
│   ├── ContentException.java               — Content exceptions
│   ├── OntoACLMessage.java                 — Ontology-aware ACL
│   ├── OntoAID.java                        — Ontology-aware AID
│   │
│   ├── abs/                                [20+ files]
│   │   └── AbsObject.java                   — Abstract content objects
│   │
│   ├── lang/
│   │   ├── Codec.java                      — Codec interface
│   │   ├── StringCodec.java                — String codec
│   │   ├── ByteArrayCodec.java             — Binary codec
│   │   ├── sl/                             [30+ files]
│   │   │   ├── SLCodec.java                — SL codec
│   │   │   ├── SLParser.java              — Generated parser
│   │   │   ├── SL0Ontology.java           — SL-0 ontology
│   │   │   ├── SL1Ontology.java           — SL-1 ontology
│   │   │   ├── SL2Ontology.java           — SL-2 ontology
│   │   │   ├── SLOntology.java            — Base SL ontology
│   │   │   └── [vocabulary, parser files]
│   │   └── leap/
│   │       └── LEAPCodec.java              — LEAP codec
│   │
│   ├── onto/
│   │   ├── Ontology.java                  (~1000+ lines) — Base ontology
│   │   ├── BasicOntology.java             (~600+ lines) — Primitive types
│   │   ├── BeanOntology.java              — Bean-based ontology
│   │   ├── BeanOntologyBuilder.java       — Ontology builder
│   │   ├── SerializableOntology.java      — Serializable objects
│   │   ├── MicroIntrospector.java         — MIDP introspector
│   │   ├── ReflectiveIntrospector.java    — Reflection introspector
│   │   ├── Introspectable.java            — Introspection interface
│   │   ├── Introspector.java              — Introspector interface
│   │   ├── ClassDiscover.java             — Class discovery
│   │   ├── OntologyUtils.java              — Utilities
│   │   └── annotations/                    [5 annotation types]
│   │
│   ├── schema/
│   │   ├── ObjectSchema.java               — Schema interface
│   │   ├── ObjectSchemaImpl.java           — Schema implementation
│   │   ├── PrimitiveSchema.java            — Primitive types
│   │   ├── AggregateSchema.java            — Aggregate types
│   │   ├── ConceptSchema.java              — Concept schema
│   │   ├── PredicateSchema.java            — Predicate schema
│   │   ├── AgentActionSchema.java         — Action schema
│   │   ├── TermSchema.java                — Term schema
│   │   ├── IRESchema.java                  — IR expression schema
│   │   ├── ContentElementSchema.java       — Element schema
│   │   ├── ContentElementListSchema.java  — List schema
│   │   ├── ReferenceSchema.java           — Reference schema
│   │   ├── VariableSchema.java            — Variable schema
│   │   └── facets/                         [10 facet types]
│   │
│   └── frame/
│       ├── Frame.java                      — Frame interface
│       ├── QualifiedFrame.java            — Qualified frame
│       ├── OrderedFrame.java              — Ordered frame
│       ├── FrameException.java             — Frame exception
│       └── SLFrameCodec.java               — SL frame codec
│
├── domain                                  [30+ files]
│   ├── ams.java                            (~800 lines) — AMS agent
│   ├── df.java                             (~1200 lines) — DF agent
│   ├── DFService.java                      — DF service
│   ├── DFDBKB.java                         — DF database KB
│   ├── DFHSQLKB.java                       — HSQLDB KB
│   ├── DFMemKB.java                        — In-memory KB
│   ├── DFKBFactory.java                    — KB factory
│   ├── FIPAException.java                  — FIPA exceptions
│   ├── FIPANames.java                      — FIPA constants
│   ├── RequestFIPAServiceBehaviour.java    — FIPA request behaviour
│   ├── AMSJadeAgentManagementBehaviour.java — AMS behaviour
│   ├── DFFipaAgentManagementBehaviour.java — DF FIPA behaviour
│   ├── AMSEventQueueFeeder.java            — AMS event feeder
│   ├── RemoteDFRequester.java              — Remote DF requests
│   ├── KBSubscriptionManager.java          — KB subscriptions
│   │
│   ├── FIPAAgentManagement/                [30+ files]
│   │   ├── FIPAManagementOntology.java    — FIPA ontology
│   │   ├── AMSAgentDescription.java      — AMS description
│   │   ├── DFAgentDescription.java        — DF description
│   │   ├── ServiceDescription.java       — Service description
│   │   ├── APDdescription.java           — AP description
│   │   ├── APService.java               — AP service
│   │   ├── SearchConstraints.java       — Search constraints
│   │   ├── Envelope.java                 — ACL envelope
│   │   ├── Property.java                  — Property
│   │   ├── Search.java                   — Search action
│   │   ├── Register.java                 — Register action
│   │   ├── Deregister.java               — Deregister action
│   │   ├── Modify.java                   — Modify action
│   │   ├── GetDescription.java           — Get description
│   │   └── [exception types, vocabulary]
│   │
│   ├── JADEAgentManagement/                [15+ files]
│   │   ├── JADEManagementOntology.java   — JADE ontology
│   │   ├── CreateAgent.java              — Create action
│   │   ├── KillAgent.java                — Kill action
│   │   ├── SniffOn.java                  — Sniff on action
│   │   ├── SniffOff.java                 — Sniff off action
│   │   ├── InstallMTP.java               — Install MTP
│   │   ├── UninstallMTP.java            — Uninstall MTP
│   │   └── [other actions]
│   │
│   ├── introspection/                       [25+ files]
│   │   ├── IntrospectionOntology.java     — Introspection ontology
│   │   ├── IntrospectionServer.java       — Introspection server
│   │   ├── AMSSubscriber.java            — AMS subscriber
│   │   ├── PlatformDescription.java       — Platform description
│   │   ├── Event.java                    — Base event
│   │   ├── Occurred.java                 — Occurred event
│   │   ├── EventRecord.java              — Event record
│   │   ├── AddedAgent.java               — Agent added event
│   │   ├── DeadAgent.java                — Agent dead event
│   │   ├── SentMessage.java              — Message sent event
│   │   ├── ReceivedMessage.java         — Message received event
│   │   └── [other event types]
│   │
│   ├── mobility/                            [15+ files]
│   │   ├── MobilityOntology.java         — Mobility ontology
│   │   ├── MoveAction.java               — Move action
│   │   ├── CloneAction.java              — Clone action
│   │   ├── MobileAgentDescription.java   — Agent description
│   │   ├── MobileAgentProfile.java       — Agent profile
│   │   ├── MobileAgentLanguage.java      — Language
│   │   ├── MobileAgentSystem.java        — System
│   │   ├── MobileAgentOS.java            — OS
│   │   ├── Parameter.java                — Parameter
│   │   └── [vocabulary]
│   │
│   ├── DFGUIManagement/                    [15+ files]
│   │   └── [GUI management ontology]
│   │
│   └── KBManagement/                       [5+ files]
│       └── [KB management components]
│
├── proto                                   [25+ files]
│   ├── Initiator.java                     — Protocol initiator base
│   ├── Responder.java                     — Protocol responder base
│   ├── FIPAProtocolNames.java             — Protocol name constants
│   ├── ContractNetInitiator.java         — Contract Net
│   ├── ContractNetResponder.java         — Contract Net responder
│   ├── AchieveREInitiator.java           — Achieve RE
│   ├── AchieveREResponder.java           — Achieve RE responder
│   ├── ProposeInitiator.java             — Propose
│   ├── ProposeResponder.java             — Propose responder
│   ├── SubscriptionInitiator.java        — Subscription
│   ├── SubscriptionResponder.java        — Subscription responder
│   ├── TwoPhInitiator.java               — Two-phase
│   ├── TwoPhResponder.java               — Two-phase responder
│   ├── SimpleAchieveREInitiator.java     — Simple RE
│   ├── SimpleAchieveREResponder.java     — Simple RE responder
│   ├── IteratedAchieveREInitiator.java   — Iterated RE
│   ├── SSIteratedAchieveREResponder.java — Iterated RE responder
│   ├── SSContractNetResponder.java       — SS Contract Net
│   ├── SSResponderDispatcher.java         — SS Dispatcher
│   ├── SSResponder.java                  — SS Responder base
│   ├── TwoPh0Initiator.java              — Phase 0 initiator
│   ├── TwoPh1Initiator.java              — Phase 1 initiator
│   ├── TwoPh2Initiator.java              — Phase 2 initiator
│   └── TwoPhConstants.java               — Phase constants
│   └── proto/states/                      [20+ state implementations]
│
├── mtp                                     [5 files]
│   ├── MTP.java                           — MTP interface
│   ├── MTPDescriptor.java                 — MTP descriptor
│   ├── TransportAddress.java              — Address interface
│   ├── InChannel.java                    — Incoming channel
│   ├── OutChannel.java                   — Outgoing channel
│   ├── MTPException.java                 — MTP exception
│   ├── http/                              [15+ files]
│   │   ├── MessageTransportProtocol.java — HTTP MTP
│   │   ├── HTTPServer.java               — HTTP server
│   │   ├── HTTPAddress.java              — HTTP address
│   │   ├── HTTPIO.java                   — HTTP I/O
│   │   ├── HTTPProtocol.java             — HTTP protocol
│   │   ├── HTTPPeer.java                 — HTTP peer
│   │   ├── HTTPHelper.java               — HTTP helper
│   │   ├── HTTPRequest.java              — HTTP request
│   │   ├── HTTPResponse.java             — HTTP response
│   │   ├── XMLCodec.java                 — XML codec
│   │   ├── BasicFipaDateTime.java       — Date/time
│   │   ├── KeepAlive.java               — Keep-alive
│   │   └── https/                         [5 HTTPS files]
│   └── iop/                                [1 file]
│       └── MessageTransportProtocol.java — IIOP MTP (DEPRECATED)
│
├── imtp                                    [100+ files]
│   ├── rmi/                                [10 files]
│   │   ├── RMIIMTPManager.java            — RMI IMTP
│   │   ├── ServiceManagerRMI.java        — Service manager
│   │   ├── ServiceManagerRMIImpl.java    — Service manager impl
│   │   ├── NodeRMI.java                  — Node RMI
│   │   ├── NodeRMIImpl.java              — Node RMI impl
│   │   └── NodeAdapter.java              — Node adapter
│   │
│   └── leap/                              [90+ files]
│       ├── LEAPIMTPManager.java           — LEAP IMTP manager
│       ├── ICP.java                       — ICP interface
│       ├── Serializer.java               — Serialization
│       ├── StubHelper.java               — Stub helper
│       ├── Stub.java                     — Stub base
│       ├── Skeleton.java                 — Skeleton base
│       ├── NodeStub.java                 — Node stub
│       ├── NodeSkel.java                 — Node skeleton
│       ├── NodeLEAP.java                 — LEAP node
│       ├── BackEndStub.java              — BE stub
│       ├── BackEndSkel.java              — BE skeleton
│       ├── FrontEndStub.java             — FE stub
│       ├── FrontEndSkel.java            — FE skeleton
│       ├── Command.java                 — LEAP command
│       ├── CommandDispatcher.java        — Command dispatch
│       ├── DeliverableDataInputStream.java — Input stream
│       ├── DeliverableDataOutputStream.java — Output stream
│       ├── ConnectionDropped.java        — Connection drop
│       ├── ICPException.java            — ICP exception
│       ├── LEAPSerializationException.java — Serialization exception
│       ├── Dispatcher.java               — Dispatcher interface
│       ├── DispatcherException.java      — Dispatcher exception
│       ├── ICPDispatchException.java    — Dispatch exception
│       ├── TransportProtocol.java       — Transport protocol
│       ├── JICP/                         [25+ files]
│       │   ├── JICPProtocol.java        — JICP protocol
│       │   ├── JICPAddress.java         — JICP address
│       │   ├── JICPServer.java           — JICP server
│       │   ├── JICPClient.java          — JICP client
│       │   ├── JICPConnection.java       — JICP connection
│       │   ├── JICPSConnection.java     — SSL connection
│       │   ├── JICPPeer.java            — JICP peer
│       │   ├── JICPSPeer.java           — SSL peer
│       │   ├── JICPMediator.java        — JICP mediator
│       │   ├── JICPMediatorManager.java — Mediator manager
│       │   ├── Connection.java          — Connection
│       │   ├── ConnectionPool.java     — Connection pool
│       │   ├── ConnectionFactory.java  — Connection factory
│       │   ├── ConnectionWrapper.java  — Connection wrapper
│       │   ├── ProtocolManager.java    — Protocol manager
│       │   ├── PDPContextManager.java  — PDP context
│       │   ├── NATUtils.java           — NAT utilities
│       │   ├── JICPCompressor.java     — Compression
│       │   ├── BIFEDispatcher.java     — BE/FE dispatcher
│       │   ├── BIBEDispatcher.java     — BE/BI dispatcher
│       │   ├── BIFESDispatcher.java    — BI/FE dispatcher
│       │   └── MaskableJICPPeer.java   — Maskable peer
│       ├── nio/                          [20+ files]
│       │   ├── NIOMediator.java        — NIO mediator
│       │   ├── NIOJICPConnection.java  — NIO connection
│       │   ├── NIOJICPSConnection.java — NIO SSL
│       │   ├── NIOJICPPeer.java        — NIO peer
│       │   ├── NIOJICPSPeer.java       — NIO SSL peer
│       │   ├── NIOHTTPSConnection.java — NIO HTTPS
│       │   ├── NIOHTTPSPeer.java       — NIO HTTPS peer
│       │   ├── NIOHTTPPeer.java        — NIO HTTP peer
│       │   ├── NIOHTTPHelper.java      — NIO HTTP helper
│       │   ├── SSLEngineHelper.java    — SSL helper
│       │   ├── PacketIncompleteException.java — Packet exception
│       │   ├── StuckSimulator.java     — Testing utility
│       │   └── BEManagementService.java — BE management
│       ├── http/                         [15+ files]
│       │   ├── HTTPProtocol.java       — HTTP protocol
│       │   ├── HTTPSProtocol.java      — HTTPS protocol
│       │   ├── HTTPPeer.java           — HTTP peer
│       │   ├── HTTPSPeer.java          — HTTPS peer
│       │   ├── HTTPAddress.java        — HTTP address
│       │   ├── HTTPSAddress.java       — HTTPS address
│       │   ├── HTTPHelper.java         — HTTP helper
│       │   ├── HTTPIO.java             — HTTP I/O
│       │   ├── HTTPPacket.java         — HTTP packet
│       │   ├── HTTPRequest.java        — HTTP request
│       │   ├── HTTPResponse.java       — HTTP response
│       │   ├── HTTPFESDispatcher.java  — FE dispatcher
│       │   ├── HTTPFEDispatcher.java  — FE dispatcher
│       │   ├── HTTPBEDispatcher.java   — BE dispatcher
│       │   ├── HTTPServerConnection.java — Server connection
│       │   └── HTTPClientConnection.java — Client connection
│       └── sms/                          [5 files]
│           ├── SMSManager.java          — SMS manager
│           ├── PhoneBasedSMSManager.java — Phone SMS
│           ├── SMSBEDispatcher.java     — BE dispatcher
│           └── Boot.java                — SMS boot
│
├── wrapper                                 [15 files]
│   ├── AgentController.java              — Agent control interface
│   ├── AgentControllerImpl.java         — Agent control impl
│   ├── ContainerController.java         — Container control interface
│   ├── AgentContainer.java              — Container control impl
│   ├── PlatformController.java         — Platform control interface
│   ├── PlatformControllerImpl.java     — Platform control impl
│   ├── ContainerProxy.java             — Container proxy
│   ├── O2AProxy.java                   — O2A proxy
│   ├── State.java                      — State interface
│   ├── StateBase.java                  — State base
│   ├── PlatformState.java              — Platform state
│   ├── AgentState.java                 — Agent state
│   ├── PlatformEvent.java              — Platform event
│   ├── O2AException.java               — O2A exception
│   ├── StaleProxyException.java        — Proxy exception
│   ├── ControllerException.java        — Controller exception
│   └── gateway/
│       ├── JadeGateway.java            — Gateway
│       └── JadeGatewayController.java  — Gateway controller
│
├── gui                                    [35+ files]
│   ├── AgentTree.java                  (~600 lines) — Tree model
│   ├── AgentTreeModel.java             — Tree model impl
│   ├── AgentTreePopupManager.java     — Popup management
│   ├── TreeIconRenderer.java          — Icon renderer
│   ├── TreeHelp.java                   — Help utilities
│   ├── AIDGui.java                    — AID editor
│   ├── AclGui.java                     — ACL editor
│   ├── GuiAgent.java                   — GUI agent
│   ├── GuiEvent.java                   — GUI events
│   ├── GuiProperties.java              — GUI properties
│   ├── VisualAIDList.java              — AID list viewer
│   ├── VisualPropertiesList.java       — Properties viewer
│   ├── VisualServicesList.java        — Services viewer
│   ├── VisualStringList.java          — String list viewer
│   ├── VisualAPServiceList.java       — AP service list
│   ├── SingleProperty.java            — Property editor
│   ├── TimeChooser.java              — Time picker
│   ├── StringDlg.java                — String dialog
│   ├── ConstraintDlg.java             — Constraint dialog
│   ├── ClassSelectionDialog.java     — Class selector
│   ├── JadeLogoButton.java           — Logo button
│   ├── BrowserLauncher.java          — URL launcher
│   ├── MyFilterImage.java            — Image filter
│   ├── UserPropertyGui.java          — User property
│   ├── NodeDescriptor.java           — Node descriptor
│   ├── AboutJadeAction.java           — About action
│   └── help/                          [help files]
│
├── tools                                  [150+ files]
│   ├── rma/                             [40+ files]
│   │   ├── rma.java                    — RMA agent
│   │   ├── MainWindow.java            — Main window
│   │   ├── MainMenu.java              — Menu bar
│   │   ├── MainPanel.java             — Main panel
│   │   ├── ToolBar.java               — Toolbar
│   │   ├── RMAAction.java             — Action base
│   │   ├── FixedAction.java           — Fixed action
│   │   ├── PlatformAction.java       — Platform action
│   │   ├── ContainerAction.java       — Container action
│   │   ├── GenericAction.java         — Generic action
│   │   ├── StartNewAgentAction.java  — Start agent
│   │   ├── KillAction.java           — Kill agent
│   │   ├── FreezeAgentAction.java    — Freeze agent
│   │   ├── ThawAgentAction.java      — Thaw agent
│   │   ├── MoveAgentAction.java      — Move agent
│   │   ├── LoadAgentAction.java      — Load agent
│   │   ├── SaveAgentAction.java      — Save agent
│   │   ├── LoadContainerAction.java  — Load container
│   │   ├── SaveContainerAction.java  — Save container
│   │   ├── SuspendAction.java        — Suspend
│   │   ├── ResumeAction.java         — Resume
│   │   ├── ShutDownAction.java       — Shutdown
│   │   ├── SnifferAction.java        — Sniffer
│   │   ├── IntrospectorAction.java  — Introspector
│   │   ├── LogManagerAgentAction.java — Logging
│   │   ├── DummyAgentAction.java    — Dummy agent
│   │   ├── ManageMTPAction.java     — Manage MTP
│   │   ├── InstallMTPAction.java    — Install MTP
│   │   ├── UninstallMTPAction.java  — Uninstall MTP
│   │   ├── RefreshAMSAgentAction.java — Refresh AMS
│   │   ├── ShowDFGuiAction.java     — Show DF GUI
│   │   ├── ViewAPDescriptionAction.java — View AP
│   │   ├── RegisterRemoteAgentAction.java — Remote reg
│   │   ├── RemoveRemoteAMSAction.java — Remove remote
│   │   ├── CustomAction.java        — Custom action
│   │   ├── RMACustomizer.java      — Customizer
│   │   ├── PopupMenuAgent.java     — Agent popup
│   │   ├── PopupMenuContainer.java — Container popup
│   │   ├── PopupMenuPlatform.java  — Platform popup
│   │   ├── PopupMenuRemotePlatform.java — Remote popup
│   │   ├── PopupMenuFrozenAgent.java — Frozen popup
│   │   ├── PopupMouser.java       — Popup mouse
│   │   ├── StartDialog.java       — Start dialog
│   │   ├── MoveDialog.java        — Move dialog
│   │   ├── PwdDialog.java         — Password dialog
│   │   ├── InstallMTPDialog.java  — Install dialog
│   │   ├── ManageMTPsDialog.java  — Manage dialog
│   │   ├── WindowCloser.java     — Window closer
│   │   ├── TablePanel.java       — Table panel
│   │   ├── ExitAction.java       — Exit action
│   │   └── [images/]
│   │
│   ├── sniffer/                        [40+ files]
│   │   ├── Sniffer.java            — Sniffer agent
│   │   ├── MainWindow.java         — Main window
│   │   ├── MainPanel.java          — Main panel
│   │   ├── MainMenu.java          — Menu bar
│   │   ├── ToolBar.java           — Toolbar
│   │   ├── MMCanvas.java          — Canvas
│   │   ├── PanelCanvas.java       — Panel canvas
│   │   ├── MessageList.java       — Message list
│   │   ├── AgentList.java        — Agent list
│   │   ├── ActionProcessor.java  — Action processor
│   │   ├── SnifferAction.java    — Action
│   │   ├── DoSnifferAction.java  — Do sniffer
│   │   ├── DoNotSnifferAction.java — Don't sniffer
│   │   ├── ViewMessage.java      — View message
│   │   ├── WriteLogFileAction.java — Write log
│   │   ├── DisplayLogFileAction.java — Display log
│   │   ├── WriteMessageListAction.java — Write messages
│   │   ├── ShowOnlyAction.java   — Show only
│   │   ├── ClearCanvasAction.java — Clear canvas
│   │   ├── PopupAgent.java       — Popup agent
│   │   ├── PopupMessage.java     — Popup message
│   │   ├── PopupMouserAgent.java — Mouse agent
│   │   ├── PopupMouserMessage.java — Mouse message
│   │   ├── PopSnifferAgent.java  — Pop agent
│   │   ├── PopShowAgent.java     — Pop show
│   │   ├── PopNoSniffAgent.java  — Pop no sniff
│   │   ├── AgentAction.java      — Agent action
│   │   ├── FixedAction.java      — Fixed action
│   │   ├── AbstractPopup.java     — Abstract popup
│   │   ├── PopMouserAgent.java   — Pop mouse agent
│   │   ├── GuiProperties.java   — Properties
│   │   ├── StartException.java  — Exception
│   │   ├── Message.java         — Message
│   │   ├── AboutBoxAction.java  — About
│   │   ├── ExitAction.java      — Exit
│   │   └── [images/]
│   │
│   ├── introspector/                   [20+ files]
│   │   ├── Introspector.java      — Introspector agent
│   │   └── [GUI components]
│   │
│   ├── dfgui/                          [30+ files]
│   │   ├── DFGUI.java              — DF GUI agent
│   │   └── [GUI components]
│   │
│   ├── testagent/                       [5 files]
│   │   ├── TestAgent.java        — Test agent
│   │   └── [GUI components]
│   │
│   ├── logging/                         [20+ files]
│   │   ├── LoggingAgent.java     — Logging agent
│   │   └── [GUI components]
│   │
│   ├── SocketProxyAgent/                [5 files]
│   │   ├── SocketProxyAgent.java — Socket proxy
│   │   ├── Server.java          — Server
│   │   ├── JadeBridge.java     — JADE bridge
│   │   ├── Connection.java     — Connection
│   │   └── WaitAnswersBehaviour.java — Wait behaviour
│   │
│   ├── applet/                         [5 files]
│   │   └── [Applet components]
│   │
│   ├── ToolAgent.java                  — Base tool agent
│   ├── ToolNotifier.java              — Tool notifications
│   └── sl/
│       └── SLFormatter.java           — SL formatter
│
├── security                               [10 files]
│   ├── Credentials.java               — Credentials
│   ├── JADESecurityException.java     — Exception
│   ├── JADEPrincipal.java             — Principal
│   ├── CredentialsHelper.java        — Credentials helper
│   ├── SDSIName.java                  — SD SI name
│   └── ThreadGroupHttpAuthenticator.java — HTTP auth
│
├── util                                   [35+ files]
│   ├── Logger.java                    — Logging facade
│   ├── Event.java                    — Event system
│   ├── InputQueue.java              — Thread-safe queue
│   ├── Toolkit.java                  — Utilities
│   ├── Callback.java                 — Callback interface
│   ├── ClassFinder.java             — Class discovery
│   ├── ClassFinderListener.java     — Class finder listener
│   ├── ClassFinderFilter.java      — Class finder filter
│   ├── RWLock.java                  — Read-write lock
│   ├── HashCache.java               — Hash cache
│   ├── SynchList.java              — Synchronized list
│   ├── ExtendedProperties.java     — Extended properties
│   ├── PropertiesException.java    — Properties exception
│   ├── WrapperException.java       — Wrapper exception
│   ├── ObjectManager.java          — Object manager
│   ├── PrintStreamSplitter.java   — Stream splitter
│   ├── PerDayFileLogger.java      — Daily logger
│   ├── TransportAddressWrapper.java — Address wrapper
│   ├── AccessControlList.java     — ACL
│   ├── ThreadDumpManager.java    — Thread dump
│   └── leap/                        [20 files]
│       ├── List.java               — List interface
│       ├── ArrayList.java         — Array list impl
│       ├── LinkedList.java        — Linked list impl
│       ├── HashMap.java           — Hash map impl
│       ├── HashSet.java           — Hash set impl
│       ├── SortedSet.java         — Sorted set interface
│       ├── SortedSetImpl.java    — Sorted set impl
│       ├── Map.java              — Map interface
│       ├── Set.java              — Set interface
│       ├── Iterator.java         — Iterator interface
│       ├── EmptyIterator.java    — Empty iterator
│       ├── EnumIterator.java    — Enum iterator
│       ├── Collection.java      — Collection interface
│       ├── Comparable.java      — Comparable interface
│       ├── Properties.java      — Properties
│       ├── RoundList.java       — Round list
│       ├── Serializable.java   — Serializable interface
│       └── LICENSE, RELEASE-NOTES.txt
│
└── [FIPA/]                             [IDL files]
    └── fipa.idl                       — FIPA IDL definitions
```

## Total File Count

| Category | Files | Lines (est.) |
|----------|-------|-------------|
| Core | 38 | ~15,000 |
| Core/Behaviours | 20 | ~8,000 |
| Core/Event | 15 | ~5,000 |
| Core/Messaging | 20+ | ~15,000 |
| Core/Mobility | 6 | ~3,000 |
| Core/Other | 30+ | ~10,000 |
| Lang/ACL | 15 | ~8,000 |
| Content | 100+ | ~50,000 |
| Domain | 100+ | ~40,000 |
| Proto | 25+ | ~15,000 |
| MTP | 20+ | ~10,000 |
| IMTP | 100+ | ~30,000 |
| Wrapper | 15 | ~5,000 |
| GUI | 35+ | ~20,000 |
| Tools | 150+ | ~50,000 |
| Security | 10 | ~3,000 |
| Util | 35 | ~10,000 |
| **Total** | **1,142** | **~220,585** |
