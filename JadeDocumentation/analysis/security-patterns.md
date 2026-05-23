# Security Patterns — JADE 4.6.0

## Security Architecture

### jade.security Package

JADE provides a security framework for agent platforms with the following components:

| Class | Purpose |
|-------|---------|
| `jade.security.Credentials` | Agent credentials for authentication |
| `jade.security.JADEPrincipal` | Principal representing an agent |
| `jade.security.CredentialsHelper` | Utility for working with credentials |
| `jade.security.JADESecurityException` | Security-related exceptions |
| `jade.security.SDSIName` | SD-SI (Security Domain/Security Identity) naming |
| `jade.security.ThreadGroupHttpAuthenticator` | HTTP authentication |

## Authentication Patterns

### Agent Principal

```java
// From jade.security.JADEPrincipal
public class JADEPrincipal implements Principal, Serializable {
    private String name;           // Principal name
    private SDSIName sdSIName;     // Security domain identity
    private byte[] digest;         // Principal digest
    
    public String getName();
    public SDSIName getSDSIName();
    public boolean equals(Object o);
    public int hashCode();
}
```

### Credentials

```java
// From jade.security.Credentials
public class Credentials implements Serializable {
    private List principals;       // jade.util.leap.List of JADEPrincipal
    private List associations;    // Security associations
    private long expirationTime;
    
    public void addPrincipal(JADEPrincipal p);
    public List getPrincipals();
    public void setExpirationTime(long time);
}
```

## Message-Level Security

### ACL Message Envelope Security

```java
// ACLMessage has security-related envelope fields:
// - to: Intended recipients
// - from: Sender identity
// - acl-representation: ACL representation standard
// - payload-encoding: Encoding of the payload
```

### Received Object Tracing

```java
// jade.domain.FIPAAgentManagement.ReceivedObject
public class ReceivedObject implements Serializable {
    private String by;           // MTP that received
    private Date receivedDate;  // When received
    private String via;          // Transport mechanism
    private String forwardedBy;  // Forwarding agent
    private Date forwardedDate;  // Forwarding date
}
```

## Transport Security

### HTTPS Support

```java
// jade.imtp.leap.http.https package
jade.imtp.leap.http.https.HTTPSTrustManager
    └── Certificate validation
    
jade.imtp.leap.http.https.HTTPSKeyManager
    └── Key management
    
jade.imtp.leap.http.https.StrongAuthentication
    └── Strong HTTPS auth
    
jade.imtp.leap.http.https.NoAuthentication
    └── No auth option
    
jade.imtp.leap.http.https.FriendListAuthentication
    └── Friend-list based auth
```

### SSL/TLS

```java
// jade.imtp.leap.nio.SSLEngineHelper
// Uses JSSE (Java Secure Socket Extension)
// For encrypted IMTP communication
```

## Access Control

### jade.util.AccessControlList

```java
// jade.util.AccessControlList
public class AccessControlList implements Serializable {
    // Not fully analyzed - appears to be 
    // a basic ACL implementation
}
```

## Security Service

JADE can integrate with a security service for platform-wide security enforcement. The security service provides:

1. **Agent Authentication**: Verifying agent identity
2. **Message Signing**: Signing ACL messages
3. **Message Encryption**: Encrypting message content
4. **Access Control**: Enforcing permissions

## Known Security Considerations

### 1. No Built-in Encryption
JADE does not provide built-in message encryption. For secure communication:
- Use HTTPS MTP (`jade.mtp.http.https`)
- Implement custom encryption in application layer
- Use SSL/TLS for IMTP (available via `nio` package)

### 2. AID Validation
```java
// AID validation is based on string comparison
// No cryptographic verification of AID ownership
// In production, consider:
// - Certificate-based AID verification
// - Platform-level security service
```

### 3. Serialization Security

```java
// jade.imtp.leap.DeliverableDataInputStream
// Uses Java serialization for inter-container communication
// Potential vulnerability if untrusted code runs on platform
```

### 4. Trusted and Untrusted Agents

JADE does not enforce sandboxing between agents on the same container. Agents on the same JVM can:
- Access any Java object in the JVM
- Use reflection to access private fields
- Consume unlimited CPU/memory unless constrained externally

### 5. RMI Security

```java
// jade.imtp.rmi package
// Uses Java RMI for remote communication
// Subject to standard RMI security concerns
// Consider RMI security manager configuration
```

## Secure Deployment Recommendations

1. **Use HTTPS MTP** for inter-platform communication
2. **Enable Java Security Manager** if running untrusted agents
3. **Use container isolation** for agents from different trust domains
4. **Implement application-layer authentication** for agent-to-agent trust
5. **Keep JDK updated** — JADE 4.6.0 targets Java 1.5 which is EOL

## Security Patterns Summary

| Pattern | Location | Status |
|---------|----------|--------|
| Agent Principals | jade.security.* | Basic implementation |
| Credentials | jade.security.* | Basic implementation |
| HTTPS Transport | jade.mtp.http.https | Available |
| SSL IMTP | jade.imtp.leap.nio | Available |
| Access Control Lists | jade.util.AccessControlList | Basic |
| Message Envelopes | jade.domain.FIPAAgentManagement | FIPA standard |

## Dependency Security

### Commons Codec 1.3 Vulnerabilities

The included `commons-codec-1.3.jar` has known vulnerabilities:
- MD5 digest methods are cryptographically weak
- No SHA-256 support in this version

**Recommendation**: Upgrade to `commons-codec-1.15+` for SHA-256 and other modern algorithms.

---

*See [Technical Debt Report](../technical-debt-report.md) for dependency-related issues.*
