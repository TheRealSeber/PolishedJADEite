# Validation Criteria — JADE 4.6.0 Migration

## Phase Validation Criteria

### Phase 1: Utilities Migration

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| `ant jade` compilation | Exit code | 0 | **Critical** |
| LEAP types unchanged | File diff | 0 changes | **Critical** |
| Logger compiles | Exit code | 0 | **High** |
| ACL parser compiles | Exit code | 0 | **High** |

### Phase 2: Core Data Types Migration

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| `ant jade` compilation | Exit code | 0 | **Critical** |
| AID class compiles | Exit code | 0 | **Critical** |
| FIPA ontology compiles | Exit code | 0 | **High** |
| DF types compile | Exit code | 0 | **High** |

### Phase 3: Content System Migration

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| `ant jade` compilation | Exit code | 0 | **Critical** |
| SL codec compiles | Exit code | 0 | **Critical** |
| Ontology system compiles | Exit code | 0 | **Critical** |
| Content manager compiles | Exit code | 0 | **Critical** |

### Phase 4: Core Kernel Migration

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| `ant jade` compilation | Exit code | 0 | **Critical** |
| Agent class compiles | Exit code | 0 | **Critical** |
| Behaviour classes compile | Exit code | 0 | **Critical** |
| AMS compiles | Exit code | 0 | **High** |
| DF compiles | Exit code | 0 | **High** |
| Protocol classes compile | Exit code | 0 | **High** |

### Phase 5: Transport Layer Migration

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| `ant jade` compilation | Exit code | 0 | **Critical** |
| HTTP MTP compiles | Exit code | 0 | **Critical** |
| LEAP IMTP compiles | Exit code | 0 | **Critical** |
| IIOP excluded (Java 11+) | File list | 0 files | **Medium** |

### Phase 6: Services Migration

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| `ant jade` compilation | Exit code | 0 | **Critical** |
| Messaging service compiles | Exit code | 0 | **Critical** |
| Mobility service compiles | Exit code | 0 | **High** |
| All services compile | Exit code | 0 | **High** |

### Phase 7: Wrapper API Migration

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| `ant jade` compilation | Exit code | 0 | **Critical** |
| Container controller compiles | Exit code | 0 | **Critical** |
| Agent controller compiles | Exit code | 0 | **Critical** |
| Platform controller compiles | Exit code | 0 | **Critical** |

### Phase 8: Tools Migration

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| `ant jade` compilation | Exit code | 0 | **Critical** |
| GUI components compile | Exit code | 0 | **High** |
| All tools compile | Exit code | 0 | **High** |
| Examples compile | Exit code | 0 | **High** |

## Full Platform Validation

### Compilation Gate

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| `ant jade` | Exit code | 0 | **Critical** |
| `ant examples` | Exit code | 0 | **Critical** |
| `ant lib` | jade.jar created | Yes | **Critical** |

### Code Quality Gate

| Criterion | Measure | Baseline | Target | Status |
|-----------|---------|---------|--------|--------|
| Unchecked warnings | Count | ~50+ | Decreasing | **Required** |
| Deprecation warnings | Count | ~47 | Tracked | **Required** |
| Serial warnings | Count | ~100+ | Tracked | **Required** |

### Binary Compatibility Gate

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| jade.jar generated | File exists | Yes | **Critical** |
| iiop.jar generated | File exists | Yes (if Java <11) | **Medium** |
| All classes present | JAR listing | All packages | **High** |

## Migration-Specific Validation

### Java Version Validation

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| Source version | build.xml | Updated | **Critical** |
| Target version | build.xml | Updated | **Critical** |
| JDK compatibility | Compilation | JDK version ≥ target | **Critical** |

### Commons Codec Upgrade Validation (Java 11+)

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| JAR version | File name | 1.15+ | **High** |
| Base64.encode/decode | Compilation | Success | **High** |
| DigestUtils | Compilation | Success | **Medium** |

### IIOP Exclusion Validation (Java 11+)

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| IIOP source excluded | Files compiled | 0 | **Critical** |
| IIOP imports absent | Compilation | No javax.rmi errors | **Critical** |
| HTTP MTP works | Compilation | Success | **High** |

### LEAP Type Preservation Validation

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| LEAP types unchanged | File diff | 0 changes | **Critical** |
| jade.util.leap.Serializable | Present | Yes | **Critical** |
| LEAP imports compile | Exit code | 0 | **Critical** |

## Behavioral Validation (If Available)

### Runtime Behavior

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| Platform starts | `ant jade` | BUILD SUCCESSFUL | **Critical** |
| Main container created | Runtime log | No errors | **High** |
| AMS started | Runtime log | AMS ready | **High** |
| DF started | Runtime log | DF ready | **High** |

### Agent Lifecycle

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| Agent created | Compilation + test | Success | **Medium** |
| Agent sends message | Example run | Success | **Medium** |
| Agent receives message | Example run | Success | **Medium** |

### DF Registration

| Criterion | Measure | Target | Severity |
|-----------|--------|--------|----------|
| DF registers agent | Compilation | Success | **Medium** |
| DF search works | Compilation | Success | **Medium** |

## Exit Criteria Summary

### Migration Phase Complete When:
1. `ant jade` returns exit code 0 (BUILD SUCCESSFUL)
2. `ant examples` returns exit code 0
3. `ant lib` creates jade.jar
4. No new compilation errors introduced
5. LEAP types preserved (0 changes to `jade.util.leap`)
6. IIOP excluded (for Java 11+ migration)

### Next Phase Can Begin When:
1. Current phase exit criteria met
2. All critical validations pass
3. Benchmark delta shows improvement (unchecked warnings decreasing)
4. No regressions in compilation of dependent packages

---

*See [Component Order](./component-order.md) for migration sequence.*
