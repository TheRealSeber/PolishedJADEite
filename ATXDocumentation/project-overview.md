# Project Overview — JADE 4.6.0

## Project Identity

**JADE** (Java Agent DEvelopment Framework) is an open-source middleware for developing multi-agent systems that fully complies with FIPA (Foundation for Intelligent Physical Agents) specifications. JADE enables the development of distributed agent-based applications through a complete set of abstractions, tools, and services.

| Attribute | Value |
|-----------|-------|
| **Project Name** | JADE — Java Agent DEvelopment Framework |
| **Version** | 4.6.0 |
| **Release Date** | ~2007 (last major release) |
| **License** | GNU Lesser General Public License v2.1 |
| **Language** | Java |
| **Target JDK** | Java 1.5 |
| **Build System** | Apache Ant |
| **Total Source Files** | 1,142 Java files |
| **Total Lines of Code** | ~220,585 lines |

## Repository Context

This repository (`PolishedJADEite`) is a **research project from Warsaw University of Technology** that implements an autonomous agentic pipeline for migrating the JADE framework from Java 1.5 to a modern LTS version. The repository contains:

- **`JADE-4.6.0/`** — Original JADE source (never modified). The canonical source of truth for the baseline.
- **`.claude/skills/`** — Migration skills for stepping-stone Java version jumps (1.5→1.6→...→21).
- **`benchmarks/`** — Evaluation cases and benchmark scripts for measuring migration quality.
- **`ATXDocumentation/`** — This comprehensive documentation generated from static code analysis.

## Technology Stack

### Core Framework
- **Java 1.5** — Target source and target bytecode level
- **Apache Ant** — Build tool (build.xml, build.properties)
- **JavaCC** — Parser generation (for ACL and SL parsers)
- **RMI** — Remote Method Invocation (for IIOP MTP)

### Dependencies
- **Apache Commons Codec 1.3** — Encoding/decoding utilities (sole external runtime dependency)
- **FIPA IDL** — CORBA-based Interface Definition Language for IIOP

### Supported Platforms (Historical)
- **J2SE** — Standard Java
- **PJAVA/CDC** — Personal Java / Connected Device Configuration
- **MIDP** — Mobile Information Device Profile (via LEAP add-on)

## Package Structure

The JADE source tree is organized under `JADE-4.6.0/src/jade/src/jade/` with the following top-level packages:

### Core Kernel
| Package | Description |
|---------|-------------|
| `jade.core` | Core runtime, Agent base class, Runtime singleton, messaging kernel, container management, node abstractions |
| `jade.core.behaviours` | Behaviour hierarchy (sequential, parallel, FSM, cyclic, one-shot, ticker, waker) |
| `jade.core.event` | JADE event system (agent, container, platform, message events) |
| `jade.core.messaging` | Message routing, delivery, encoding filters, MOM integration |
| `jade.core.mobility` | Agent mobility service (movement and cloning) |
| `jade.core.management` | Agent and container lifecycle management |
| `jade.core.nodeMonitoring` | UDP-based node failure detection |
| `jade.core.replication` | Agent replication for fault tolerance |
| `jade.core.sam` | SAM (Self-Healing Agent Middleware) integration |
| `jade.core.faultRecovery` | Fault recovery mechanisms |

### Agent Services & Domain
| Package | Description |
|---------|-------------|
| `jade.domain` | AMS (Agent Management System) and DF (Directory Facilitator) agents |
| `jade.domain.FIPAAgentManagement` | FIPA-standard management ontology |
| `jade.domain.JADEAgentManagement` | JADE-specific management ontology |
| `jade.domain.introspection` | Platform introspection ontology |
| `jade.domain.mobility` | Agent mobility domain ontology |
| `jade.domain.persistence` | Agent persistence services |
| `jade.domain.KBManagement` | Knowledge base management |
| `jade.domain.DFGUIManagement` | DF GUI management ontology |

### Communication & Content
| Package | Description |
|---------|-------------|
| `jade.lang.acl` | ACL message parsing, encoding, MessageTemplate |
| `jade.content` | Content language abstractions (Term, Concept, Predicate, AgentAction) |
| `jade.content.abs` | Abstract content elements |
| `jade.content.lang` | Codec interfaces and implementations (SL, LEAP) |
| `jade.content.onto` | Ontology system (BasicOntology, BeanOntology, annotations) |
| `jade.content.schema` | Schema definitions and facets |
| `jade.content.frame` | Frame-based content representation |

### Protocols
| Package | Description |
|---------|-------------|
| `jade.proto` | FIPA interaction protocols (ContractNet, AchieveRE, Propose, Subscription, TwoPhases) |
| `jade.proto.states` | Protocol state implementations |

### Message Transport
| Package | Description |
|---------|-------------|
| `jade.mtp` | MTP interfaces (generic) |
| `jade.mtp.http` | HTTP MTP implementation |
| `jade.mtp.iiop` | IIOP/CORBA MTP implementation (deprecated in modern Java) |

### Inter-Container Communication
| Package | Description |
|---------|-------------|
| `jade.imtp` | Internal message transport abstraction |
| `jade.imtp.rmi` | RMI-based IMTP (legacy) |
| `jade.imtp.leap` | LEAP IMTP (lightweight, multi-platform) |
| `jade.imtp.leap.JICP` | JADE Inter-Container Protocol |
| `jade.imtp.leap.nio` | NIO-based JICP (non-blocking I/O) |
| `jade.imtp.leap.http` | HTTP transport for LEAP |
| `jade.imtp.leap.sms` | SMS transport (mobile) |

### Utilities
| Package | Description |
|---------|-------------|
| `jade.util` | General utilities (Logger, Event, Toolkit, InputQueue) |
| `jade.util.leap` | LEAP-compatible collections (J2ME bridge, mirrors java.util) |

### GUI & Tools
| Package | Description |
|---------|-------------|
| `jade.gui` | Common GUI components (AIDGui, AclGui, AgentTree) |
| `jade.tools.rma` | Remote Monitoring Agent (RMA) administration GUI |
| `jade.tools.sniffer` | Sniffer tool for message inspection |
| `jade.tools.introspector` | Agent introspection tool |
| `jade.tools.testagent` | Test agent for debugging |
| `jade.tools.dfgui` | DF GUI tool |
| `jade.tools.logging` | Logging management tool |
| `jade.tools.SocketProxyAgent` | Socket-to-JADE bridge |
| `jade.tools.sl` | SL content language formatter |

### Wrapper / API
| Package | Description |
|---------|-------------|
| `jade.wrapper` | External container/controller API for embedding JADE |
| `jade.wrapper.gateway` | Process gateway for Java/non-Java integration |

## FIPA Compliance

JADE implements the following FIPA specifications:

- **FIPA ACL** — Agent Communication Language (ISO 8601 date format, message envelope)
- **FIPA AMS** — Agent Management System (platform administration)
- **FIPA DF** — Directory Facilitator (service discovery and registration)
- **FIPA Interaction Protocols** — Contract Net, Request, Query, Propose, Subscribe, Two-Phase Commit
- **FIPA SL** — Semantic Language (content ontology)

## Key Architectural Characteristics

1. **Container-Based Architecture**: The platform is organized as a set of containers, each hosting multiple agents. A main container coordinates peripheral containers.
2. **Service-Oriented Kernel**: Core functionality (messaging, mobility, security, etc.) is exposed as services through a service finder pattern.
3. **Behaviour-Based Concurrency**: Agents use a behaviour tree model for concurrent task execution.
4. **Multi-Transport Messaging**: Messages can be routed over multiple MTPs (HTTP, IIOP, JICP).
5. **Ontology-Based Content**: Rich content representation through FIPA SL ontologies with Java bean mapping.
6. **Cross-Platform Support**: Originally designed to run on J2SE, J2ME/MIDP, and CDC through the LEAP add-on.

## Analysis Scope

This documentation was generated through comprehensive static analysis of the `JADE-4.6.0/src/jade/src/jade/` source tree, covering:
- All 1,142 Java source files
- Build configuration (build.xml, build.properties)
- Package and class hierarchy
- Dependency relationships
- Deprecated API usage
- Design patterns
- Security implementations

**No compilation, execution, or runtime testing was performed.** All analysis is based on source code inspection.
