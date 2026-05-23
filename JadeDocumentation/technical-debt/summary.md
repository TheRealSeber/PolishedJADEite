# Technical Debt Summary — JADE 4.6.0

## Overview

This document provides an aggregated overview of all technical debt identified in the JADE 4.6.0 codebase through static analysis. Technical debt is categorized by severity and type, following the priority order: (1) EOL/deprecated runtimes and frameworks, (2) outdated dependencies, (3) code quality and architectural issues.

## Debt Categories

### Category 1: Runtime & Platform Debt (High Severity)

| ID | Item | Severity | Files Affected | Status |
|----|------|----------|----------------|--------|
| TD-RT-01 | Java 1.5 EOL (2009) | **High** | build.xml | End of Life |
| TD-RT-02 | CORBA/IIOP MTP removal in Java 9+ | **High** | jade.mtp.iiop/* | Blocked |
| TD-RT-03 | FIPA ContractNetResponder partial deprecation | **High** | jade.proto.ContractNetResponder | Confusing API |

**Total Runtime Debt**: 3 items, all High severity

### Category 2: Dependency Debt (Medium-High Severity)

| ID | Item | Severity | Files Affected | Status |
|----|------|----------|----------------|--------|
| TD-DEP-01 | Apache Commons Codec 1.3 EOL | **High** | lib/commons-codec-1.3.jar | Known CVEs |
| TD-DEP-02 | No Maven/Gradle build system | **Medium** | build.xml | Legacy Ant only |

**Total Dependency Debt**: 2 items (1 High, 1 Medium)

### Category 3: Code Quality Debt (Medium Severity)

| ID | Item | Severity | Files Affected | Estimate |
|----|------|----------|----------------|----------|
| TD-CQ-01 | Raw collection types (no generics) | **Medium** | 122+ files | 239+ instances |
| TD-CQ-02 | Deprecated DFService methods | **Medium** | jade.domain.DFService | 7 methods |
| TD-CQ-03 | Deprecated behaviour handlers | **Medium** | jade.proto.* | 6 methods |
| TD-CQ-04 | Deprecated GUI tree methods | **Low** | jade.gui.AgentTree | 3 methods |
| TD-CQ-05 | Deprecated protocol names class | **Low** | jade.proto.FIPAProtocolNames | 1 class |
| TD-CQ-06 | Deprecated parser CharStream | **Low** | jade.lang.acl.SimpleCharStream | 2 classes |

**Total Code Quality Debt**: 6 items (3 Medium, 3 Low)

### Category 4: Architectural Debt (Medium Severity)

| ID | Item | Severity | Impact |
|----|------|----------|--------|
| TD-ARCH-01 | God Class: Agent.java (~2,502 lines) | **Medium** | Hard to maintain, test |
| TD-ARCH-02 | LEAP collection duplicate hierarchy | **Medium** | Migration complexity |
| TD-ARCH-03 | Thread management in Agent.java | **Medium** | Synchronization complexity |

**Total Architectural Debt**: 3 items, all Medium severity

## Debt by Severity

| Severity | Count | Category |
|----------|-------|----------|
| **High** | 4 | Runtime (3), Dependency (1) |
| **Medium** | 6 | Code Quality (3), Architectural (3) |
| **Low** | 3 | Code Quality (3) |

**Total Technical Debt Items**: 13

## Debt Distribution by Package

| Package | High | Medium | Low | Total |
|---------|------|--------|-----|-------|
| jade.core | 1 | 1 | 0 | 2 |
| jade.mtp.iiop | 1 | 0 | 0 | 1 |
| jade.proto | 1 | 1 | 0 | 2 |
| jade.domain | 0 | 1 | 1 | 2 |
| jade.lang.acl | 0 | 0 | 1 | 1 |
| jade.content | 0 | 0 | 1 | 1 |
| jade.gui | 0 | 0 | 1 | 1 |
| Build System | 1 | 1 | 0 | 2 |
| External Dependency | 1 | 0 | 0 | 1 |

## Trend Analysis

Based on the deprecation annotations and code comments:

### Growing Debt (Recent)
- `AchieveREResponder` deprecated methods added in JADE 3.3+
- `ContractNetResponder` deprecated methods added in JADE 3.4+
- `WakerBehaviour.onWake()` replacement added recently

### Stable Debt (Long-standing)
- `jade.proto.FIPAProtocolNames` — deprecated since early JADE 3.x
- Java 1.5 target — unchanged since JADE 3.0

### Unknown Age
- Commons Codec 1.3 — likely since JADE 3.0 era
- Raw collections — present since pre-generics era (pre-Java 5)

## Impact Assessment

### Compilation Impact
- Java 1.5 target prevents compilation on Java 9+ without changes
- Commons Codec 1.3 may not be resolvable in modern Maven repositories
- CORBA/IIOP removal requires package exclusion on Java 9+

### Runtime Impact
- Java 1.5 EOL means no security patches for JVMs running JADE
- Known vulnerabilities in Commons Codec 1.3
- No maintenance or support available

### Development Impact
- Raw collections produce unchecked warnings
- Deprecated API usage clutters code
- No IDE autocomplete for deprecated patterns

## Recommended Prioritization

1. **Immediate**: Java 1.5 migration (enables everything else)
2. **Short-term**: Commons Codec upgrade, IIOP exclusion
3. **Medium-term**: Generics for collections, deprecation cleanup
4. **Long-term**: Architectural refactoring of Agent.java

## Maintenance Burdens

See [Maintenance Burden](./maintenance-burden.md) for detailed analysis of high-maintenance areas.

## Remediation Tracking

See [Remediation Plan](./remediation-plan.md) for prioritized action items with specific guidance.

---

*For detailed findings, see the parent [Technical Debt Report](../technical-debt-report.md).*
