# Ontology System — JADE 4.6.0

## Overview

JADE's ontology system maps between Java objects and FIPA Semantic Language (SL) content representations. It enables agents to communicate using structured, typed content beyond simple strings.

## Architecture

```
Ontology System
├── jade.content.ContentManager — Manages encoding/decoding
├── jade.content.onto.Ontology — Base ontology class
├── jade.content.onto.BasicOntology — Built-in primitives
├── jade.content.onto.BeanOntology — Bean-based ontology
├── jade.content.lang.Codec — Codec interface
├── jade.content.lang.sl.SLCodec — SL codec implementation
├── jade.content.schema.ObjectSchema — Schema base
└── jade.content.abs.AbsObject — Abstract content
```

## Core Concepts

### ContentElement Hierarchy

```
Serializable
    │
    └── ContentElement (interface)
            ├── Term (interface)
            │     ├── Primitive
            │     │     ├── String
            │     │     ├── Long
            │     │     ├── Boolean
            │     │     └── ...
            │     ├── Concept
            │     │     └── User-defined concepts
            │     ├── Predicate
            │     │     └── User-defined predicates
            │     ├── AgentAction
            │     │     └── User-defined actions
            │     ├── Aggregate
            │     │     └── jade.util.leap.List
            │     └── Variable
            │
            └── ContentElementList
```

### Abstract Content (AbsObject)

The ontology system works with abstract representations that can be serialized:

```
AbsObject (interface)
    ├── AbsPrimitive — Simple values
    ├── AbsConcept — Concept representation
    ├── AbsPredicate — Predicate representation
    ├── AbsAgentAction — Action representation
    ├── AbsAggregate — Collection representation
    └── AbsIRE — Individual Term reference
```

## Built-in Ontologies

### BasicOntology

Provides schemas for primitive types and core FIPA concepts.

**Package**: `jade.content.onto.BasicOntology`

**Singleton**: `BasicOntology.getInstance()`

**Types Registered**:
| Type | Java Class | SL Representation |
|------|-----------|------------------|
| String | `String` | String literal |
| Long | `Long` | Integer literal |
| Double | `Double` | Float literal |
| Boolean | `Boolean` | "true" / "false" |
| Date | `java.util.Date` | FIPA DateTime |
| AID | `jade.core.AID` | Agent identifier |
| RawSequence | `byte[]` | Raw sequence |

### SerializableOntology

Handles Java Serializable objects as opaque content.

**Package**: `jade.content.onto.SerializableOntology`

**Usage**: Wrap arbitrary Serializable objects in ACL messages.

## Creating Custom Ontologies

### Step 1: Define Concept/Action Classes

```java
public class Book implements Concept {
    private String title;
    private String author;
    private Long price;
    
    public Book() {}
    
    public String getTitle() { return title; }
    public void setTitle(String t) { title = t; }
    
    public String getAuthor() { return author; }
    public void setAuthor(String a) { author = a; }
    
    public Long getPrice() { return price; }
    public void setPrice(Long p) { price = p; }
}
```

### Step 2: Create Ontology Class

```java
public class BookTradingOntology extends Ontology {
    public static final String NAME = "book-trading";
    
    // Vocabulary constants
    public static final String BOOK = "Book";
    public static final String BUY_BOOK = "buy-book";
    public static final String SELL_BOOK = "sell-book";
    public static final String TITLE = "title";
    public static final String AUTHOR = "author";
    public static final String PRICE = "price";
    
    private static final BookTradingOntology INSTANCE = 
        new BookTradingOntology();
    
    public static BookTradingOntology getInstance() {
        return INSTANCE;
    }
    
    private BookTradingOntology() {
        super(NAME, 
              new Ontology[]{BasicOntology.getInstance(), 
                             SerializableOntology.getInstance()},
              new BCReflectiveIntrospector());
        
        try {
            // Register concepts
            add(new ConceptSchema(BOOK), Book.class);
            
            // Register actions
            add(new AgentActionSchema(BUY_BOOK), BuyBook.class);
            add(new AgentActionSchema(SELL_BOOK), SellBook.class);
        } catch (OntologyException e) {
            throw new RuntimeException(e);
        }
    }
}
```

### Step 3: Register with ContentManager

```java
// In agent setup()
ContentManager cm = getContentManager();
cm.registerLanguage(new SLCodec(), FIPANames.ContentLanguage.FIPA_SL0);
cm.registerOntology(BookTradingOntology.getInstance());
```

### Step 4: Use in Messages

```java
// Encode
Book book = new Book();
book.setTitle("The Art of War");
book.setAuthor("Sun Tzu");
book.setPrice(999L);

ACLMessage msg = new ACLMessage(ACLMessage.INFORM);
msg.setLanguage(FIPANames.ContentLanguage.FIPA_SL0);
msg.setOntology(BookTradingOntology.NAME);

BuyBook action = new BuyBook();
action.setBook(book);
action.setBuyer(getAID());

cm.fillContent(msg, action);
send(msg);

// Decode
ACLMessage reply = receive();
cm.fillReceiver(reply);
BuyBook result = (BuyBook) cm.extractContent(reply);
Book boughtBook = result.getBook();
```

## Schema System

### ObjectSchema

```java
public class ObjectSchema implements Serializable {
    public void add(String slotName, ObjectSchema schema);
    public void add(String slotName, ObjectSchema schema, int cardMin, int cardMax);
    public void add(String slotName, ObjectSchema schema, Object defaultValue);
    public void addFacet(String slotName, Facet f);
    
    public ObjectSchema getSchema(String slotName);
    public int getCardinalityMin(String slotName);
    public int getCardinalityMax(String slotName);
    public boolean isMandatory(String slotName);
}
```

### Schema Types

| Schema Type | For | Example |
|------------|-----|---------|
| `ConceptSchema` | Concepts | `Book`, `Person` |
| `PredicateSchema` | Predicates | ` Likes(book, person)` |
| `AgentActionSchema` | Actions | `BuyBook`, `SellBook` |
| `PrimitiveSchema` | Primitives | `String`, `Long` |
| `AggregateSchema` | Collections | `List<Book>` |
| `VariableSchema` | Variables | `?x` |

### Schema Facets

Facets add constraints to slot values:

```java
// Mandatory slot
schema.add("name", new PrimitiveSchema(BasicOntology.STRING), 1, 1);

// Optional slot with default
schema.add("author", new PrimitiveSchema(BasicOntology.STRING), 0, 1, "Unknown");

// List of values
schema.add("keywords", new PrimitiveSchema(BasicOntology.STRING), 0, -1); // -1 = unlimited

// With regex constraint
schema.addFacet("email", new RegexFacet("[a-z]+@[a-z]+\\.[a-z]+"));
```

## Bean Introspection

### BCReflectiveIntrospector

Uses JavaBean conventions to automatically map schema slots to getter/setter methods.

**Convention**: `getXxx()` / `setXxx()` for slot `xxx`

```java
// Bean
public class Person implements Concept {
    private String name;
    
    public String getName() { return name; }
    public void setName(String n) { name = n; }
}

// Schema auto-generated:
// slot "name" maps to getName()/setName()
```

### Annotation Support

```java
public class Person implements Concept {
    @Slot(mandatory=true)
    private String name;
    
    @Slot(defaultValue="unknown@example.com")
    private String email;
    
    @Slot(maximum=150)
    private Long age;
    
    @Slot(cardMin=0, cardMax=-1) // 0 to unlimited
    private List<String> hobbies;
}
```

## FIPA Semantic Language (SL)

### SL Levels

| Level | Features | Use Case |
|-------|----------|---------|
| SL-0 | Primitives, AID, sequences | Simple messages |
| SL-1 | SL-0 + concepts, actions | Most agent communication |
| SL-2 | SL-1 + predicates, variables | Complex reasoning |

### Codec Registration

```java
// SL-0 (simplest)
cm.registerLanguage(new SLCodec(), FIPANames.ContentLanguage.FIPA_SL0);

// SL-1 (recommended)
cm.registerLanguage(new SLCodec(), FIPANames.ContentLanguage.FIPA_SL1);

// SL-2 (full reasoning)
cm.registerLanguage(new SLCodec(), FIPANames.ContentLanguage.FIPA_SL2);
```

## Content Encoding Example

```
Java Object Tree
    │
    ▼
BeanOntologyBuilder maps to
    │
    ▼
Ontology.toObject()
    │
    ▼
AbsObject (abstract tree)
    │
    ▼
SLCodec.encode()
    │
    ▼
SL String
    │
    ▼
ACLMessage.setContent()

ACLMessage.getContent()
    │
    ▼
SLCodec.decode()
    │
    ▼
AbsObject
    │
    ▼
Ontology.fromObject()
    │
    ▼
Java Object Tree
```

## Ontology Utilities

### BeanOntologyBuilder

Programmatically build ontologies from class metadata:

```java
BeanOntologyBuilder builder = new BeanOntologyBuilder(NAME, parentOntologies);
builder.add(Book.class);
Ontology onto = builder.build();
```

### OntologyUtils

```java
// Merge ontologies
Ontology merged = OntologyUtils.merge(onto1, onto2);

// Clone with modifications
Ontology modified = OntologyUtils.clone(onto, additions);
```
