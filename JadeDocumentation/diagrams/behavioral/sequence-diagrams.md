# Behavioral Diagrams — JADE 4.6.0

## Sequence: Agent Send/Receive Message

```
Agent A                           Scheduler                      Agent B
   │                                  │                              │
   │  send(ACLMessage)               │                              │
   │────────────────────────────────>│                              │
   │                                  │                              │
   │  return                          │                              │
   │◀─────────────────────────────────│                              │
   │                                  │                              │
   │                                  │ [ASYNC] route to B           │
   │                                  │─────────────────────────────▶│
   │                                  │                              │
   │                                  │              dispatchInMessage │
   │                                  │◀────────────────────────────│
   │                                  │                              │
   │                                  │              deliver to queue │
   │                                  │◀────────────────────────────│
   │                                  │                              │
   │                                  │                              │
   │  receive(template)               │                              │
   │────────────────────────────────>│                              │
   │                                  │                              │
   │                                  │  check queue                 │
   │                                  │─────────────────────────────▶│
   │                                  │                              │
   │                                  │  [if match found]            │
   │                                  │◀────────────────────────────│
   │                                  │                              │
   │  return message                  │                              │
   │◀─────────────────────────────────│                              │
   │                                  │                              │
   │  action() with message           │                              │
   │────────────────────────────────>│                              │
```

## Sequence: DF Registration

```
Agent                              DF Agent                       DFDBKB
   │                                  │                              │
   │  DFService.register(dfd)        │                              │
   │────────────────────────────────>│                              │
   │                                  │                              │
   │                                  │  validate(dfd)               │
   │                                  │─────────────────────────────▶│
   │                                  │                              │
   │                                  │  [if valid]                  │
   │                                  │◀────────────────────────────│
   │                                  │                              │
   │                                  │  register(dfd)              │
   │                                  │─────────────────────────────▶│
   │                                  │                              │
   │                                  │  [persist to HSQL]           │
   │                                  │◀────────────────────────────│
   │                                  │                              │
   │  return (no exception)           │                              │
   │◀─────────────────────────────────│                              │
```

## Sequence: Contract Net Protocol

```
Initiator                           Participant A                 Participant B
   │                                  │                              │
   │  send(CFP)                       │                              │
   │──────────────────────────────▶│─────────────────────────────▶│
   │                                  │                              │
   │                                  │  receive(CFP)               │
   │                                  │───────────────────────────▶│
   │                                  │                              │
   │  [wait for responses]            │                              │
   │                                  │  evaluate(CFP)              │
   │                                  │───────────────────────────▶│
   │                                  │                              │
   │                                  │  PROPOSE(proposal)           │
   │                                  │◀───────────────────────────│
   │                                  │                              │
   │                                  │  [skip / refuse]            │
   │                                  │───────────────────────────▶│
   │                                  │                              │
   │  all responses collected         │                              │
   │                                  │                              │
   │  evaluate proposals              │                              │
   │                                  │                              │
   │  ACCEPT_PROPOSAL                │                              │
   │──────────────────────────────▶│                              │
   │                                  │                              │
   │  REJECT_PROPOSAL                │                              │
   │─────────────────────────────────────────────────────────────▶│
   │                                  │                              │
   │                                  │  handleAcceptProposal()      │
   │                                  │───────────────────────────▶│
   │                                  │                              │
   │                                  │  perform action              │
   │                                  │───────────────────────────▶│
   │                                  │                              │
   │                                  │  INFORM(result)              │
   │                                  │◀───────────────────────────│
   │                                  │                              │
   │  INFORM received                 │                              │
   │◀─────────────────────────────────│                              │
```

## Sequence: Agent Mobility (Move)

```
Agent                          Mobility Service                  Dest Container
   │                                  │                              │
   │  doMove(destination)             │                              │
   │────────────────────────────────>│                              │
   │                                  │                              │
   │                                  │  prepare agent state         │
   │                                  │─────────────────────────────▶│
   │                                  │                              │
   │                                  │  [serialize state]           │
   │                                  │◀────────────────────────────│
   │                                  │                              │
   │                                  │  transfer via IMTP           │
   │                                  │─────────────────────────────▶│
   │                                  │                              │
   │                                  │  deserialize state            │
   │                                  │◀────────────────────────────│
   │                                  │                              │
   │                                  │  create new agent instance    │
   │                                  │◀────────────────────────────│
   │                                  │                              │
   │                                  │  start(new agent)            │
   │                                  │◀────────────────────────────│
   │                                  │                              │
   │  return (moved)                  │                              │
   │◀─────────────────────────────────│                              │
```

## State Diagram: Agent Lifecycle

```
                    ┌─────────┐
              ┌─────▶│  INIT   │◀────┐
              │      └────┬────┘     │
              │           │          │
              │      start()         │
              │           │          │
              │           ▼          │
              │      ┌────────┐     │
              │      │ ACTIVE │─────┼─────► (other agents)
              │      └───┬────┘     │
              │          │          │
              │   suspend()         │
              │          │          │
              │          ▼          │
              │    ┌───────────┐    │
              │    │ SUSPENDED │────┤
              │    └───────────┘    │
              │          │          │
              │    resume()         │
              │          │          │
              │          ▼          │
              │    ┌───────────┐    │
   kill()     │    │ WAITING   │────┘
              │    └─────┬─────┘
              │          │
              │     block()
              │          │
              │          ▼
              │    ┌──────────┐
              └────│ DELETED  │
                   └──────────┘
```

## State Diagram: Behaviour Execution

```
┌─────────────────────┐
│  SCHEDULED          │
│  (ready to run)     │
└──────────┬──────────┘
           │
           │ scheduler picks up
           ▼
┌─────────────────────┐
│   RUNNING           │
│   action() called   │
└──────────┬──────────┘
           │
           ▼
    ┌──────────────┐
    │ done()?      │
    └──────┬───────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
  [YES]      [NO]
     │           │
     ▼           ▼
┌─────────┐ ┌─────────────┐
│ REMOVED │ │ BLOCKED    │────► (message arrives)
└─────────┘ └─────────────┘
                    │
                    ▼
              ┌──────────┐
              │ SCHEDULED│
              └──────────┘
```

## Activity Diagram: Message Handling

```
        ┌─────────────────┐
        │ Receive message  │
        └────────┬────────┘
                 │
                 ▼
        ┌─────────────────┐
        │ Check template  │
        └────────┬────────┘
                 │
         ┌───────┴───────┐
         │               │
         ▼               ▼
    ┌─────────┐    ┌───────────┐
    │ MATCH   │    │ NO MATCH  │
    └────┬────┘    └─────┬─────┘
         │               │
         ▼               ▼
    ┌─────────┐    ┌───────────┐
    │ Return  │    │  Block   │
    │ message │    │  (wait)  │
    └─────────┘    └───────────┘
```

## Sequence: Ontology Encoding

```
Agent                           ContentManager                     Ontology
   │                                  │                              │
   │  send(contentElement)            │                              │
   │────────────────────────────────>│                              │
   │                                  │                              │
   │                                  │  toObject(element)         │
   │                                  │────────────────────────────▶│
   │                                  │                              │
   │                                  │  [apply schema]            │
   │                                  │◀────────────────────────────│
   │                                  │                              │
   │                                  │  encode to AbsObject         │
   │                                  │────────────────────────────▶│
   │                                  │                              │
   │                                  │  [map to SL]                 │
   │                                  │◀────────────────────────────│
   │                                  │                              │
   │                                  │  return AbsObject            │
   │                                  │◀────────────────────────────│
   │                                  │                              │
   │                                  │  Codec.encode(absObj)        │
   │                                  │────────────────────────────▶│
   │                                  │                              │
   │                                  │  return SL string            │
   │                                  │◀────────────────────────────│
   │                                  │                              │
   │  [ACLMessage sent]              │                              │
```

## Sequence: Platform Shutdown

```
PlatformController              AMS                          All Agents
   │                              │                              │
   │  kill()                      │                              │
   │────────────────────────────>│                              │
   │                              │                              │
   │                              │  [notify all agents]         │
   │                              │────────────────────────────>│
   │                              │────────────────────────────>│
   │                              │────────────────────────────>│
   │                              │                              │
   │                              │  [each agent:]              │
   │                              │────────────────────────────>│
   │                              │      takeDown()             │
   │                              │◀────────────────────────────│
   │                              │      DF deregister           │
   │                              │◀────────────────────────────│
   │                              │                              │
   │  [wait for agents]           │                              │
   │                              │                              │
   │                              │  stop containers             │
   │                              │◀────────────────────────────│
   │                              │                              │
   │  [complete]                  │                              │
   │◀─────────────────────────────│                              │
```

---

*See [Architecture Diagrams](../diagrams/architecture/) for system-level views.*
