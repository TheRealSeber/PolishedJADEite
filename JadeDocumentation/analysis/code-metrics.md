# Code Metrics — JADE 4.6.0

## Project Statistics

| Metric | Value |
|--------|-------|
| **Total Java Files** | 1,142 |
| **Total Lines of Code** | ~220,585 |
| **Total Packages** | 60+ |
| **Average File Size** | ~193 lines |
| **Median File Size** | ~150 lines |
| **Largest File** | `jade.core.Agent.java` (~2,502 lines) |

## File Size Distribution

| Size Range | Files | Percentage |
|-----------|-------|-----------|
| < 100 lines | ~300 | 26% |
| 100-250 lines | ~500 | 44% |
| 250-500 lines | ~250 | 22% |
| 500-1000 lines | ~70 | 6% |
| > 1000 lines | ~22 | 2% |

## Largest Files

| File | Package | Lines (est.) |
|------|---------|-------------|
| `Agent.java` | jade.core | ~2,502 |
| `Ontology.java` | jade.content.onto | ~1,000+ |
| `ACLMessage.java` | jade.lang.acl | ~1,322 |
| `df.java` | jade.domain | ~1,200+ |
| `BasicOntology.java` | jade.content.onto | ~600+ |
| `BeanOntologyBuilder.java` | jade.content.onto | ~600+ |
| `Profile.java` | jade.core | ~622 |
| `AgentTree.java` | jade.gui | ~600+ |
| `AID.java` | jade.core | ~562 |
| `DFService.java` | jade.domain | ~1,181 |

## Package Size Distribution

| Package | Files | Est. Lines |
|---------|-------|-----------|
| jade.content.* | 100+ | ~50,000 |
| jade.tools.* | 150+ | ~50,000 |
| jade.imtp.* | 100+ | ~30,000 |
| jade.domain.* | 100+ | ~40,000 |
| jade.gui.* | 35+ | ~20,000 |
| jade.core.* | 38+ | ~15,000 |
| jade.proto.* | 25+ | ~15,000 |
| jade.util.* | 35+ | ~10,000 |
| jade.lang.acl | 15+ | ~8,000 |
| jade.core.behaviours | 20+ | ~8,000 |

## Code Complexity Indicators

### High-Complexity Indicators

#### Nested Conditionals
Files with deep nesting (>5 levels) detected in:
- `Agent.java` — Agent lifecycle state management
- `MessagingService.java` — Message routing logic
- `Ontology.java` — Content validation chains
- `DFDBKB.java` — Search and matching logic

#### Large Switch Statements
- `ACLMessage.java` — Performative handling (~25 cases)
- `AgentState.java` — State transitions
- `FSMBehaviour.java` — State machine transitions

#### Complex Synchronization
- `Agent.java` — Thread-to-behaviour mapping with `Hashtable` synchronization
- `Scheduler.java` — Behaviour scheduling with locks
- `CommandProcessor.java` — Sink registration with `Hashtable` synchronization

## Code Quality Metrics

### Comment Coverage

| Metric | Estimate |
|--------|----------|
| Files with Javadoc | ~60% |
| Classes with Javadoc | ~70% |
| Methods with inline comments | ~40% |
| Deprecated items documented | ~90% |

### Type Usage

#### Raw Collections (No Generics)
- **Files affected**: 122+
- **Instances of raw Hashtable**: 30+
- **Instances of raw ArrayList/List**: 100+
- **Instances of raw Iterator**: 50+

### Deprecated API Usage
- `@deprecated` annotations: 47 instances
- Deprecated classes: 5
- Deprecated methods: 30+

## Package Coupling

### Highly Coupled Packages
| Package A | Package B | Coupling Type |
|-----------|----------|---------------|
| jade.core | jade.util.leap | Dependency |
| jade.domain | jade.core | Inheritance |
| jade.proto | jade.core.behaviours | Dependency |
| jade.lang.acl | jade.domain | Dependency |
| jade.content | jade.core | Dependency |
| jade.gui | jade.core | Dependency |
| jade.tools | jade.gui | Inheritance |
| jade.wrapper | jade.core | Dependency |

### Afferent Coupling (Incoming Dependencies)
Packages depended upon by many others:
1. `jade.core` — Core (highest)
2. `jade.lang.acl` — ACL messages
3. `jade.util.leap` — Collections
4. `jade.domain` — Domain model

## Compilation Metrics

### Build Configuration
- **Source version**: Java 1.5
- **Target version**: Java 1.5
- **Exclusions**: `demo/**`, `examples/**`, `test/**`
- **Compiler options**: `nowarn="on"`, `deprecation="on"`, `debug="on"`

### Expected Compile Warnings
Based on code analysis:
- Unchecked cast warnings: 50+ (from raw collections)
- Deprecation warnings: 47+ (from deprecated APIs)
- Serial warning (missing serialVersionUID): 100+

## Documentation Quality

### Javadoc Coverage by Package

| Package | Javadoc % | Notes |
|---------|-----------|-------|
| jade.core | 80% | Good coverage |
| jade.lang.acl | 75% | Good coverage |
| jade.domain | 70% | FIPA spec documented |
| jade.content | 65% | Some schemas undocumented |
| jade.proto | 60% | Protocol states documented |
| jade.gui | 40% | GUI code less documented |
| jade.tools | 30% | Tool internals less documented |

## Test Coverage (Not Analyzed)

No test files were found in the source tree (`JADE-4.6.0/src/jade/src/`). Tests may exist separately or were not committed to the repository.

---

*See [Complexity Analysis](./complexity-analysis.md) for detailed complexity metrics.*
