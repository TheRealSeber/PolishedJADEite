# Dependency Analysis — JADE 4.6.0

## External Dependencies

### Maven Dependency Tree

```
JADE 4.6.0
└── commons-codec:commons-codec:1.3
    └── No transitive dependencies (this version is standalone)
```

### Dependency Details

| Dependency | Version | Purpose | License | Status |
|------------|---------|---------|---------|--------|
| Apache Commons Codec | 1.3 | Encoding/Base64 | Apache 2.0 | EOL, Known CVEs |

### Library Usage Map

**commons-codec-1.3.jar**:
```
jade.imtp.leap.http.HTTPHelper
    └── Base64.encodeBase64()
    └── Base64.decodeBase64()

jade.imtp.leap.Serializer
    └── DigestUtils (indirect)

jade.imtp.leap.http.https.HTTPSTrustManager
    └── Certificate handling
```

## Internal Package Dependencies

### jade.core (Most Central)

```
jade.core
├── jade.util.leap           (100% of files)
├── jade.util                (Logger, Properties)
├── jade.lang.acl            (ACLMessage, MessageTemplate)
├── jade.domain              (AID, Profile)
├── jade.security            (Security helpers)
├── jade.core.behaviours    (All behaviour types)
├── jade.core.mobility      (Mobility helpers)
└── java.util                (Hashtable, Vector, Enumeration)
```

### jade.domain

```
jade.domain
├── jade.core               (Agent, AID, Profile)
├── jade.lang.acl            (ACLMessage, ISO8601)
├── jade.core.behaviours    (Behaviour)
├── jade.content.*          (Ontology, ContentManager)
├── jade.domain.FIPAAgentManagement
├── jade.domain.JADEAgentManagement
└── jade.util.leap
```

### jade.lang.acl

```
jade.lang.acl
├── jade.core               (AID)
├── jade.domain.FIPAAgentManagement (Envelope)
└── jade.util.leap
```

### jade.content.onto

```
jade.content.onto
├── jade.core               (Service helpers)
├── jade.content.abs
├── jade.content.schema
├── jade.content.lang
└── jade.util.leap
```

### jade.proto

```
jade.proto
├── jade.core               (Agent, AID)
├── jade.core.behaviours    (Behaviour)
├── jade.lang.acl            (ACLMessage)
├── jade.content            (ContentManager)
├── jade.domain             (FIPAException)
└── jade.util.leap
```

## Dependency Graph Summary

### Most-Dependent-Upon (Afferent Coupling)

| Package | Dependents | Assessment |
|---------|-----------|------------|
| `jade.core` | 50+ | Central hub |
| `jade.util.leap` | 40+ | Utility hub |
| `jade.lang.acl` | 30+ | Message hub |
| `jade.domain` | 20+ | Domain hub |
| `jade.content.onto` | 15+ | Ontology hub |

### Most-Dependent-On (Efferent Coupling)

| Package | Dependencies | Assessment |
|---------|-------------|------------|
| `jade.core` | High | Depends on many |
| `jade.wrapper` | Medium | Depends on core, domain |
| `jade.tools` | Medium-High | Depends on gui, core |
| `jade.domain` | Medium | Depends on core, content |
| `jade.proto` | Medium | Depends on core, behaviours |

## Circular Dependencies

### Detected Cycles

1. **jade.content.lang ↔ jade.content.onto**
   - Ontology uses Codec
   - Codec may reference Ontology schemas

2. **jade.domain ↔ jade.lang.acl**
   - Envelope references ACL structures
   - ACL may reference domain types

### Impact
Circular dependencies in `jade.content.*` are generally contained and do not propagate to the main `jade.core` package. The core kernel is acyclic.

## Platform-Specific Dependencies

### J2SE Only (MIDP_EXCLUDE_BEGIN)

```java
//#MIDP_EXCLUDE_BEGIN
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import javax.swing.JTree;
//#MIDP_EXCLUDE_END
```

**Affected packages**: jade.core, jade.gui, jade.tools, jade.wrapper

### J2SE Only (DOTNET_EXCLUDE_BEGIN)

```java
//#DOTNET_EXCLUDE_BEGIN
import java.net.NetworkInterface;
import java.net.Inet4Address;
import java.net.Inet6Address;
//#DOTNET_EXCLUDE_END
```

### MIDP Only (MIDP_INCLUDE_BEGIN)

```java
/*#MIDP_INCLUDE_BEGIN
import javax.microedition.midlet.MIDlet;
#MIDP_INCLUDE_END*/
```

**Affected**: jade.core (Agent class)

## Package Stability Assessment

| Package | Stability | Reason |
|---------|-----------|--------|
| `jade.core` | High | Must be stable for all agents |
| `jade.util.leap` | High | Contract fixed by J2ME requirement |
| `jade.lang.acl` | High | FIPA standard |
| `jade.content.onto` | Medium-High | Schema system is stable |
| `jade.domain` | Medium-High | FIPA standard |
| `jade.wrapper` | Medium | External API, backward compat needed |
| `jade.gui` | Medium | Internal tools |
| `jade.tools` | Medium | Tool-specific |

## Key Architectural Dependencies

### Agent ↔ Service Communication

```
Agent
  └── ServiceFinder
        └── Service.getHelper(Agent)
              └── ServiceHelper.init(Agent)
```

### Message Flow

```
Agent.send(ACLMessage)
  └── Scheduler
        └── OutBox
              └── MessagingService
                    └── OutgoingEncodingFilter
                          └── MTP.deliver()
```

### Ontology Encoding

```
Agent
  └── ContentManager
        └── Ontology (fromObject/toObject)
              └── Introspector (Bean/BC/Reflective)
                    └── Codec.encode()/decode()
                          └── ACLMessage content
```

---

*See [Code Metrics](../analysis/code-metrics.md) for additional metrics.*
