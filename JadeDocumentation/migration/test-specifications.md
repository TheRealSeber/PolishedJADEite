# Test Specifications — JADE 4.6.0 Migration

## Phase 1: Utilities Migration Tests

### Test 1.1: LEAP Collections Compatibility
- **Purpose**: Verify LEAP collections still work
- **Action**: Compile all files importing `jade.util.leap.*`
- **Expected**: SUCCESS — LEAP types unchanged
- **Validation**: No changes to LEAP type signatures

### Test 1.2: Logger Functionality
- **Purpose**: Verify Logger still works
- **Action**: Compile `jade.util.Logger`
- **Expected**: SUCCESS
- **Validation**: Logger facade compiles with correct log levels

### Test 1.3: ACL Message Template Compilation
- **Purpose**: Verify ACL parsing still works
- **Action**: Compile `jade.lang.acl.*`
- **Expected**: SUCCESS
- **Validation**: ACLMessage, MessageTemplate compile

## Phase 2: Core Data Types Tests

### Test 2.1: AID Construction
- **Purpose**: Verify AID still works
- **Action**: Compile `jade.core.AID`
- **Expected**: SUCCESS
- **Validation**: AID constructor, getName(), getHap() work

### Test 2.2: FIPA Ontology Compilation
- **Purpose**: Verify FIPA ontology types compile
- **Action**: Compile `jade.domain.FIPAAgentManagement.*`
- **Expected**: SUCCESS
- **Validation**: All FIPA description types compile

### Test 2.3: DF Agent Description
- **Purpose**: Verify DF description types compile
- **Action**: Compile `jade.domain.FIPAAgentManagement.DFAgentDescription`
- **Expected**: SUCCESS
- **Validation**: ServiceDescription, DFAgentDescription compile

## Phase 3: Content System Tests

### Test 3.1: SL Codec Compilation
- **Purpose**: Verify SL codec compiles
- **Action**: Compile `jade.content.lang.sl.*`
- **Expected**: SUCCESS
- **Validation**: SLCodec, SLParser compile

### Test 3.2: Ontology System Compilation
- **Purpose**: Verify ontology system compiles
- **Action**: Compile `jade.content.onto.*`
- **Expected**: SUCCESS
- **Validation**: Ontology, BasicOntology, BeanOntology compile

### Test 3.3: Content Manager Compilation
- **Purpose**: Verify content manager compiles
- **Action**: Compile `jade.content.ContentManager`
- **Expected**: SUCCESS
- **Validation**: ContentManager, encode/decode methods compile

## Phase 4: Core Kernel Tests

### Test 4.1: Agent Base Class Compilation
- **Purpose**: Verify Agent class compiles
- **Action**: Compile `jade.core.Agent`
- **Expected**: SUCCESS
- **Validation**: setup(), takeDown(), send(), receive() compile

### Test 4.2: Runtime Singleton Compilation
- **Purpose**: Verify Runtime compiles
- **Action**: Compile `jade.core.Runtime`
- **Expected**: SUCCESS
- **Validation**: Runtime.instance(), createAgentContainer() compile

### Test 4.3: Behaviour Classes Compilation
- **Purpose**: Verify all behaviour classes compile
- **Action**: Compile `jade.core.behaviours.*`
- **Expected**: SUCCESS
- **Validation**: All behaviour types compile

### Test 4.4: AMS Agent Compilation
- **Purpose**: Verify AMS compiles
- **Action**: Compile `jade.domain.ams`
- **Expected**: SUCCESS
- **Validation**: AMS agent lifecycle methods compile

### Test 4.5: DF Agent Compilation
- **Purpose**: Verify DF compiles
- **Action**: Compile `jade.domain.df`, `jade.domain.DFService`
- **Expected**: SUCCESS
- **Validation**: DF registration, search compile

### Test 4.6: Protocol Classes Compilation
- **Purpose**: Verify all protocol classes compile
- **Action**: Compile `jade.proto.*`
- **Expected**: SUCCESS
- **Validation**: ContractNet, AchieveRE, Propose, Subscription protocols compile

## Phase 5: Transport Layer Tests

### Test 5.1: HTTP MTP Compilation
- **Purpose**: Verify HTTP MTP compiles
- **Action**: Compile `jade.mtp.http.*`
- **Expected**: SUCCESS
- **Validation**: HTTPServer, HTTPProtocol compile

### Test 5.2: LEAP IMTP Compilation
- **Purpose**: Verify LEAP IMTP compiles
- **Action**: Compile `jade.imtp.leap.*`
- **Expected**: SUCCESS
- **Validation**: LEAPIMTPManager, JICP, HTTP transports compile

### Test 5.3: NIO Transport Compilation
- **Purpose**: Verify NIO transport compiles
- **Action**: Compile `jade.imtp.leap.nio.*`
- **Expected**: SUCCESS
- **Validation**: NIOMediator, NIO connections compile

### Test 5.4: IIOP MTP Exclusion (Java 11+)
- **Purpose**: Verify IIOP excluded for Java 11+
- **Action**: Compile without `jade.mtp.iiop`
- **Expected**: SUCCESS
- **Validation**: `jade.mtp.iiop` excluded from build

## Phase 6: Services Tests

### Test 6.1: Messaging Service Compilation
- **Purpose**: Verify messaging service compiles
- **Action**: Compile `jade.core.messaging.*`
- **Expected**: SUCCESS
- **Validation**: MessagingService, message routing compile

### Test 6.2: Mobility Service Compilation
- **Purpose**: Verify mobility service compiles
- **Action**: Compile `jade.core.mobility.*`
- **Expected**: SUCCESS
- **Validation**: AgentMobilityService, mobility helpers compile

### Test 6.3: Replication Service Compilation
- **Purpose**: Verify replication service compiles
- **Action**: Compile `jade.core.replication.*`
- **Expected**: SUCCESS
- **Validation**: AgentReplicationService compile

## Phase 7: Wrapper API Tests

### Test 7.1: Container Controller Compilation
- **Purpose**: Verify container controller compiles
- **Action**: Compile `jade.wrapper.ContainerController`, `jade.wrapper.AgentContainer`
- **Expected**: SUCCESS
- **Validation**: createNewAgent(), getAgent() compile

### Test 7.2: Agent Controller Compilation
- **Purpose**: Verify agent controller compiles
- **Action**: Compile `jade.wrapper.AgentController`, `jade.wrapper.AgentControllerImpl`
- **Expected**: SUCCESS
- **Validation**: start(), suspend(), resume(), kill() compile

### Test 7.3: Platform Controller Compilation
- **Purpose**: Verify platform controller compiles
- **Action**: Compile `jade.wrapper.PlatformController`, `jade.wrapper.PlatformControllerImpl`
- **Expected**: SUCCESS
- **Validation**: start(), kill(), createAgentContainer() compile

## Phase 8: Tools and GUI Tests

### Test 8.1: GUI Components Compilation
- **Purpose**: Verify GUI components compile
- **Action**: Compile `jade.gui.*`
- **Expected**: SUCCESS
- **Validation**: AgentTree, AclGui, AIDGui compile

### Test 8.2: RMA Tool Compilation
- **Purpose**: Verify RMA tool compiles
- **Action**: Compile `jade.tools.rma.*`
- **Expected**: SUCCESS
- **Validation**: RMA main window, actions compile

### Test 8.3: Sniffer Tool Compilation
- **Purpose**: Verify sniffer tool compiles
- **Action**: Compile `jade.tools.sniffer.*`
- **Expected**: SUCCESS
- **Validation**: Sniffer agent, canvas compile

### Test 8.4: Introspector Tool Compilation
- **Purpose**: Verify introspector tool compiles
- **Action**: Compile `jade.tools.introspector.*`
- **Expected**: SUCCESS
- **Validation**: Introspector agent compile

## Full Platform Integration Tests

### Test 9.1: Full Compilation
- **Purpose**: Verify entire platform compiles
- **Action**: `ant jade`
- **Expected**: BUILD SUCCESSFUL
- **Validation**: All packages compile without errors

### Test 9.2: Examples Compilation
- **Purpose**: Verify examples still compile
- **Action**: `ant examples`
- **Expected**: BUILD SUCCESSFUL
- **Validation**: Example agents compile

### Test 9.3: Library Generation
- **Purpose**: Verify JAR can be generated
- **Action**: `ant lib`
- **Expected**: BUILD SUCCESSFUL, jade.jar created
- **Validation**: JAR contains all compiled classes

## Code Quality Tests

### Test 10.1: Unchecked Warning Count
- **Purpose**: Verify generics reduce unchecked warnings
- **Action**: Count unchecked warnings in build output
- **Expected**: Count decreases after migration
- **Validation**: Warning delta tracked per migration phase

### Test 10.2: Deprecated Warning Count
- **Purpose**: Verify deprecated API warnings tracked
- **Action**: Count deprecation warnings
- **Expected**: Warnings from `@deprecated` annotations tracked
- **Validation**: Deprecation warning count documented

---

*See [Validation Criteria](./validation-criteria.md) for success criteria.*
