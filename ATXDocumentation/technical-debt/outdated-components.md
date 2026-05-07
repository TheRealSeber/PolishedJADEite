# Outdated Components — JADE 4.6.0

## Runtime Environment

### Java 1.5 — End of Life

| Attribute | Value |
|-----------|-------|
| **Current Target** | Java 1.5 |
| **EOL Date** | November 3, 2009 |
| **Last Public Update** | October 2009 |
| **Successor** | Java 6 (December 2009) |
| **Status** | **Critical — No Security Support** |

**Location**: `JADE-4.6.0/src/jade/build.xml` (lines 158-159)
```xml
target="1.5"
source="1.5"
```

**Impact**:
- No security patches available for any known JVM vulnerabilities
- Cannot compile on modern JDKs without modification
- Cannot run on modern JVMs without modification
- No modern language features (generics, enums, foreach, varargs)

**Migration Path**:
```
1.5 → 1.6 → 1.7 → 1.8 → 11 → 17 → 21
```
Each step should be validated with `ant jade` compilation. The `jade-phase0-scanner` skill identifies files needing changes at each step.

---

## CORBA/IIOP Message Transport Protocol

### jade.mtp.iiop Package — Removed in Java 9+

| File | Purpose |
|------|---------|
| `jade.mtp.iiop.MessageTransportProtocol.java` | IIOP MTP implementation |

**Technology**: CORBA/IIOP based on `javax.rmi.CORBA` and `org.omg.CORBA.*` packages.

**Java 9+ Impact**: The `javax.rmi` and `org.omg` packages were removed from Java 9 as part of the modularization (Jigsaw) project. The `jade.mtp.iiop` package will not compile on Java 9 or higher.

**Files That Must Be Excluded for Java 11+**:
- `JADE-4.6.0/src/jade/src/jade/mtp/iiop/MessageTransportProtocol.java`

**Build.xml Reference**: The `ant lib` target creates `iiop.jar` separately from `jade.jar`:
```xml
<!-- iiop.jar creation -->
```

**Migration Actions**:
1. Remove `jade.mtp.iiop` package from source tree for Java 11+
2. Exclude from javadoc generation in build.xml
3. Document HTTP MTP as the recommended alternative
4. Update `dist` target to not include IIOP distribution

---

## External Libraries

### Apache Commons Codec 1.3

| Attribute | Value |
|-----------|-------|
| **Version** | 1.3 |
| **Release Date** | October 2006 |
| **EOL** | Deprecated by Apache |
| **Current Stable** | 1.15+ (as of 2020) |
| **Status** | **Known Vulnerabilities** |

**Location**: `JADE-4.6.0/src/jade/lib/commons-codec/commons-codec-1.3.jar`

**Usage in JADE**:
- `jade.imtp.leap.http.HTTPHelper` — Base64 encoding/decoding
- `jade.imtp.leap.http.HTTPIO` — HTTP message encoding
- `jade.imtp.leap.Serializer` — Object serialization encoding
- `jade.imtp.leap.http.https.HTTPSTrustManager` — Certificate handling

**Known Vulnerabilities** (in 1.3):
- DigestUtils MD5/SHA methods considered weak
- No support for modern encoding needs

**Upgrade Path**:
```xml
<!-- Change in build.xml classpath -->
<!-- FROM: -->
<classpath="lib/commons-codec/commons-codec-1.3.jar"/>
<!-- TO: -->
<classpath="lib/commons-codec/commons-codec-1.15.jar"/>
```

**Verification**: The Commons Codec API is backward compatible for all methods used by JADE (primarily Base64 and DigestUtils). Test compilation with `ant jade` after upgrade.

---

## Build System

### Apache Ant — Still Supported
Apache Ant remains actively maintained. No action required, but consider modernizing the build system to Maven or Gradle for dependency management and IDE integration.

### JavaCC Version
- **Current Target**: Java 1.4 in build.xml (line 129: `jdkversion="1.4"`)
- **Parser Output**: Generated files in `jade.lang.acl` and `jade.content.lang.sl`
- **Action**: No immediate change needed, but rebuild parsers with newer JavaCC for Java 8+ compatibility

---

## Deprecated Language Features

### Raw Collections (No Generics)

**Count**: 122 files with `Hashtable`, raw `ArrayList`, raw `List`, raw `Iterator`, raw `Vector` usage.

**Key Locations**:
| File | Pattern | Count |
|------|---------|-------|
| `jade.core.Agent.java` | Hashtable, ArrayList, List | 5+ |
| `jade.core.MessagingService.java` | Hashtable | 3+ |
| `jade.domain.ams.java` | Hashtable | 5+ |
| `jade.content.onto.Ontology.java` | Hashtable | 3+ |
| `jade.util.Logger.java` | Hashtable | 2+ |

**Migration**:
- Use `jade-1.5-to-1.6-raw-types` skill to add generics
- **EXCEPTION**: `jade.util.leap.*` types must NEVER be parameterized (J2ME compatibility)
- **EXCEPTION**: `java.util.Hashtable` can be replaced with `java.util.HashMap` (already synchronized maps exist in Collections)

---

## Deprecated API Methods

### High-Priority Deprecations

#### jade.proto.ContractNetResponder
**File**: `JADE-4.6.0/src/jade/src/jade/proto/ContractNetResponder.java`

| Line | Deprecated Method | Replacement |
|------|------------------|-------------|
| 104 | `REPLY_KEY` | `jade.proto.FIPAProtocolNames` constants |
| 108 | `ACCEPT_PROPOSAL_KEY` | `jade.proto.FIPAProtocolNames` |
| 114 | `REJECT_PROPOSAL_KEY` | `jade.proto.FIPAProtocolNames` |
| 157 | `handleCfp()` | `handleCfp(L8NPROPOSAL_KEY)` |
| 164 | `handleAcceptProposal()` | `handleAcceptProposal(ACCEPT_PROPOSAL_KEY)` |
| 171 | `registerHandleCfp()` | `registerHandleCfp(L8NPROPOSAL_KEY)` |
| 178 | `registerHandleAcceptProposal()` | `registerHandleAcceptProposal(ACCEPT_PROPOSAL_KEY)` |

**Issue**: These methods are deprecated but the class itself is not. This creates a partially deprecated API.

#### jade.domain.DFService
**File**: `JADE-4.6.0/src/jade/src/jade/domain/DFService.java`

| Line | Deprecated Method | Replacement |
|------|------------------|-------------|
| 524 | Blocking registration methods | `createSubscriptionMessage()` |
| 1104-1165 | `register()`, `deregister()`, `modify()`, `search()` | `createSubscriptionMessage()` + `SubscriptionInitiator` |

**Issue**: 7 methods deprecated with no direct method replacement — only behaviour-based alternatives exist.

#### jade.proto.AchieveREResponder
**File**: `JADE-4.6.0/src/jade/src/jade/proto/AchieveREResponder.java`

| Line | Deprecated Method | Replacement |
|------|------------------|-------------|
| 298 | `handleRequest()` | `handleRequest_()` |
| 340 | `registerHandleRequest()` | `registerHandleRequest_()` |

**Note**: The underscore suffix indicates the non-deprecated version.

#### jade.proto.SubscriptionResponder
**File**: `JADE-4.6.0/src/jade/src/jade/proto/SubscriptionResponder.java`

| Line | Deprecated Method | Replacement |
|------|------------------|-------------|
| 256 | `handleSubscription()` | `handleSubscription_()` |
| 312 | `registerHandleSubscription()` | `registerHandleSubscription_()` |

#### jade.core.behaviours.WakerBehaviour
**File**: `JADE-4.6.0/src/jade/src/jade/core/behaviours/WakerBehaviour.java`

| Line | Deprecated Method | Replacement |
|------|------------------|-------------|
| 147 | `onWake()` | Override `done()` method |

### Low-Priority Deprecations

| File | Deprecated Item | Replacement |
|------|-----------------|-------------|
| `jade.proto.FIPAProtocolNames` | Entire class | `jade.domain.FIPANames.InteractionProtocol` |
| `jade.lang.acl.SimpleCharStream` | CharStream methods | Generated by newer JavaCC |
| `jade.content.lang.sl.SimpleCharStream` | CharStream methods | Generated by newer JavaCC |
| `jade.tools.sniffer.Sniffer` | Properties file | Programmatic configuration |
| `jade.gui.AgentTree` | Tree node creation | `createAgentNode()`, `createContainerNode()` |

---

## Deprecated Package-Wide Items

### jade.util.leap Serializable
**Location**: `jade.util.leap.Serializable`
**Purpose**: J2ME-compatible serialization interface
**Note**: Not deprecated, but note that it coexists with `java.io.Serializable`. This dual-type system is intentional for cross-platform support.

### jade.lang.acl.ACLMessage.setContentObject()
**Location**: `jade.lang.acl.ACLMessage.java` (line 313)
**Note**: Marked deprecated because all ACL messages should have a type. However, the method is still functional.

---

## J2ME/MIDP Support

### LEAP Add-on (Historical)

The `jade.util.leap.*` package exists to provide J2ME-compatible collection and serialization types for MIDP environments where `java.util.*` is not available.

**Critical**: These types must NOT be:
1. Parameterized with generics (would break MIDP compilation)
2. Replaced with `java.util.*` equivalents (would break MIDP)
3. Removed or refactored (maintains J2ME compatibility)

**Detection in Source**:
```java
// MIDP compatible
import jade.util.leap.ArrayList;
import jade.util.leap.Serializable;

// NOT compatible with jade.util.leap
import java.util.ArrayList;
import java.io.Serializable;
```

---

*For remediation guidance, see [Remediation Plan](../technical-debt/remediation-plan.md).*
