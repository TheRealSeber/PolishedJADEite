# Dependencies — JADE 4.6.0

## External Dependencies

### Runtime Dependencies

#### Apache Commons Codec 1.3
- **Location**: `JADE-4.6.0/src/jade/lib/commons-codec/commons-codec-1.3.jar`
- **Purpose**: Used for encoding/decoding in ACL message processing and HTTP MTP
- **Status**: EOL — released October 2006, no longer maintained
- **Vulnerabilities**: Known CVEs present in this version
- **Usage Pattern**: Direct JAR in classpath; referenced in build.xml classpath

**Used In**:
- `jade.imtp.leap.http.HTTPHelper` — Base64 encoding
- `jade.imtp.leap.http.HTTPRequest/Response` — Encoding
- `jade.mtp.http.https.HTTPSTrustManager` — Certificate handling
- `jade.imtp.leap.Serializer` — Serialization encoding
- `jade.imtp.leap.http.HTTPIO` — Message encoding

**Upgrade Path**: Upgrade to `commons-codec 1.15+` (supports Java 8+). The API is backward compatible for the encoding methods used.

---

### Build Dependencies

#### Apache Ant
- **Version**: Any (no specific version constraint)
- **Purpose**: Build system for compilation, JAR creation, documentation generation
- **Status**: Active and maintained

**Targets Used**:
| Target | Purpose |
|--------|---------|
| `ant jade` | Compile JADE source |
| `ant lib` | Create jade.jar and iiop.jar |
| `ant examples` | Compile example agents |
| `ant doc` | Generate Javadoc |
| `ant dist` | Create distribution ZIPs |
| `ant clean` | Clean build artifacts |

#### JavaCC
- **Version**: Any (configured via `JAVACC_HOME` environment variable)
- **Purpose**: Generate parsers from `.jj` grammar files
- **Status**: Active and maintained

**Parser Files**:
| Grammar File | Output Package | Language |
|-------------|----------------|----------|
| `jade/lang/acl/ACLParser.jj` | `jade.lang.acl` | FIPA ACL |
| `jade/content/lang/sl/SLParser.jj` | `jade.content.lang.sl` | SL-0/1/2 |
| `jade/content/lang/sl/ExtendedSLParser.jj` | `jade.content.lang.sl` | Extended SL |

**Build Configuration** (build.xml lines 127-136):
- `javacc jdkversion="1.4"` — Targets Java 1.4 syntax in generated parsers
- Conditional execution based on `rebuildParsers` property

---

## Internal Package Dependencies

### Dependency Graph (Top-Level)

```
jade.core
  ├── jade.util.leap (LEAP collections)
  ├── jade.util (Logger, properties)
  ├── jade.domain (AMS, DF)
  ├── jade.lang.acl (ACL messages)
  └── jade.security

jade.domain
  ├── jade.core
  ├── jade.lang.acl
  ├── jade.core.behaviours
  ├── jade.content.* (onto, lang, abs)
  └── jade.domain.FIPAAgentManagement
       └── jade.domain.JADEAgentManagement

jade.lang.acl
  ├── jade.core (AID)
  └── jade.domain.FIPAAgentManagement (Envelope)

jade.content
  ├── jade.core
  ├── jade.lang.acl
  └── jade.util.leap

jade.proto
  ├── jade.core
  ├── jade.core.behaviours
  ├── jade.lang.acl
  ├── jade.content
  └── jade.domain

jade.mtp
  ├── jade.core
  └── jade.util.leap

jade.imtp
  ├── jade.core
  ├── jade.util
  └── jade.util.leap

jade.gui
  ├── jade.core
  ├── jade.lang.acl
  ├── jade.domain
  └── javax.swing (J2SE only)

jade.tools
  ├── jade.core
  ├── jade.gui
  ├── jade.lang.acl
  ├── jade.domain
  └── jade.content

jade.wrapper
  ├── jade.core
  ├── jade.domain
  ├── jade.lang.acl
  └── jade.content
```

### jade.util.leap — LEAP Collections
**Critical**: This package provides J2ME-compatible collection interfaces that do NOT extend `java.util.*` equivalents. These must NEVER be modified or replaced with `java.util.*` types during migration.

**Classes**:
| Class | Mirrors | Purpose |
|-------|---------|---------|
| `jade.util.leap.List` | java.util.List | J2ME list interface |
| `jade.util.leap.ArrayList` | java.util.ArrayList | J2ME array list |
| `jade.util.leap.LinkedList` | java.util.LinkedList | J2ME linked list |
| `jade.util.leap.HashMap` | java.util.HashMap | J2ME hash map |
| `jade.util.leap.HashSet` | java.util.HashSet | J2ME hash set |
| `jade.util.leap.Map` | java.util.Map | J2ME map interface |
| `jade.util.leap.Set` | java.util.Set | J2ME set interface |
| `jade.util.leap.Iterator` | java.util.Iterator | J2ME iterator |
| `jade.util.leap.Properties` | java.util.Properties | J2ME properties |
| `jade.util.leap.Serializable` | java.io.Serializable | J2ME serializable |

**Detection Rule**: `grep -n "jade\.util\.leap" <file>` — any match indicates LEAP type usage.

### jade.util — General Utilities
**Classes**:
| Class | Purpose |
|-------|---------|
| `Logger` | Platform-wide logging abstraction |
| `Event` | Event/Listener pair pattern |
| `InputQueue` | Thread-safe message queue |
| `Toolkit` | Static utility methods |
| `RWLock` | Read-write lock implementation |
| `HashCache` | Hash-based cache |
| `PerDayFileLogger` | Daily rotating file logger |
| `ClassFinder` | Dynamic class discovery |
| `ExtendedProperties` | Extended properties with circular detection |

---

## Detailed Package-to-Package Dependencies

### jade.core → jade.util.leap
- 100% of jade.core classes use `jade.util.leap.Serializable`
- `Agent.java` uses `ArrayList`, `List`, `HashMap`, `Iterator`, `Properties`
- `AID.java` uses `ArrayList`, `List`, `Iterator`
- `Scheduler.java` uses `List`, `Iterator`
- `CommandProcessor.java` uses `Hashtable` (java.util, synchronized access)

### jade.core → jade.lang.acl
- `Agent.java` imports `jade.lang.acl.ACLMessage`, `MessageTemplate`, `ISO8601`
- `AgentContainerImpl.java` uses ACLMessage for inter-container communication

### jade.domain → jade.core
- `ams.java` extends `Agent`, uses `AID`, `Profile`
- `df.java` extends `Agent`, uses `AID`, `Profile`, `DFDBKB`

### jade.domain → jade.content.onto
- `FIPAAgentManagement.*` classes are ontologies extending `Ontology`
- `JADEManagementOntology.java` extends `Ontology`
- `IntrospectionOntology.java` extends `Ontology`
- `MobilityOntology.java` extends `Ontology`

### jade.lang.acl → jade.domain.FIPAAgentManagement
- `ACLMessage` imports `Envelope` for wrapping messages

### jade.proto → jade.core.behaviours
- All protocol initiator/responder classes extend behaviour base classes
- `Initiator.java` (base) extends `Behaviour`
- `ContractNetInitiator` extends `Initiator`

### jade.mtp.http → jade.util.leap
- HTTP MTP uses `Hashtable` for address-to-service mapping
- Uses `Iterator` for iterating over addresses

### jade.imtp.leap → jade.util.leap + commons-codec
- Serialization uses `Hashtable` in various mediator implementations
- Encoding uses `Base64` from commons-codec

---

## Class Dependency Highlights

### Agent.java — Most Central Class
**Imports**: 60+ classes from across the framework
**Key dependencies**:
- `jade.util.leap.*` — All collection types
- `jade.util.Logger` — Logging
- `jade.core.behaviours.*` — All behaviour types
- `jade.lang.acl.*` — Message handling
- `jade.security.*` — Security helpers
- `jade.core.mobility.*` — Mobility helpers

### MessagingService.java — Message Routing Hub
**Key dependencies**:
- `jade.lang.acl.ACLMessage`
- `jade.core.AID`
- `Hashtable` (java.util) for alias tables
- `jade.imtp.*` for message transport

### Ontology.java — Content Representation
**Key dependencies**:
- `jade.util.leap.Hashtable` (note: jade.util.leap has a HashMap but not Hashtable; this is java.util.Hashtable)
- `jade.content.abs.*` — Abstract content elements
- `jade.content.schema.*` — Schema definitions

---

## API/ABI Dependencies

### Public API Dependencies (jade.wrapper)
The external embedding API (`jade.wrapper.*`) has strict backward compatibility requirements:

| Interface | Stability | Notes |
|-----------|-----------|-------|
| `PlatformController` | High | Must be backward compatible |
| `ContainerController` | High | Must be backward compatible |
| `AgentController` | High | Must be backward compatible |
| `State` | High | Agent/container states |
| `PlatformEvent` | Medium | Event types may evolve |

### Deprecated API Surface
See [Technical Debt Report](../technical-debt-report.md) for complete deprecated API listing.

---

## Version-Specific Dependency Constraints

| Java Version | Constraint | Action |
|-------------|------------|--------|
| 1.5 | Target | Current baseline |
| 1.6 | target=1.5 works | Safe upgrade |
| 1.7 | Diamond operator | Explicit types needed |
| 1.8 | Lambda/stream | Not yet applicable |
| 9+ | CORBA removed | Exclude `jade.mtp.iiop` |
| 11+ | java.desktop modularized | GUI tools need module grants |

---

*See [Dependency Analysis](../analysis/dependency-analysis.md) for detailed internal dependency metrics.*
