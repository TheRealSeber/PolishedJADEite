# MTP Documentation — JADE 4.6.0

## Message Transport Protocols Overview

JADE supports multiple Message Transport Protocols (MTPs) for inter-platform and inter-agent communication.

## HTTP MTP

**Package**: `jade.mtp.http`

### Architecture

```
HTTP MTP
├── HTTPServer — Embedded HTTP server
├── MessageTransportProtocol — Main MTP implementation
├── HTTPAddress — HTTP transport address
├── HTTPProtocol — HTTP protocol handling
├── HTTPHelper — HTTP utilities
├── HTTPIO — Input/Output handling
├── HTTPRequest — HTTP request wrapper
├── HTTPResponse — HTTP response wrapper
├── XMLCodec — XML encoding/decoding for ACL
├── BasicFipaDateTime — FIPA date/time formatting
├── KeepAlive — Connection keep-alive management
└── https/
    ├── HTTPSPeer — HTTPS peer
    ├── HTTPSAddress — HTTPS address
    ├── HTTPSProtocol — HTTPS protocol
    ├── HTTPServerConnection — Server connection
    ├── HTTPClientConnection — Client connection
    ├── HTTPSTrustManager — Trust management
    ├── HTTPSKeyManager — Key management
    ├── StrongAuthentication — Strong auth
    ├── NoAuthentication — No auth option
    └── FriendListAuthentication — Friend-list auth
```

### Configuration

```xml
<!-- In profile properties -->
jade.mtp.http.enabled=true
jade.mtp.http.port=7778
jade.mtp.http.keystore=path/to/keystore
jade.mtp.http.keystore-password=password
jade.mtp.http.truststore=path/to/truststore
jade.mtp.http.truststore-password=password
```

### Usage

```java
// Start HTTP MTP on specific port
Profile profile = new ProfileImpl();
profile.setParameter("jade.mtp.http.port", "7778");
```

## IIOP MTP (DEPRECATED)

**Package**: `jade.mtp.iiop`

**Status**: DEPRECATED — Uses CORBA/IIOP which was removed from Java 9+.

### Architecture

```
IIOP MTP
└── MessageTransportProtocol — IIOP-based MTP implementation
```

### Blocking on Java 9+

This MTP CANNOT compile or run on Java 9 or higher due to CORBA package removal.

### Migration Path

Replace IIOP MTP with HTTP MTP for Java 9+ deployments.

## Internal Message Transport (IMTP)

### LEAP IMTP

**Package**: `jade.imtp.leap`

The LEAP IMTP provides lightweight inter-container communication with multiple transport options.

#### JICP Protocol

**Package**: `jade.imtp.leap.JICP`

JADE Inter-Container Protocol — lightweight, efficient binary protocol.

```
JICP
├── JICPProtocol — Protocol definitions
├── JICPAddress — Address format
├── JICPServer — Server component
├── JICPClient — Client component
├── JICPConnection — Connection management
├── JICPSConnection — SSL connection
├── JICPPeer — Peer interface
├── JICPSPeer — SSL peer
├── Connection — Base connection interface
├── ConnectionPool — Connection pooling
├── ConnectionFactory — Factory pattern
├── ConnectionWrapper — Connection decorator
├── ProtocolManager — Protocol management
├── PDPContextManager — PDP context
├── NATUtils — NAT traversal utilities
├── JICPCompressor — Compression (1, 2, 3 variants)
├── BIFEDispatcher — BE/FE dispatcher
├── BIBEDispatcher — BI/BE dispatcher
├── BIFESDispatcher — BI/FE dispatcher
└── MaskableJICPPeer — Maskable peer
```

#### NIO Transport

**Package**: `jade.imtp.leap.nio`

Non-blocking I/O for scalable inter-container communication.

```
NIO Transport
├── NIOMediator — NIO mediation
├── NIOJICPConnection — NIO JICP connection
├── NIOJICPSConnection — NIO SSL connection
├── NIOJICPPeer — NIO peer
├── NIOJICPSPeer — NIO SSL peer
├── NIOHTTPSConnection — NIO HTTPS connection
├── NIOHTTPSPeer — NIO HTTPS peer
├── NIOHTTPPeer — NIO HTTP peer
├── NIOHTTPHelper — HTTP utilities
├── SSLEngineHelper — SSL helper
├── PacketIncompleteException — Packet exception
├── StuckSimulator — Testing utility
└── BEManagementService — BE management
```

#### HTTP Transport

**Package**: `jade.imtp.leap.http`

HTTP-based inter-container transport (for firewalls/proxies).

```
HTTP Transport
├── HTTPProtocol — HTTP protocol
├── HTTPSProtocol — HTTPS protocol
├── HTTPPeer — HTTP peer
├── HTTPSPeer — HTTPS peer
├── HTTPAddress — HTTP address
├── HTTPSAddress — HTTPS address
├── HTTPHelper — HTTP utilities
├── HTTPIO — Input/Output
├── HTTPPacket — HTTP packet
├── HTTPRequest — Request wrapper
├── HTTPResponse — Response wrapper
├── HTTPFESDispatcher — FE dispatcher
├── HTTPFEDispatcher — FE dispatcher
├── HTTPBEDispatcher — BE dispatcher
├── HTTPServerConnection — Server connection
└── HTTPClientConnection — Client connection
```

#### SMS Transport

**Package**: `jade.imtp.leap.sms`

SMS-based transport for mobile devices.

```
SMS Transport
├── SMSManager — SMS management
├── PhoneBasedSMSManager — Phone implementation
├── SMSBEDispatcher — BE dispatcher
└── Boot — SMS boot
```

### IMTP Manager

**Package**: `jade.imtp.leap`

```
LEAPIMTPManager
├── ConnectionDropped — Connection drop callback
├── CommandDispatcher — Command dispatch
├── Serializer — Object serialization
├── StubHelper — Stub helper
├── Stub — Stub base
├── Skeleton — Skeleton base
├── NodeStub — Node stub
├── NodeSkel — Node skeleton
├── NodeLEAP — LEAP node
├── BackEndStub — BE stub
├── BackEndSkel — BE skeleton
├── FrontEndStub — FE stub
├── FrontEndSkel — FE skeleton
├── ICP — ICP interface
├── ICPException — ICP exception
├── LEAPSerializationException — Serialization exception
├── Dispatcher — Dispatcher interface
├── DispatcherException — Dispatcher exception
├── ICPDispatchException — Dispatch exception
├── TransportProtocol — Transport protocol
└── DeliverableDataInputStream / DeliverableDataOutputStream — Serialization streams
```

### RMI IMTP (Legacy)

**Package**: `jade.imtp.rmi`

```
RMI IMTP
├── RMIIMTPManager — RMI manager
├── ServiceManagerRMI — Service manager interface
├── ServiceManagerRMIImpl — Service manager impl
├── NodeRMI — Node RMI interface
├── NodeRMIImpl — Node RMI impl
└── NodeAdapter — Node adapter
```

## Transport Selection

### Profile Configuration

```java
// Use LEAP IMTP with JICP transport
profile.setParameter(Profile.IMTP, "jade.imtp.leap.JICPIMTPManager");

// Use LEAP IMTP with HTTP transport
profile.setParameter(Profile.IMTP, "jade.imtp.leap.HTTPIMTPManager");

// Use RMI IMTP
profile.setParameter(Profile.IMTP, "jade.imtp.rmi.RMIIMTPManager");
```

### Default Selection

| Environment | Default IMTP |
|------------|-------------|
| J2SE Desktop | LEAP/JICP |
| J2ME/MIDP | LEAP/JICP |
| LEAP Mobile | LEAP/HTTP or SMS |
| Java 11+ | LEAP/JICP or HTTP |

## MTP Descriptor

Each MTP publishes a descriptor for discovery:

```java
public class MTPDescriptor implements Serializable {
    private String name;           // Human-readable name
    private String className;      // MTP class
    private String[] addresses;    // Transport addresses
    
    // Used by AMS to track available MTPs
}
```

## Adding Custom MTPs

1. Implement `jade.mtp.MTP` interface
2. Implement `jade.mtp.MTPDescriptor`
3. Register with platform:
   ```java
   // Via administration
   ContainerController cc = ...;
   cc.installMTP("com.example.MyMTP", new Properties());
   ```
