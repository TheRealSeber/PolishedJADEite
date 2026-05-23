# Remediation Plan — JADE 4.6.0

## Prioritized Action Items

Remediation items are ordered by: (1) EOL/deprecated runtimes, (2) outdated dependencies, (3) code quality. Each item includes severity, effort assessment, and specific actions.

---

## Phase 1: Runtime Migration (Critical Priority)

### 1.1 Upgrade from Java 1.5 to Java 1.6

**Severity**: High
**Blocker**: No — Java 1.6 can compile Java 1.5 source
**Effort**: Low

**Actions**:
1. Update `build.xml` lines 158-159:
   ```xml
   <!-- FROM -->
   target="1.5"
   source="1.5"
   <!-- TO -->
   target="1.6"
   source="1.6"
   ```
2. Run `ant jade` to verify compilation
3. Address any deprecation warnings from javac

**Validation**: `ant jade` must complete with BUILD SUCCESSFUL

---

### 1.2 Add Generics to Raw Collections (Phase 1)

**Severity**: Medium
**Dependencies**: 1.1
**Effort**: Medium-High

**Tool**: Use `jade-1.5-to-1.6-raw-types` skill

**Scope**:
- 122+ files with raw `Hashtable`, `ArrayList`, `List`, `Iterator`, `Vector`
- 239+ raw collection instances
- 47 deprecated `@deprecated` annotations

**Actions**:
1. Run `jade-phase0-scanner` to identify all files
2. Process files with `jade-1.5-to-1.6-raw-types` skill
3. Verify with `ant jade` compilation
4. **CRITICAL**: Do NOT parameterize `jade.util.leap.*` types

**Example Transformation**:
```java
// BEFORE
Hashtable localAliases = new Hashtable();
List addresses = new ArrayList();

// AFTER  
Hashtable<String, AID> localAliases = new Hashtable<String, AID>();
List<String> addresses = new ArrayList<String>();
```

**Validation**: Zero compile errors, reduced unchecked warnings

---

### 1.3 Continue Generics Through Java 1.7

**Severity**: Medium
**Dependencies**: 1.2
**Effort**: Medium

**Actions**:
1. Update `build.xml` to `target="1.7"`, `source="1.7"`
2. Add explicit type parameters where diamond operator (`<>`) would have been used
3. Verify with `ant jade`

---

## Phase 2: Dependency Remediation (High Priority)

### 2.1 Upgrade Apache Commons Codec

**Severity**: High
**Effort**: Low

**Actions**:
1. Download `commons-codec-1.15.jar` from Maven Central
2. Place in `JADE-4.6.0/src/jade/lib/commons-codec/`
3. Update `build.xml` classpath reference:
   ```xml
   classpath="lib/commons-codec/commons-codec-1.15.jar"
   ```
4. Verify with `ant jade`

**API Compatibility**: 100% backward compatible for methods used by JADE (Base64, DigestUtils)

---

### 2.2 Exclude CORBA/IIOP MTP for Java 11+

**Severity**: High (blocking for Java 9+)
**Effort**: Medium

**Actions**:
1. For Java 11+ builds, exclude `jade.mtp.iiop` package:
   ```xml
   excludes="demo/**,examples/**,test/**,jade/mtp/iiop/**"
   ```
2. Update `javadoc` target to exclude iiop package
3. Document HTTP MTP as replacement
4. Update distribution configuration to not include `iiop.jar`

**Impact**: IIOP/CORBA-based agent platforms will not work on Java 11+. Users must switch to HTTP MTP.

---

## Phase 3: Deprecated API Cleanup (Medium Priority)

### 3.1 Clean Up ContractNetResponder

**Severity**: Medium
**Effort**: Medium

**Actions**:
1. Either:
   - Deprecate entire `ContractNetResponder` class
   - OR remove deprecated methods entirely
2. Update all examples using deprecated methods
3. Document migration path in release notes

**Recommended**: Deprecate entire class, keep existing deprecated methods functional for backward compatibility

---

### 3.2 Clean Up DFService Methods

**Severity**: Medium
**Effort**: Medium-High

**Actions**:
1. Remove the 7 deprecated blocking methods from `DFService`
2. Update all example code using `df.register()`, `df.deregister()`, etc.
3. Replace with `SubscriptionInitiator` / `SubscriptionResponder` pattern
4. Update Javadoc to remove deprecated notice

---

### 3.3 Clean Up Behaviour Handlers

**Severity**: Medium
**Effort**: Medium

**Files**:
- `jade.proto.AchieveREResponder`
- `jade.proto.SubscriptionResponder`
- `jade.core.behaviours.WakerBehaviour`

**Actions**:
1. Remove underscore-suffixed deprecated handlers
2. Keep non-underscore methods (which are the current recommended approach)
3. Update examples

---

### 3.4 Clean Up FIPAProtocolNames

**Severity**: Low
**Effort**: Low

**Actions**:
1. Mark entire class deprecated with `@Deprecated`
2. Add Javadoc redirecting to `jade.domain.FIPANames.InteractionProtocol`
3. Schedule removal for next major version

---

## Phase 4: Architecture Improvements (Medium Priority)

### 4.1 Refactor Agent.java

**Severity**: Medium (Long-term)
**Effort**: High

**Not a prerequisite for migration**, but recommended for long-term maintainability.

**Actions**:
1. Extract `AgentBehaviourManager` class
2. Extract `AgentMessageQueue` class
3. Extract `AgentServiceRegistry` class
4. Extract `AgentMobilityHandler` class
5. Keep `Agent.java` as facade/wrapper

**Validation**: All existing tests must pass after refactoring

---

### 4.2 Separate Generated Parser Code

**Severity**: Low
**Effort**: Low

**Actions**:
1. Add `jade/lang/acl/ACLParser*.java` to `.gitignore`
2. Add `jade/content/lang/sl/SLParser*.java` to `.gitignore`
3. Update `ant parser` target to create these files
4. Document: `ant jade` requires `ant parser` first if parsers not present

---

## Phase 5: Build System Modernization (Low Priority)

### 5.1 Consider Maven/Gradle Migration

**Severity**: Low
**Effort**: High

**Rationale**: Modern IDE integration, dependency management, CI/CD compatibility.

**Current**: Apache Ant (still maintained, no immediate need to change)

**Recommendation**: Keep Ant for now, but add Maven POM as alternative for modern tooling.

---

## Migration Version Path

```
Current: JADE-4.6.0 (Java 1.5)
    │
    ▼
Phase 1: JADE-4.6.0-java1.6  (Generics added)
    │   Skills: jade-1.5-to-1.6-raw-types, jade-1.5-to-1.6-enhanced-for
    │
    ▼
Phase 2: JADE-4.6.0-java1.7  (Diamond, try-with-resources)
    │   Add diamond operator where applicable
    │
    ▼
Phase 3: JADE-4.6.0-java1.8  (Lambdas, streams, new APIs)
    │   Upgrade Commons Codec to 1.15
    │   Add stream-based convenience methods
    │
    ▼
Phase 4: JADE-4.6.0-java11   (Module system, CORBA removed)
    │   Exclude jade.mtp.iiop
    │   Module system configuration
    │
    ▼
Phase 5: JADE-4.6.0-java17   (Modern LTS)
    │
    ▼
Phase 6: JADE-4.6.0-java21   (Latest LTS)
```

---

## Validation Checklist

For each phase, verify:

- [ ] `ant jade` compiles with BUILD SUCCESSFUL
- [ ] `ant examples` compiles example agents
- [ ] `ant doc` generates javadoc
- [ ] No new compile warnings introduced
- [ ] All existing unit tests pass (if any)
- [ ] Core agent lifecycle works (create, send message, kill)
- [ ] DF registration/search works
- [ ] AMS platform management works

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Commons Codec API break | Very Low | Medium | Test after upgrade |
| MIDP support broken | Low | High | Keep LEAP types unparameterized |
| Deprecated API users broken | Medium | Low | Deprecation warnings first |
| Example code broken | Medium | Low | Update examples in same PR |

---

*This remediation plan should be executed incrementally. Each phase should be validated before proceeding to the next.*
